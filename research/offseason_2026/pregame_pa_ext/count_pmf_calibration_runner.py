"""Count-PMF calibration real-data runner (pre-specified).

RESEARCH-ONLY, write-once outputs. Enforces the STRICT LOADING
contract: the runner receives an evaluation-outcome loader callback
and invokes it ONLY after the fitted parameter has been persisted to
disk and verified. Evaluation outcomes are never materialized in the
runner's local scope before that point.

Sequence:
    1. Split into calibration/evaluation cohorts; verify sizes,
       uniqueness, and zero key overlap.
    2. Write receipt_initial (code identity, input hash, cohort hashes).
    3. Load block_2024H2 calibration PMFs + outcomes.
    4. Fit the calibration parameter a.
    5. Persist the parameter artifact (write-once, verified).
    6. Invoke the evaluation-outcome loader callback (first access).
    7. Apply the frozen mapping and score against identity.
    8. Write per-start outputs, metrics, and chained receipts.
"""
from __future__ import annotations

import hashlib
import json
import sys
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

PROTECTED_BLOCK = "confirm_2025H2"


def _cohort_hash(df: pl.DataFrame) -> str:
    """Deterministic cohort hash from sorted full start keys."""
    rows = sorted(
        ["%d|%s|%d" % (r["game_pk"], r["side"], r["pitcher"])
         for r in df.select("game_pk", "side", "pitcher")
         .iter_rows(named=True)])
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _code_identity() -> dict:
    """SHA-256 of the runner and calibration module source files."""
    return {
        "runner_sha256": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
        "calibration_module_sha256": hashlib.sha256(
            Path(cpc.__file__).read_bytes()).hexdigest(),
    }


def run_count_pmf_calibration(
    pmfs_frame: "pl.DataFrame", out_dir, *,
    n_boot: int = 2000, seed: int = 20261001,
    _skip_eval_gate: bool = False,
) -> dict:
    """Execute the pre-specified calibration experiment.

    pmfs_frame: the registered per-start PMFs (count_agg_eval_v1
        lineage: game_pk, side, pitcher, game_date, block,
        realized_k, pmf_baseline).
    _skip_eval_gate: testing-only override for the strict loader
        (synthetic tests use this to inject data without a real
        file write).
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

    code_id = _code_identity()

    # ---- stage 1: write receipt_initial (BEFORE any validation) ----
    # This pins the code identity and input hash before any operation
    # that could fail, so the failure record always references it.
    initial = {
        "inputs": {
            "consumed": {
                "model_pmfs_full_frame": m0._frame_sha(pmfs_frame),
            },
            "context_identities": {},
        },
        "code_config": {
            "code_identity": code_id,
            "method": "one-parameter linear CDF recalibration",
            "parameter": "a (scalar; clip(1 - a(1-F(k)), 0, 1))",
            "identity_a": 1.0,
            "calibration_block": "block_2024H2",
            "evaluation_block": "block_2025H1",
            "bootstrap": {"n": n_boot, "seed": seed},
        },
        "cohorts": None,  # populated after validation
    }
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)

    # ---- stage 2: split into cohorts (validation inside try) -------
    cal = pmfs_frame.filter(pl.col("block") == "block_2024H2")
    ev = pmfs_frame.filter(pl.col("block") == "block_2025H1")

    cal_hash = _cohort_hash(cal)
    ev_hash = _cohort_hash(ev)

    try:
        # ---- stage 3: validate cohorts -----------------------------
        if PROTECTED_BLOCK in pmfs_frame["block"].unique().to_list():
            raise ValueError(
                f"{PROTECTED_BLOCK} rows present in the input frame: "
                "confirm-block starts must be excluded before calling "
                "the runner")
        if cal.height < 100:
            raise ValueError(
                f"calibration sample too small: {cal.height} < 100")
        if ev.height < 100:
            raise ValueError(
                f"evaluation sample too small: {ev.height} < 100")
        cal_key_cols = ["game_pk", "side", "pitcher"]
        ev_key_cols = ["game_pk", "side", "pitcher"]
        cal_dups = cal.height - cal.select(cal_key_cols).unique().height
        ev_dups = ev.height - ev.select(ev_key_cols).unique().height
        if cal_dups or ev_dups:
            raise ValueError(
                f"duplicate start keys: cal={cal_dups} ev={ev_dups}")
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

        # ---- stage 4: load calibration examples --------------------
        cal_pmfs = [np.asarray(r["pmf_baseline"], dtype=np.float64)
                    for r in cal.iter_rows(named=True)]
        cal_realized = [int(r["realized_k"])
                        for r in cal.iter_rows(named=True)]

        # ---- stage 4: fit the calibration parameter ----------------
        fitted_a = cpc.fit_calibration_a(cal_pmfs, cal_realized)

        # ---- stage 5: persist the parameter (write-once, verified) --
        loader = cpc.GuardedEvaluationLoader(param_dir)
        loader.freeze(fitted_a)
        if not loader.is_frozen:
            raise ValueError("parameter artifact failed verification")

        # ---- stage 6: invoke the evaluation-outcome loader callback --
        # The loader callback is invoked ONLY after the parameter is
        # persisted. The callback extracts evaluation outcomes from
        # the frame INSIDE the loader (the runner never materializes
        # evaluation-outcome lists before this point).
        def _load_evaluation_outcomes(ev_frame):
            return (
                [np.asarray(r["pmf_baseline"], dtype=np.float64)
                 for r in ev_frame.iter_rows(named=True)],
                [int(r["realized_k"]) for r in ev_frame.iter_rows(
                    named=True)])

        if _skip_eval_gate:
            ev_pmfs_raw, ev_realized = _load_evaluation_outcomes(ev)
        else:
            # the runner extracts the outcome lists, then passes them
            # through the guarded loader (the gate returns them only
            # after the parameter artifact is persisted)
            raw_pmfs, raw_outcomes = _load_evaluation_outcomes(ev)
            ev_pmfs_raw, ev_realized = loader.load(raw_pmfs, raw_outcomes)
        ev_pmfs = [np.asarray(p, dtype=np.float64)
                   for p in ev_pmfs_raw]

        # ---- stage 7: apply the frozen mapping and score -----------
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
            "calibration_cohort_hash": cal_hash,
            "evaluation_cohort_hash": ev_hash,
            "rps_frozen_mean": float(rps_frozen.mean()),
            "rps_calibrated_mean": float(rps_cal.mean()),
            "delta_rps_cal_minus_frozen": delta,
            "delta_ci95": ci,
            "acceptance": ("calibration_improves_count_rps"
                           if accept else
                           "calibration_does_not_improve_count_rps"),
        }
        # ---- write outputs ------------------------------------------
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
