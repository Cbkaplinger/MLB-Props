"""Count-PMF calibration real-data runner (pre-specified).

RESEARCH-ONLY, write-once outputs. Implements the FIT-ISOLATION
contract: the fitting procedure receives calibration examples only;
evaluation outcomes are not used for fitting, parameter selection, or
stopping decisions. Evaluation scoring follows parameter persistence.

The runner does NOT claim that evaluation outcomes were never loaded
into memory before parameter persistence. The supplied frame already
contains both blocks' realized_k values. The contract is that
evaluation outcomes do not enter the fitting path.

Sequence:
    1. Verify expected cohort hashes against the supplied frame.
    2. Write receipt_initial (code identity, input hash, expected and
       actual cohort hashes, hash recipe).
    3. Load block_2024H2 calibration PMFs + outcomes.
    4. Fit the calibration parameter a.
    5. Persist the parameter artifact (write-once, verified).
    6. Extract evaluation outcomes (fit-isolation: after fitting).
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
from pregame_pa_ext import market_eval_k as mk  # noqa: E402

import kcount_combiner as kc  # noqa: E402

PROTECTED_BLOCK = "confirm_2025H2"


def _cohort_hash(df: "pl.DataFrame") -> str:
    """Deterministic cohort hash from sorted full start keys.

    Recipe: sorted 'game_pk|side|pitcher' lines joined by \\n,
    SHA-256 hex digest.
    """
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
    expected_cal_hash: str,
    expected_eval_hash: str,
    n_boot: int = 2000, seed: int = 20261001,
) -> dict:
    """Execute the pre-specified calibration experiment.

    pmfs_frame: the registered per-start PMFs (count_agg_eval_v1
        lineage: game_pk, side, pitcher, game_date, block,
        realized_k, pmf_baseline). Must contain ONLY dev-block rows
        (confirm_2025H2 excluded before calling).
    expected_cal_hash: the predeclared SHA-256 of the sorted start
        keys for the calibration cohort (block_2024H2).
    expected_eval_hash: the predeclared SHA-256 of the sorted start
        keys for the evaluation cohort (block_2025H1).
    """
    import polars as pl

    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    initial_path = out_dir / "receipt_initial.json"
    failure_path = out_dir / "failure_record.json"
    param_dir = out_dir / "fitted_parameter"

    code_id = _code_identity()

    # ---- stage 1: write receipt_initial (BEFORE validation) --------
    # Pins the code identity, input hash, and expected cohort hashes
    # before any operation that could fail, so the failure record
    # always references it.
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
        "expected_cohort_hashes": {
            "calibration": expected_cal_hash,
            "evaluation": expected_eval_hash,
        },
        "actual_cohort_hashes": None,  # populated after splitting
        "hash_recipe": ("sorted 'game_pk|side|pitcher' lines joined "
                        "by \\n, SHA-256 hex digest"),
    }
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)

    try:
        # ---- stage 2: reject unexpected block labels ----------------
        # The runner accepts only the two registered dev blocks.
        # Protected blocks (confirm_2025H2) and any unrecognized block
        # must fail the run, not be silently filtered.
        seen_blocks = set(pmfs_frame["block"].unique().to_list())
        allowed = {"block_2024H2", "block_2025H1"}
        forbidden = seen_blocks - allowed
        if forbidden:
            raise ValueError(
                f"unexpected block labels in the input frame: "
                f"{sorted(forbidden)}; the runner accepts only "
                f"{sorted(allowed)}")

        # ---- stage 3: split into cohorts ---------------------------
        cal = pmfs_frame.filter(pl.col("block") == "block_2024H2")
        ev = pmfs_frame.filter(pl.col("block") == "block_2025H1")

        # registered card threshold: 1,000 calibration starts minimum
        if cal.height < 1000:
            raise ValueError(
                f"calibration cohort below the registered 1,000-start "
                f"threshold: {cal.height}")
        if ev.height < 1000:
            raise ValueError(
                f"evaluation cohort below the registered 1,000-start "
                f"threshold: {ev.height}")

        cal_hash = _cohort_hash(cal)
        ev_hash = _cohort_hash(ev)

        # ---- stage 3: verify cohort hashes against expected --------
        if cal_hash != expected_cal_hash:
            raise ValueError(
                f"calibration cohort hash mismatch: "
                f"actual={cal_hash} expected={expected_cal_hash}")
        if ev_hash != expected_eval_hash:
            raise ValueError(
                f"evaluation cohort hash mismatch: "
                f"actual={ev_hash} expected={expected_eval_hash}")

        # ---- stage 4: cohort uniqueness and overlap checks ---------
        cal_key_cols = ["game_pk", "side", "pitcher"]
        ev_key_cols = ["game_pk", "side", "pitcher"]
        cal_dups = cal.height - cal.select(cal_key_cols).unique().height
        if cal_dups:
            raise ValueError(
                f"duplicate cal start keys: {cal_dups}")
        ev_dups = ev.height - ev.select(ev_key_cols).unique().height
        if ev_dups:
            raise ValueError(
                f"duplicate ev start keys: {ev_dups}")
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

        # ---- stage 5: load calibration examples --------------------
        cal_pmfs = [np.asarray(r["pmf_baseline"], dtype=np.float64)
                    for r in cal.iter_rows(named=True)]
        cal_realized = [int(r["realized_k"])
                        for r in cal.iter_rows(named=True)]

        # ---- stage 6: fit the calibration parameter ----------------
        fitted_a = cpc.fit_calibration_a(cal_pmfs, cal_realized)

        # ---- stage 7: persist the parameter (write-once, verified) --
        loader = cpc.GuardedEvaluationLoader(param_dir)
        loader.freeze(fitted_a)
        if not loader.is_frozen:
            raise ValueError("parameter artifact failed verification")

        # ---- stage 8: extract evaluation outcomes -------------------
        # FIT-ISOLATION contract: evaluation outcomes are extracted
        # AFTER fitting and parameter persistence. They do not enter
        # the fitting, parameter selection, or stopping path.
        # Routed through the GuardedEvaluationLoader gate.
        raw_pmfs = [np.asarray(r["pmf_baseline"], dtype=np.float64)
                    for r in ev.iter_rows(named=True)]
        raw_outcomes = [int(r["realized_k"])
                        for r in ev.iter_rows(named=True)]
        ev_pmfs_raw, ev_realized = loader.load(raw_pmfs, raw_outcomes)
        ev_pmfs = [np.asarray(p, dtype=np.float64)
                   for p in ev_pmfs_raw]

        # ---- stage 9: apply the frozen mapping and score -----------
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

        # secondary diagnostics (card §10): threshold reliability,
        # full-CDF calibration, MAE/RMSE of point summaries
        thresholds = [4.5, 5.5, 6.5, 7.5]
        reliability = []
        for t in thresholds:
            pred_frozen = [float(mk.model_p_over(np.asarray(p), t))
                           for p in ev_pmfs]
            pred_cal = [float(mk.model_p_over(
                cpc.linear_cdf_calibrate(np.asarray(p), fitted_a), t))
                for p in ev_pmfs]
            obs = [1.0 if k > t else 0.0 for k in ev_realized]
            for pname, preds in (("frozen", pred_frozen),
                                 ("calibrated", pred_cal)):
                reliability.append({
                    "threshold": t, "predictor": pname,
                    "n": len(preds),
                    "mean_predicted": float(np.mean(preds)),
                    "observed_frequency": float(np.mean(obs)),
                })
        mean_k_frozen = [float((np.asarray(p) * np.arange(24)).sum())
                         for p in ev_pmfs]
        mean_k_cal = [float((cpc.linear_cdf_calibrate(
            np.asarray(p), fitted_a) * np.arange(24)).sum())
            for p in ev_pmfs]
        mae_frozen = float(np.mean(np.abs(
            np.asarray(mean_k_frozen) - np.asarray(ev_realized))))
        mae_cal = float(np.mean(np.abs(
            np.asarray(mean_k_cal) - np.asarray(ev_realized))))
        rmse_frozen = float(np.sqrt(np.mean(
            (np.asarray(mean_k_frozen) - np.asarray(ev_realized)) ** 2)))
        rmse_cal = float(np.sqrt(np.mean(
            (np.asarray(mean_k_cal) - np.asarray(ev_realized)) ** 2)))
        secondary = {
            "threshold_reliability": reliability,
            "mae_frozen": mae_frozen, "mae_calibrated": mae_cal,
            "rmse_frozen": rmse_frozen, "rmse_calibrated": rmse_cal,
        }

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
            "secondary": secondary,
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
    final["actual_cohort_hashes"] = {
        "calibration": cal_hash,
        "evaluation": ev_hash,
    }
    final_path = out_dir / "receipt_final.json"
    final_path.write_text(json.dumps(final, indent=1, sort_keys=True),
                          encoding="utf-8")
    if ad.sha256_file(initial_path) != initial_sha:
        raise ValueError("IMMUTABLE initial receipt modified")
    return {"out_dir": str(out_dir), "metrics": metrics,
            "receipt_final": final,
            "receipt_initial_sha256": initial_sha}
