"""Forecast-only preflight (NO scoring, NO outcome joins).

Fresh process; corrected bundle only (FAILED_POPULATION bundles
rejected by path). Captured 2026 cohort, confirmed-only adapter,
both arms' shared BF PMFs via the frozen kcount tail contract.

COVERAGE BASIS: adapter/coverage counts use each team-game's maximum
fetch time (cutoff_basis = max_fetch_per_team_game) - a
status/completeness availability upper bound, explicitly NOT actual
forecast-cutoff usability. Actual-cutoff usability is reported
separately by the A/B forecast runner at its declared per-row cutoffs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import bf_distribution as bfd  # noqa: E402
import kcount_combiner as kc  # noqa: E402
import pregame_lineup_capture as pc  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402
import run_i3_transfer_2024 as tr  # noqa: E402
import sklearn  # noqa: E402

FAILED_BUNDLES = ("bf-bundle-2026-20261012_130026",
                  "bf-bundle-2026-20261012_131334")
K_MAX = 24


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--data-root", default=None)
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        assert not any(f in str(args.bundle) for f in FAILED_BUNDLES), \
            "FAILED_POPULATION bundle rejected"
        # mandatory pre-load identity guard (before any deserialization)
        import run_bf_ab_forecast_2026 as frun
        frun.verify_bundle_identity(args.bundle)
        root = Path(args.data_root) if args.data_root else (
            Path(__file__).resolve().parents[2] / "data")
        raws = {}
        shas = {}
        for y in (2022, 2023, 2024, 2025, 2026):
            p = (root / "Savant-Data" / "regular" / str(y)
                 / ("statcast_%d_regular.parquet" % y))
            raws[y] = pl.read_parquet(p)
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            shas[y] = h.hexdigest()
        fb = rch.derive_fallback_2022(raws[2022])
        import run_pa_lgbm_comparison as _x  # noqa: F401
        appearances, hist_quar = tr._appearances(
            [raws[2022], raws[2023], raws[2024], raws[2025], raws[2026]])
        b = {y: rch.build_batting_rows(raws[y]) for y in raws}
        frame26 = tr._season_frame(raws[2026], appearances, b[2026],
                                   b[2025], 2026, 2025, fb["mean_bf"])
        pdf26 = frame26.to_pandas()
        # captured 2026 cohort (max-fetch availability basis; see docstring)
        snaps = pc.load_snapshots(sorted(
            (root / "processed").glob("daily_lineups_*.parquet")))
        g = snaps.group_by(["game_pk", "team"]).agg(
            pl.col("fetched_at").max().alias("last_fetch"),
            pl.col("game_time").max().alias("game_time"))
        rows, fallbacks = [], {}
        pdf26["game_date"] = __import__("pandas").to_datetime(
            pdf26["game_date"])
        for r in g.iter_rows(named=True):
            sel = pc.select_pregame_lineup(
                snaps, int(r["game_pk"]), r["team"], r["last_fetch"],
                mode=pc.MODE_CONFIRMED_ONLY)
            fallbacks[sel["reason"]] = fallbacks.get(sel["reason"], 0) + 1
            for side in ("home", "away"):
                pass  # probable pitcher per team comes from the capture
        # probable-pitcher forecasts: join capture probable IDs to frame26
        probs = (snaps.select(["game_pk", "is_home",
                               "home_probable_pitcher_id",
                               "away_probable_pitcher_id"])
                 .unique(subset=["game_pk", "is_home"], keep="last")
                 .with_columns(
                     pl.when(pl.col("is_home") == 1)
                     .then(pl.col("home_probable_pitcher_id"))
                     .otherwise(pl.col("away_probable_pitcher_id"))
                     .alias("probable_pitcher_id"))
                 .with_columns(pl.col("probable_pitcher_id")
                               .cast(pl.Int64).alias("pitcher"))
                 .select(["game_pk", "pitcher"]))
        matched = probs.join(
            pl.from_pandas(pdf26), on=["game_pk", "pitcher"],
            how="inner").unique(subset=["game_pk", "pitcher"])
        n_unmatched = int(probs.height) - int(matched.height)
        feats_df = matched.to_pandas()
        feats = feats_df[rch.CHALLENGER_FEATURES].to_numpy(dtype=float)
        import pickle
        bundle = pickle.load(open(Path(args.bundle) / "bf_bundle.pkl",
                                  "rb"))
        pmfs37 = bfd.predict_pmf(bundle, feats)
        bf60 = np.array([kc.bf_pmf_from_37(p) for p in pmfs37])
        tail_mass = float(pmfs37[:, 36].mean())
        rep = {
            "bundle": str(args.bundle),
            "failed_bundles_rejected": FAILED_BUNDLES,
            "sources_sha": {str(k): v[:16] + "..." for k, v
                            in shas.items()},
            "sources_2025_2026_note": "used for PREGAME features only "
                                      "(rolling/team-rate histories); "
                                      "sha recorded, not registered",
            "fallback": fb, "tail_contract": (
                "frozen kcount_combiner.bf_pmf_from_37: P(N>=37) "
                "redistributed over 37..60 via geometric tail "
                "(ratio 1 - mean implied hazard of indices 31..36); "
                "NOT collapsed to exactly 37"),
            "mean_tail_mass_p_ge_37": tail_mass,
            "n_captured_team_games": int(g.height),
            "adapter_fallbacks_confirmed_only": fallbacks,
            "cutoff_basis": "max_fetch_per_team_game",
            "coverage_interpretation": (
                "adapter counts below are a status/completeness "
                "availability upper bound computed at each team-game's "
                "maximum fetch time; NOT actual forecast-cutoff "
                "usability; actual-cutoff forecast counts are kept "
                "separate in the A/B forecast runner receipts"),
            "n_probable_pitcher_rows": int(probs.height),
            "n_unmatched_probable_rows": n_unmatched,
            "n_matched_to_feature_frame": int(matched.height),
            "bf_pmf_shape": list(bf60.shape),
            "bf_pmf_mass_max_err": float(np.abs(
                bf60.sum(axis=1) - 1.0).max()),
            "finite_predictions": bool(np.isfinite(bf60).all()),
            "no_outcome_access": True,
            "created": str(datetime.now(timezone.utc).isoformat()),
        }
        (out_dir / "preflight_receipt.json").write_text(
            json.dumps(rep, indent=2, default=str), encoding="ascii")
        np.save(out_dir / "forecast_bf_pmfs.npy", bf60)
        (out_dir / "bf_bucket_mapping.json").write_text(
            json.dumps({"array": "forecast_bf_pmfs.npy",
                        "convention": "BF support 1..60 (KCOUNT_CAP=60); "
                                      "columns 0..35 = P(N=1)..P(N=36), "
                                      "columns 36..59 = geometric tail "
                                      "37..60 (overflow redistributed, "
                                      "frozen bf_pmf_from_37); NOT the "
                                      "final K 24-bucket mapping",
                        "keys": ["game_pk", "pitcher"],
                        "row_source": "matched probable-pitcher join"},
                       indent=1), encoding="ascii")
        print(json.dumps({k: rep[k] for k in (
            "n_captured_team_games", "adapter_fallbacks_confirmed_only",
            "n_probable_pitcher_rows", "n_matched_to_feature_frame",
            "mean_tail_mass_p_ge_37", "bf_pmf_mass_max_err")}, indent=1))
        print("WROTE %s" % out_dir)
        return 0
    except Exception as exc:
        print("BLOCKER %s: %s" % (type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
