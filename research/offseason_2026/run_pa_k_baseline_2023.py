"""PA-K baseline scored runner (2023, first-pitcher PAs, expanding training).

Implements `research/offseason_2026/pa-k-baseline-prereg.md`
(sha 9bc963966cc5e19073d2aff77dbfe9609b757374657cdc460860c5dc416da6f3).

ONE scored run on the approved sha-verified 2023 + 2022 Savant inputs.
Arms: A = shrunk log5 baseline; B = L2 logistic (richer frozen features -
baseline-versus-richer-model comparison, NOT same-information).
Primary gate: pooled paired log-loss (B-A) date-clustered 95% CI
entirely below 0. 2023 DEVELOPMENTAL; conditional matchup diagnostic
only - no deployable xK or ladder claim.

2022 enters ONLY through prior-rate aggregates; the logistic trains on
2023 PAs strictly before each origin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
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

import pa_k_baseline as pak  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402

PA_COLUMNS = ["game_pk", "game_date", "pitcher", "batter", "stand",
              "p_throws", "events", "at_bat_number"]
ORIGINS = (date(2023, 4, 15), date(2023, 7, 1), date(2023, 8, 1),
           date(2023, 9, 1))
FINAL = date(2023, 10, 1)
SEED = 20261001
N_BOOT = 2000
REPRO_TOL = 1e-12
BANDS = [(0.0, 0.15), (0.15, 0.20), (0.20, 0.25), (0.25, 0.30),
         (0.30, 1.01)]


class RunFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_frames(pitches_raw_2023, pitches_raw_2022, unified_2023,
                unified_2022):
    """Explicit-column PA tables + spine first-pitcher identity."""
    keys23, _q23 = rch.audit_identity(unified_2023)
    keys22, _q22 = rch.audit_identity(unified_2022)

    def pa_table(raw, keys):
        raw = raw.select(PA_COLUMNS)
        return pak.build_pa_table(
            raw, keys.select(["game_pk",
                              pl.col("forecast_pitcher").alias("pitcher")]))

    pa23 = pa_table(pitches_raw_2023, keys23)
    pa22 = pa_table(pitches_raw_2022, keys22)
    return pa23, pa22


def _wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (c - h, c + h)


def reliability(p, y):
    rows = []
    for lo, hi in BANDS:
        m = (p >= lo) & (p < hi)
        n = int(m.sum())
        k = int(y[m].sum())
        wlo, whi = _wilson(k, n)
        rows.append({"band": "[%g,%g%s" % (lo, hi, ")" if hi <= 1 else "]"),
                     "n": n, "events": k,
                     "mean_p": float(p[m].mean()) if n else None,
                     "event_freq": (k / n) if n else None,
                     "wilson_lo": wlo, "wilson_hi": whi})
    return rows


def run_diagnostic(pa23, pa22, out_dir: Path, prereg_path: Path) -> dict:
    prior_pool = pl.concat([pa22, pa23], how="vertical")
    all_rows = []
    per_origin = []
    repro_max = 0.0
    for origin in ORIGINS:
        # BF-lane eval windows: [origin, next_origin) or [09-01, 10-01)
        nxt = (ORIGINS[ORIGINS.index(origin) + 1]
               if ORIGINS.index(origin) + 1 < len(ORIGINS) else FINAL)
        ev = pa23.filter((pl.col("game_date") >= origin)
                         & (pl.col("game_date") < nxt))
        if ev.height == 0:
            raise RunFailure("no eval rows for %s" % origin)
        train23 = pa23.filter(pl.col("game_date") < origin)
        if train23.height == 0:
            raise RunFailure("no training rows for %s" % origin)
        y = ev["y"].to_numpy()

        # April shared-input + determinism assertions (NOT cross-model)
        if origin == ORIGINS[0]:
            lg1 = pak.prior_rates(prior_pool, origin, "pitcher")[1]
            lg2 = pak.prior_rates(prior_pool, origin, "pitcher")[1]
            if abs(lg1 - lg2) > 1e-12:
                raise RunFailure("April shared league rate not identical")
            pA_chk, _, _ = pak.arm_a_probs(ev, prior_pool, origin)
            pA_chk2, _, _ = pak.arm_a_probs(ev, prior_pool, origin)
            dA = float(np.abs(pA_chk - pA_chk2).max())
            if dA > REPRO_TOL:
                raise RunFailure("arm A not deterministic: %g" % dA)
            pB_chk, _ = pak.arm_b_probs(ev, train23, origin,
                                        rates_source=prior_pool)
            pB_chk2, _ = pak.arm_b_probs(ev, train23, origin,
                                         rates_source=prior_pool)
            dB = float(np.abs(pB_chk - pB_chk2).max())
            if dB > REPRO_TOL:
                raise RunFailure("arm B not deterministic: %g" % dB)

        pA, lg, (np_p, nb_p) = pak.arm_a_probs(ev, prior_pool, origin)
        pB, _bundle = pak.arm_b_probs(ev, train23, origin,
                                      rates_source=prior_pool)
        llA = pak.logloss(pA, y)
        llB = pak.logloss(pB, y)
        rawA = pA
        rawB = pB
        clipA = int(((rawA <= pak.CLIP_LO) | (rawA >= pak.CLIP_HI)).sum())
        clipB = int(((rawB <= pak.CLIP_LO) | (rawB >= pak.CLIP_HI)).sum())
        rows = pd.DataFrame({
            "origin": str(origin),
            "game_pk": ev["game_pk"].to_numpy(),
            "at_bat_number": ev["at_bat_number"].to_numpy(),
            "pitcher": ev["pitcher"].to_numpy(),
            "batter": ev["batter"].to_numpy(),
            "game_date": ev["game_date"].cast(str).to_numpy(),
            "y": y,
            "p_A": pA, "p_B": pB,
            "ll_A": llA, "ll_B": llB,
            "brier_A": pak.brier(pA, y), "brier_B": pak.brier(pB, y),
            "pitcher_prior_pa": np_p, "batter_prior_pa": nb_p,
        })
        X = pak.arm_b_features(ev, prior_pool, origin)
        for j, f in enumerate(pak.FEATURES):
            rows["feat_" + f] = X[:, j]
        all_rows.append(rows)
        per_origin.append({
            "origin": str(origin), "n_eval": int(ev.height),
            "n_events": int(y.sum()),
            "n_train_2023": int(train23.height),
            "league_rate": lg,
            "cold_start_pitchers": int(sum(1 for v in np_p if v == 0)),
            "cold_start_batters": int(sum(1 for v in nb_p if v == 0)),
            "clip_A": clipA, "clip_B": clipB,
            "mean_ll_A": float(llA.mean()), "mean_ll_B": float(llB.mean()),
            "mean_brier_A": float(pak.brier(pA, y).mean()),
            "mean_brier_B": float(pak.brier(pB, y).mean()),
        })

    all_rows = pd.concat(all_rows, ignore_index=True)
    dates = all_rows["game_date"].to_numpy().astype(str)
    d_ll = all_rows["ll_B"].to_numpy() - all_rows["ll_A"].to_numpy()
    pooled = {
        "n": int(len(all_rows)),
        "mean_ll_A": float(all_rows["ll_A"].mean()),
        "mean_ll_B": float(all_rows["ll_B"].mean()),
        "mean_brier_A": float(all_rows["brier_A"].mean()),
        "mean_brier_B": float(all_rows["brier_B"].mean()),
        "paired": {
            "comparison_id": "pa_logistic_v1__vs__pa_log5_v1",
            "slate_date_primary": rch.cluster_bootstrap(d_ll, dates),
            "pitcher_sensitivity": rch.cluster_bootstrap(
                d_ll, all_rows["pitcher"].to_numpy().astype(str)),
        },
    }
    gate = pooled["paired"]["slate_date_primary"]
    pooled["gate1"] = {
        "definition": "pooled paired log-loss (B-A) 95% CI entirely < 0",
        "estimate": gate["estimate"], "lo95": gate["lo95"],
        "hi95": gate["hi95"], "pass": bool(gate["hi95"] < 0.0)}
    pooled["reliability_A"] = reliability(
        all_rows["p_A"].to_numpy(), all_rows["y"].to_numpy())
    pooled["reliability_B"] = reliability(
        all_rows["p_B"].to_numpy(), all_rows["y"].to_numpy())

    key_hash = hashlib.sha256(";".join(sorted(
        "%s:%s" % (k, a) for k, a in zip(
            all_rows["game_pk"].astype(str), all_rows["at_bat_number"]
            .astype(str)))).encode()).hexdigest()
    manifest = {
        "lane": "pa_k_baseline_2023",
        "status": "COMPLETE",
        "preregistration": str(prereg_path),
        "preregistration_sha256": sha256_file(Path(prereg_path)),
        "origins": [str(o) for o in ORIGINS],
        "final_date": str(FINAL),
        "population": {
            "pa_2023_first_pitcher": int(pa23.height),
            "pa_2022_first_pitcher": int(pa22.height),
            "n_eval_total": pooled["n"],
            "row_identity_hash_sha256": key_hash},
        "per_origin": per_origin,
        "pooled": pooled,
        "code": {p.name: sha256_file(p) for p in [
            HERE / "run_pa_k_baseline_2023.py",
            HERE / "pa_k_baseline.py",
            HERE / "run_corrected_history_2023.py"]},
        "notes": ("2023 DEVELOPMENTAL; conditional matchup diagnostic "
                  "only - no deployable xK or ladder claim; B tests the "
                  "model+information package (richer features), not "
                  "architecture alone; 2022 enters prior-rate aggregates "
                  "only, never as training rows"),
    }
    (out_dir / "pa_k_baseline_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="ascii")
    all_rows.to_csv(out_dir / "predictions.csv", index=False)
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--prereg", required=True)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--season-sha", action="append", default=[])
    args = ap.parse_args(argv)

    from run_corrected_history_2023 import (MechanicalFailure,
                                            default_sources, verify_and_load,
                                            _unified_pitches)

    out_dir = Path(args.out)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        prereg = Path(args.prereg)
        if not prereg.is_file():
            raise RunFailure("missing preregistration file")
        root = Path(args.data_root) if args.data_root else rch.REPO / "data"
        shas = {}
        for item in args.season_sha or []:
            y, d = item.split(":", 1)
            shas[int(y)] = d.lower()
        sources = default_sources(root, 2023, (2022,), shas)
        raw23 = verify_and_load(sources["savant_2023"])
        raw22 = verify_and_load(sources["savant_2022"])
        if sorted(rch.frame_years(raw23)) != [2023] \
                or sorted(rch.frame_years(raw22)) != [2022]:
            raise RunFailure("period violation")
        pa23, pa22 = load_frames(raw23, raw22,
                                 _unified_pitches([raw23]),
                                 _unified_pitches([raw22]))
        manifest = run_diagnostic(pa23, pa22, out_dir, prereg)
        manifest["inputs"] = {
            name: {"path": str(Path(s["path"]).resolve()),
                   "sha256": s["sha256"]}
            for name, s in sources.items()}
        (out_dir / "pa_k_baseline_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="ascii")
        print(json.dumps({"status": manifest["status"],
                          "gate1": manifest["pooled"]["gate1"],
                          "mean_ll_A": manifest["pooled"]["mean_ll_A"],
                          "mean_ll_B": manifest["pooled"]["mean_ll_B"]}))
        return 0
    except (RunFailure, MechanicalFailure) as exc:
        print("RUN %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
