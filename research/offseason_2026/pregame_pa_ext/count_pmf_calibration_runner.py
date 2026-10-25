"""Count-PMF calibration real-data runner (pre-specified).

RESEARCH-ONLY, write-once outputs. Enforces the evaluation-outcome
isolation contract at the code level: the runner OWNS the loading
sequence and will not read block_2025H1 outcomes until the fitted
calibration parameter has been persisted to disk.

Sequence:
    1. Verify inputs and cohort keys (hash pinned).
    2. Load block_2024H2 calibration examples (PMFs + outcomes).
    3. Fit the calibration parameter a.
    4. Persist the parameter artifact and fit provenance.
    5. Load block_2025H1 evaluation outcomes.
    6. Apply the frozen mapping and score against identity.
    7. Write per-start outputs, metrics, and chained receipts.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402
from pregame_pa_ext import count_pmf_calibration as cpc  # noqa: E402

import kcount_combiner as kc  # noqa: E402


def run_count_pmf_calibration(
    pmfs_frame: pl.DataFrame, out_dir, *,
    n_boot: int = 2000, seed: int = 20261001,
) -> dict:
    """Execute the pre-specified calibration experiment.

    pmfs_frame: the registered per-start PMFs (count_agg_eval_v1
        lineage: game_pk, side, pitcher, game_date, block,
        realized_k, pmf_baseline).
    """
    import polars as pl
    from datetime import date as _date

    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    initial_path = out_dir / "receipt_initial.json"
    failure_path = out_dir / "failure_record.json"
    param_dir = out_dir / "fitted_parameter"

    initial = {
        "inputs": {
            "consumed": {
                "model_pmfs": m0._frame_sha(pmfs_frame),
            },
            "context_identities": {},
        },
        "code_config": {
            "method": "one-parameter linear CDF recalibration",
            "parameter": "a (scalar; clip(1 - a(1-F(k)), 0, 1))",
            "identity_a": 1.0,
            "calibration_block": "block_2024H2",
            "evaluation_block": "block_2025H1",
            "bootstrap": {"n": n_boot, "seed": seed},
        },
    }
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)

    try:
        # stage 1: verify inputs and split into cal/eval cohorts
        cal = pmfs_frame.filter(pl.col("block") == "block_2024H2")
        ev = pmfs_frame.filter(pl.col("block") == "block_2025H1")
        if cal.height < 100:
            raise ValueError(
                f"calibration sample too small: {cal.height} < 100")
        if ev.height < 100:
            raise ValueError(
                f"evaluation sample too small: {ev.height} < 100")
        cal_keys = set(zip(cal["game_pk"].to_list(),
                           cal["side"].to_list(),
                           cal["pitcher"].to_list()))
        ev_keys = set(zip(ev["game_pk"].to_list(),
                          ev["side"].to_list(),
                          ev["pitcher"].to_list()))
        overlap = cal_keys & ev_keys
        if overlap:
            raise ValueError(
                f"cal/eval key overlap: {len(overlap)} shared starts")
        print(f"cal={cal.height} eval={ev.height} "
              f"overlap=0", flush=True)

        # stage 2: load block_2024H2 calibration examples
        cal_pmfs = [np.asarray(r["pmf_baseline"], dtype=np.float64)
                    for r in cal.iter_rows(named=True)]
        cal_realized = [int(r["realized_k"])
                        for r in cal.iter_rows(named=True)]

        # stage 3: fit the calibration parameter
        fitted_a = cpc.fit_calibration_a(cal_pmfs, cal_realized)
        print(f"fitted a = {fitted_a:.6f}", flush=True)

        # stage 4: persist the parameter (BEFORE loading eval outcomes)
        loader = cpc.GuardedEvaluationLoader(param_dir)
        loader.freeze(fitted_a)
        if not loader.is_frozen:
            raise ValueError("parameter artifact failed verification")
        print("parameter persisted and verified", flush=True)

        # stage 5: load block_2025H1 evaluation outcomes — routed
        # through the guarded loader so the loading is gated on the
        # persisted parameter artifact
        ev_pmfs_raw, ev_realized = loader.load(
            [np.asarray(r["pmf_baseline"], dtype=np.float64)
             for r in ev.iter_rows(named=True)],
            [int(r["realized_k"]) for r in ev.iter_rows(named=True)])
        ev_pmfs = [np.asarray(p, dtype=np.float64) for p in ev_pmfs_raw]

        # stage 6: apply the frozen mapping and score
        rps_frozen, rps_cal, keys, dates = [], [], [], []
        for ev_row, ev_pmf, ev_k in zip(
                ev.iter_rows(named=True), ev_pmfs, ev_realized):
            rps_frozen.append(
                float(kc.count_rps(ev_pmf, ev_k)))
            cal_pmf = cpc.linear_cdf_calibrate(ev_pmf, fitted_a)
            rps_cal.append(float(kc.count_rps(cal_pmf, ev_k)))
            keys.append((ev_row["game_pk"], ev_row["side"],
                         ev_row["pitcher"]))
            dates.append(ev_row["game_date"])
        rps_frozen = np.asarray(rps_frozen)
        rps_cal = np.asarray(rps_cal)

        # paired bootstrap
        cmp_mod = br.load_registered_comparison()
        blocks = ["block_2025H1"] * len(dates)
        res = cmp_mod.slate_date_draws(
            {"cal": rps_cal, "frozen": rps_frozen},
            dates, blocks, n_boot=n_boot, seed=seed)
        d_rep = res[:, 0] - res[:, 1]
        delta = float(rps_cal.mean() - rps_frozen.mean())
        ci = [float(np.percentile(d_rep, 2.5)),
              float(np.percentile(d_rep, 97.5))]
        accept = ci[1] < 0

        metrics = {
            "fitted_a": fitted_a,
            "n_calibration": int(cal.height),
            "n_evaluation": int(ev.height),
            "rps_frozen_mean": float(rps_frozen.mean()),
            "rps_calibrated_mean": float(rps_cal.mean()),
            "delta_rps_cal_minus_frozen": delta,
            "delta_ci95": ci,
            "acceptance": ("calibration_improves_count_rps"
                           if accept else
                           "calibration_does_not_improve_count_rps"),
        }
        print(f"delta = {delta:+.6f} CI {ci}", flush=True)

        # stage 7: write outputs
        per_start = pl.DataFrame({
            "game_pk": [k[0] for k in keys],
            "side": [k[1] for k in keys],
            "pitcher": [k[2] for k in keys],
            "game_date": dates,
            "realized_k": ev_realized,
            "rps_frozen": rps_frozen,
            "rps_calibrated": rps_cal,
        })
        ps_path = out_dir / "calibration_per_start_v1.parquet"
        per_start.write_parquet(ps_path)
        metrics_path = out_dir / "metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        outputs = {
            "calibration_per_start_v1.parquet":
                ad.sha256_file(ps_path),
            "metrics.json": ad.sha256_file(metrics_path),
            "fitted_a.json": ad.sha256_file(
                param_dir / "fitted_a.json"),
        }
    except Exception as exc:
        failure = {"stage": "count_pmf_calibration", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise

    final = dict(initial)
    final["metrics"] = metrics
    final["outputs"] = outputs
    final["acceptance"] = {"receipt_chain": initial_sha,
                           "fitted_a": fitted_a}
    final_path = out_dir / "receipt_final.json"
    final_path.write_text(json.dumps(final, indent=1, sort_keys=True),
                          encoding="utf-8")
    if ad.sha256_file(initial_path) != initial_sha:
        raise ValueError("IMMUTABLE initial receipt modified")
    return {"out_dir": str(out_dir), "metrics": metrics,
            "receipt_final": final,
            "receipt_initial_sha256": initial_sha}
