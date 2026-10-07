"""BF-distribution diagnostic runner (2023 origins incl. April extension).

Implements frozen design preregistration
`research/offseason_2026/bf-distribution-design-prereg.md`.
ONE scored diagnostic on previously approved 2022/2023 Savant inputs.
No 2024+ data, no tuning, no calibration layers, no promotion claims.

Reuse (no blind copies):
- run_corrected_history_2023 (same package, under review together):
  input plumbing (default_sources, verify_and_load, _unified_pitches,
  _require_temp_out, MechanicalFailure), BF target (bf_table_canonical),
  team-rate builders (build_batting_rows, build_team_rate_features),
  origin assignment (assign_origins), constants (ORIGINS_2023,
  FINAL_EVAL_DATE, CHALLENGER_FEATURES, BOOTSTRAP_*).
- run_reconstruction_audit_2023 (COMMITTED main): audit_identity,
  build_history_appearances.
- workload_spine (COMMITTED main): build_appearance_history.
- bf_distribution (this package): scoring/conversion/baseline/fit.
- src/Python/statcast.py event sets via the team-rate builders.

Prohibited here: multi-season artifact opens beyond the two Savant
files, oracle lineup inputs, 2024+ access, feature search.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import bf_distribution as bfd  # noqa: E402
import workload_spine as ws  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402
from run_reconstruction_audit_2023 import (  # noqa: E402
    audit_identity,
    build_history_appearances,
)

APRIL_ORIGIN = "2023-04-15"
APRIL_FINAL = "2023-05-01"
DEFAULT_ORIGINS = ("2023-04-15", "2023-07-01", "2023-08-01",
                   "2023-09-01")
DEFAULT_FINAL = "2023-10-01"


class RunFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_frames(pitches_2023, pitches_2022, fallback_mean: float):
    """Identity, BF target, histories, and features (all 2023 rows)."""
    keys, quarantine = audit_identity(pitches_2023)
    bf, excluded = rch.bf_table_canonical(pitches_2023)
    keyed = keys.select(
        pl.col("game_pk"),
        pl.col("forecast_pitcher").alias("pitcher"),
        pl.col("game_date")).join(
        bf, on=["game_pk", "pitcher"], how="left")
    zero_bf = keyed.filter(pl.col("PA").is_null() | (pl.col("PA") < 1))
    starts = keyed.filter(pl.col("PA").is_not_null()
                          & (pl.col("PA") >= 1))
    if starts.height + zero_bf.height != keyed.height:
        raise RunFailure("zero-BF identity failed")
    pool = rch._unified_pitches([pitches_2022, pitches_2023])
    appearances, history_quarantine = build_history_appearances(
        pool.filter(pl.col("game_date").dt.year() == 2022),
        pool.filter(pl.col("game_date").dt.year() == 2023))
    forecast_all = keys.select(
        pl.col("game_pk"),
        pl.col("forecast_pitcher").alias("pitcher"),
        pl.col("game_date"))
    hist_all = ws.build_appearance_history(
        appearances, forecast_all, fallback_mean,
        date(2022, 1, 1), date(2023, 12, 31))
    game_meta = (
        pitches_2023.select("game_pk", "home_team", "away_team")
        .unique(subset=["game_pk"]))
    hand = (
        pitches_2023.select("game_pk", "pitcher", "p_throws")
        .unique(subset=["game_pk", "pitcher"]))
    lineup_free = (
        forecast_all.join(game_meta, on="game_pk", how="left")
        .join(hand, on=["game_pk", "pitcher"], how="left")
        .join(keys.select("game_pk", pl.col("forecast_pitcher").alias(
            "pitcher"), "is_home"),
            on=["game_pk", "pitcher"], how="left")
        .with_columns(
            pl.when(pl.col("is_home")).then(pl.col("away_team"))
            .otherwise(pl.col("home_team")).alias("opponent_team"),
            pl.col("p_throws").alias("pitcher_hand")))
    rated = rch.build_team_rate_features(
        lineup_free, rch.build_batting_rows(pitches_2023),
        rch.build_batting_rows(pitches_2022),
        cur_year=2023, prior_year=2022)
    frame = (
        starts.select("game_pk", "pitcher", "game_date", "PA")
        .join(hist_all.drop("game_date"), on=["game_pk", "pitcher"],
              how="left")
        .join(rated.select(
            ["game_pk", "pitcher"] + rch.CHALLENGER_FEATURES[-2:]
            + ["rate_std_source", "rate_hand_source",
               "rate_std_used_fallback", "rate_hand_unknown"]),
            on=["game_pk", "pitcher"], how="left"))
    if frame.height != starts.height:
        raise RunFailure("feature join dropped rows")
    for col in rch.CHALLENGER_FEATURES:
        if frame[col].null_count() == frame.height:
            raise RunFailure("feature entirely null: %s" % col)
    pop = {"n_raw": int(keys.height),
           "n_retained": int(starts.height),
           "n_zero": int(zero_bf.height),
           "n_terminal": int(excluded["n_terminal_at_bats"]),
           "n_excluded": int(excluded["n_excluded_non_pa"]),
           "n_quarantined_games": len(quarantine),
           "quarantine": quarantine,
           "n_history_quarantined_games": len(history_quarantine),
           "history_quarantine": history_quarantine}
    return frame, appearances, pop


def evaluate_origin(origin, ev, hazard_bundle, base_pmf):
    """Score distribution + point references on identical eval rows."""
    y = ev["PA"].to_numpy(dtype=int)
    feature_cols = rch.CHALLENGER_FEATURES
    pmfs = bfd.predict_pmf(
        hazard_bundle, ev[feature_cols].to_numpy(dtype=float))
    rps = np.array([bfd.rps_score(p, int(k)) for p, k in zip(pmfs, y)])
    nlls, clipped = zip(*[bfd.count_nll(p, int(k))
                           for p, k in zip(pmfs, y)])
    briers = np.array([bfd.short_outing_brier(p, int(k))
                       for p, k in zip(pmfs, y)])
    base_rps = np.array([bfd.rps_score(base_pmf, int(k)) for k in y])
    rows = pd.DataFrame({
        "origin": origin,
        "game_pk": ev["game_pk"].to_numpy(),
        "pitcher": ev["pitcher"].to_numpy(),
        "game_date": ev["game_date"].astype(str).to_numpy(),
        "PA": y,
        "category": [bfd._category(int(k)) for k in y],
        "rps": rps,
        "nll": np.array(nlls),
        "nll_clipped": np.array(clipped),
        "short_brier": briers,
        "base_rps": base_rps,
    })
    return rows, pmfs


def run_diagnostic(pitches_2023, pitches_2022, fallback_mean: float,
                   origins, final_date, out_dir: Path,
                   prereg_path: Path) -> dict:
    """Full scored diagnostic on injected frames. Returns manifest."""
    out_dir = Path(out_dir)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        frame, appearances, pop = build_frames(
            pitches_2023, pitches_2022, fallback_mean)
        pdf = frame.to_pandas()
        assigned = rch.assign_origins(pdf, tuple(origins), final_date)
        per_origin_rows = []
        per_origin_pmfs = []
        per_origin = {}
        blocked = None
        for origin in origins:
            origin_ts = pd.Timestamp(origin)
            train = assigned[
                (assigned["origin"].isna())
                & (assigned["game_date"] < origin_ts)
            ]
            ev = assigned[assigned["origin"] == origin]
            if len(ev) == 0:
                raise RunFailure(
                    "no evaluation rows for origin %s" % origin)
            if len(train) == 0:
                blocked = {"origin": origin,
                           "reason": "no training rows"}
                break
            bundle = bfd.fit_hazard(
                train[rch.CHALLENGER_FEATURES].to_numpy(dtype=float),
                train["PA"].to_numpy(dtype=int),
                list(rch.CHALLENGER_FEATURES))
            base_counts = bfd.counts_from_outcomes(
                [int(v) for v in train["PA"].to_numpy(dtype=int)])
            base_pmf = bfd.empirical_baseline(base_counts)
            rows, pmfs = evaluate_origin(origin, ev, bundle, base_pmf)
            per_origin_rows.append(rows)
            per_origin_pmfs.append(pmfs)
            per_origin[origin] = {
                "n_eval": int(len(ev)),
                "n_train": int(len(train)),
            }
        if not per_origin_rows:
            pooled = {"pooled": False, "reason": "no evaluation rows"}
            all_rows = pd.DataFrame()
            all_pmfs = np.empty((0, bfd.N_CATEGORIES))
        else:
            all_rows = pd.concat(per_origin_rows, ignore_index=True)
            all_pmfs = np.concatenate(per_origin_pmfs, axis=0)
            pooled = _pool_scores(all_rows, all_pmfs)
        manifest = _manifest(prereg_path, origins, final_date, pop,
                             per_origin, pooled, blocked, all_rows)
        _write_outputs(manifest, all_rows, all_pmfs, out_dir)
        return manifest
    except Exception as exc:  # noqa: BLE001 - receipt then re-raise
        import traceback as _tb

        receipt = {
            "status": "MECHANICAL_FAILURE",
            "stage": "run_diagnostic",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": _tb.format_exc(),
        }
        (out_dir / "failure_receipt.json").write_text(
            json.dumps(receipt, indent=2, default=str), encoding="ascii")
        raise


def _pool_scores(all_rows: pd.DataFrame,
                 all_pmfs: np.ndarray) -> dict:
    pooled = {
        "pooled": True,
        "n_eval": int(len(all_rows)),
        "n_unique_dates": int(all_rows["game_date"].nunique()),
        "n_unique_pitchers": int(all_rows["pitcher"].nunique()),
        "mean_rps": float(all_rows["rps"].mean()),
        "mean_nll": float(all_rows["nll"].mean()),
        "nll_clipped": int(all_rows["nll_clipped"].sum()),
        "mean_short_brier": float(all_rows["short_brier"].mean()),
        "baseline_mean_rps": float(all_rows["base_rps"].mean()),
    }
    dates = all_rows["game_date"].astype(str).to_numpy()
    pitchers = all_rows["pitcher"].to_numpy()
    pooled["paired"] = {}
    for comp, col in (("hazard_vs_baseline", "rps"),):
        d = (all_rows["rps"].to_numpy() - all_rows["base_rps"].to_numpy())
        pooled["paired"][comp] = {
            "comparison_id": "bf_hazard_v1__vs__empirical_v1",
            "slate_date_primary": rch.cluster_bootstrap(d, dates),
            "pitcher_sensitivity": rch.cluster_bootstrap(d, pitchers),
        }
    pooled["slices"] = []
    masks = {
        "bf_lt9": all_rows["PA"] < 9,
        "bf_le6": all_rows["PA"] <= 6,
        "bf_7_8": (all_rows["PA"] >= 7) & (all_rows["PA"] <= 8),
        "bf_ge9": all_rows["PA"] >= 9,
    }
    months = pd.to_datetime(all_rows["game_date"]).dt.strftime("%Y-%m")
    for m in sorted(months.unique()):
        masks["month_%s" % m] = months == m
    for o in sorted(all_rows["origin"].unique()):
        masks["origin_%s" % o] = all_rows["origin"] == o
    for name, mask in masks.items():
        sub = all_rows[mask]
        pos = sub.index.to_numpy()
        entry = {"slice": name, "n": int(len(sub))}
        if len(sub):
            entry.update({
                "mean_rps": float(sub["rps"].mean()),
                "mean_nll": float(sub["nll"].mean()),
                "mean_short_brier": float(sub["short_brier"].mean()),
            })
            iv50 = [bfd.central_interval(all_pmfs[i], 0.50) for i in pos]
            iv80 = [bfd.central_interval(all_pmfs[i], 0.80) for i in pos]
            entry["coverage_50"] = float(np.mean(
                [bfd.interval_covered(iv, int(k))
                 for iv, k in zip(iv50, sub["PA"].to_numpy(dtype=int))]))
            entry["coverage_80"] = float(np.mean(
                [bfd.interval_covered(iv, int(k))
                 for iv, k in zip(iv80, sub["PA"].to_numpy(dtype=int))]))
            entry["mean_width_50"] = float(np.mean([iv[2] for iv in iv50]))
            entry["mean_width_80"] = float(np.mean([iv[2] for iv in iv80]))
        else:
            entry.update({"mean_rps": None, "mean_nll": None,
                          "mean_short_brier": None, "coverage_50": None,
                          "coverage_80": None, "mean_width_50": None,
                          "mean_width_80": None})
        pooled["slices"].append(entry)
    return pooled


def _manifest(prereg_path, origins, final_date, pop, per_origin,
              pooled, blocked, all_rows) -> dict:
    here = Path(__file__).resolve()

    def _sha(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    return {
        "lane": "bf_distribution_2023",
        "preregistration": str(prereg_path),
        "preregistration_sha256": _sha(Path(prereg_path)),
        "origins": list(origins),
        "final_date": final_date,
        "code": {
            "run_bf_distribution_2023.py": _sha(here),
            "bf_distribution.py": _sha(here.parent / "bf_distribution.py"),
            "run_corrected_history_2023.py": _sha(
                here.parent / "run_corrected_history_2023.py"),
            "workload_spine.py": _sha(
                Path(ws.__file__)),
        },
        "population": pop,
        "origins_detail": per_origin,
        "pooled": pooled,
        "status": "BLOCKED" if blocked else "COMPLETE",
    }


def _write_outputs(manifest, all_rows, all_pmfs, out_dir) -> None:
    keep = ["origin", "game_pk", "pitcher", "game_date", "PA",
            "category", "rps", "nll", "nll_clipped", "short_brier",
            "base_rps"]
    if len(all_rows):
        all_rows[keep].to_csv(out_dir / "predictions.csv", index=False)
    else:
        pd.DataFrame({c: [] for c in keep}).to_csv(
            out_dir / "predictions.csv", index=False)
    pmf_cols = ["pmf_%02d" % i for i in range(bfd.N_CATEGORIES)]
    pl.DataFrame(np.asarray(all_pmfs, dtype=float),
                 schema=pmf_cols).write_parquet(out_dir / "pmfs.parquet")
    manifest_path = out_dir / "bf_distribution_manifest.json"
    if manifest_path.exists():
        raise RunFailure("manifest already exists; refusing overwrite")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str), encoding="ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="BF-distribution diagnostic (one run; needs "
                    "execution authorization).")
    parser.add_argument("--out", required=True)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--prereg", required=True)
    parser.add_argument("--origins", default=",".join(DEFAULT_ORIGINS))
    parser.add_argument("--final-date", default=DEFAULT_FINAL)
    parser.add_argument("--season-sha", action="append", default=[])
    parser.add_argument("--fallback-mean", type=float, required=True)
    parser.add_argument("--fallback-source", required=True)
    parser.add_argument("--fallback-cutoff", required=True)
    args = parser.parse_args(argv)

    from run_corrected_history_2023 import (  # noqa: E402
        MechanicalFailure,
        default_sources,
        verify_and_load,
    )

    out_dir = Path(args.out)
    try:
        rch._require_temp_out(out_dir)
        root = Path(args.data_root) if args.data_root else rch.REPO / "data"
        prereg_path = Path(args.prereg)
        if not prereg_path.is_file():
            raise RunFailure("missing preregistration file")
        shas: dict[int, str] = {}
        for item in args.season_sha or []:
            try:
                year_s, digest = item.split(":", 1)
                shas[int(year_s)] = digest.lower()
            except ValueError:
                raise RunFailure(
                    "--season-sha must look like YYYY:hex, got %r" % (item,))
        sources = default_sources(root, 2023, (2022,), shas)
        pitches = {}
        verified = {}
        for name, spec in sources.items():
            frame = verify_and_load(spec)
            verified[name] = spec["sha256"]
            year = int(str(name).split("_")[1])
            years = sorted(rch.frame_years(frame))
            if years != [year]:
                raise RunFailure(
                    "period violation in %s: years %s" % (name, years))
            pitches[year] = rch._unified_pitches([frame])
        if 2023 not in pitches or 2022 not in pitches:
            raise RunFailure("2022 and 2023 inputs both required")
        origins = tuple(o for o in args.origins.split(",") if o)
        if not origins:
            raise RunFailure("no origins supplied")
        manifest = run_diagnostic(
            pitches[2023], pitches[2022], args.fallback_mean,
            origins, args.final_date, out_dir, prereg_path)
        manifest["inputs"] = {
            name: {"path": str(Path(spec["path"]).resolve()),
                   "sha256": verified[name]}
            for name, spec in sources.items()
        }
        manifest["fallback"] = {
            "mean_bf": float(args.fallback_mean),
            "population_mean_source": args.fallback_source,
            "source_cutoff": args.fallback_cutoff,
            "mode": "declared",
            "provenance": "DECLARED by caller; not independently verified",
        }
        (out_dir / "bf_distribution_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="ascii")
        print(json.dumps({"status": manifest["status"]}))
        return 0 if manifest["status"] == "COMPLETE" else 1
    except (RunFailure, MechanicalFailure, SystemExit) as exc:
        print("RUN %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
