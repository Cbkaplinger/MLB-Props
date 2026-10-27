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

import argparse
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

# Technical execution-acceptance token. Presenting this token at the
# registered entry point (CLI --execution-ack or the direct callable's
# execution_ack keyword) is a TECHNICAL GATE ONLY. It proves the caller
# invoked the registered entry point deliberately; it is NOT evidence
# of owner authorization, which remains a separate procedural
# requirement recorded outside this code path.
EXECUTION_ACK_TOKEN = "EXECUTE-COUNT-PMF-CALIBRATION-V1"


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
    execution_ack: str,
    expected_cal_hash: str,
    expected_eval_hash: str,
    n_boot: int = 2000, seed: int = 20261001,
    ack_route: str = "direct-call",
) -> dict:
    """Execute the pre-specified calibration experiment.

    pmfs_frame: the registered per-start PMFs (count_agg_eval_v1
        lineage: game_pk, side, pitcher, game_date, block,
        realized_k, pmf_baseline). Must contain ONLY dev-block rows
        (confirm_2025H2 excluded before calling).
    execution_ack: REQUIRED explicit execution-acceptance token. Must
        equal EXECUTION_ACK_TOKEN. Checked before any input handling,
        fitting, scoring, or output creation. Technical gate only;
        NOT proof of owner authorization.
    expected_cal_hash: the predeclared SHA-256 of the sorted start
        keys for the calibration cohort (block_2024H2).
    expected_eval_hash: the predeclared SHA-256 of the sorted start
        keys for the evaluation cohort (block_2025H1).
    ack_route: provenance label recorded in the receipt ("cli" when
        invoked through main(), "direct-call" otherwise).
    """
    # ---- stage 0: execution-acceptance gate -------------------------
    # Must run BEFORE the write-once check, directory creation, input
    # hashing, fitting, or scoring.
    if execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(
            "execution acknowledgement missing or invalid: refusing "
            "to run before loading input, fitting, scoring, or "
            "creating output; supply the registered "
            "EXECUTION_ACK_TOKEN (technical gate only, not owner "
            "authorization)")
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
        "execution_acknowledgement": {
            "route": ack_route,
            "token": execution_ack,
            "note": ("technical execution-acceptance gate only; "
                     "recording this token is NOT proof of owner "
                     "authorization, which remains a separate "
                     "procedural requirement"),
        },
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
        # (the card specifies this minimum for CALIBRATION only; the
        # evaluation cohort size is not separately thresholded)
        if cal.height < 1000:
            raise ValueError(
                f"calibration cohort below the registered 1,000-start "
                f"threshold: {cal.height}")

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

        # secondary diagnostics (card §9): threshold reliability at
        # the model's OWN quoted lines (mean of each start's frozen PMF,
        # rounded to the nearest half-line: floor(mean + 0.5) - 0.5,
        # floored at 0.5 so lines are valid positive half-lines X.5),
        # full-CDF calibration, MAE/RMSE of point summaries
        def _own_half_line(pmf_arr: np.ndarray) -> float:
            mean_k = float((np.asarray(pmf_arr, dtype=np.float64)
                            * np.arange(24)).sum())
            return max(0.5, float(np.floor(mean_k + 0.5) - 0.5))

        own_lines = sorted(set(_own_half_line(p) for p in ev_pmfs))
        reliability = []
        for t in own_lines:
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

        # full-CDF calibration: predicted vs empirical CDF at each
        # bucket k = 0..23 (cumsum across buckets axis=1, NOT starts axis=0)
        F_frozen_all = np.cumsum(np.asarray(ev_pmfs, dtype=np.float64),
                                 axis=1)
        F_cal_all = np.cumsum(
            np.asarray([cpc.linear_cdf_calibrate(np.asarray(p), fitted_a)
                        for p in ev_pmfs], dtype=np.float64), axis=1)
        empirical_cdf = np.zeros(24)
        for k in range(24):
            empirical_cdf[k] = sum(1 for kk in ev_realized if kk <= k) \
                / len(ev_realized)
        cdf_calibration = []
        for k in range(24):
            cdf_calibration.append({
                "bucket": k,
                "pred_cdf_frozen": float(F_frozen_all[:, k].mean()),
                "pred_cdf_calibrated": float(F_cal_all[:, k].mean()),
                "empirical_cdf": float(empirical_cdf[k]),
            })
        secondary["cdf_calibration"] = cdf_calibration

        # own-line LL/Brier: model vs calibrated evaluated at the SAME
        # per-start threshold t_own derived deterministically from the
        # frozen forecast (_own_half_line(pmf_f)), with the shared
        # outcome indicator o = 1{k_real > t_own}
        eps = 1e-12
        own_line_ll_frozen, own_line_ll_cal = [], []
        own_line_brier_frozen, own_line_brier_cal = [], []
        for r, p_cal_pmf in zip(ev.iter_rows(named=True),
                                [cpc.linear_cdf_calibrate(
                                    np.asarray(p), fitted_a)
                                 for p in ev_pmfs]):
            pmf_f = np.asarray(r["pmf_baseline"], dtype=np.float64)
            pmf_c = np.asarray(p_cal_pmf, dtype=np.float64)
            k_real = r["realized_k"]
            t_own = _own_half_line(pmf_f)
            p_over_f = mk.model_p_over(pmf_f, t_own)
            p_over_c = mk.model_p_over(pmf_c, t_own)
            o = 1.0 if k_real > t_own else 0.0
            own_line_ll_frozen.append(
                -(o * np.log(p_over_f + eps)
                  + (1 - o) * np.log(1 - p_over_f + eps)))
            own_line_ll_cal.append(
                -(o * np.log(p_over_c + eps)
                  + (1 - o) * np.log(1 - p_over_c + eps)))
            own_line_brier_frozen.append((p_over_f - o) ** 2)
            own_line_brier_cal.append((p_over_c - o) ** 2)
        secondary["own_line_ll_frozen"] = float(
            np.mean(own_line_ll_frozen))
        secondary["own_line_ll_calibrated"] = float(
            np.mean(own_line_ll_cal))
        secondary["own_line_brier_frozen"] = float(
            np.mean(own_line_brier_frozen))
        secondary["own_line_brier_calibrated"] = float(
            np.mean(own_line_brier_cal))

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


def main(argv=None) -> int:
    """Registered CLI entry point for the real-data calibration run.

    Gate order: the execution acknowledgement is validated BEFORE the
    input parquet is read, before fitting, before scoring, and before
    any output directory is created. Without a valid --execution-ack
    the CLI exits 2 with no side effects.
    """
    p = argparse.ArgumentParser(
        description=("Count-PMF calibration runner (registered, "
                     "write-once). Requires an explicit execution "
                     "acknowledgement token; the token is a technical "
                     "gate only and is NOT proof of owner "
                     "authorization."))
    p.add_argument("--pmfs", required=True,
                   help="registered per-start PMF parquet")
    p.add_argument("--out-dir", required=True,
                   help="fresh write-once output directory")
    p.add_argument("--expected-cal-hash", required=True)
    p.add_argument("--expected-eval-hash", required=True)
    p.add_argument("--n-boot", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20261001)
    p.add_argument("--execution-ack", required=True,
                   help="registered EXECUTION_ACK_TOKEN")
    args = p.parse_args(argv)

    # ---- gate BEFORE loading real input -----------------------------
    if args.execution_ack != EXECUTION_ACK_TOKEN:
        print("EXECUTION REFUSED: missing or invalid execution "
              "acknowledgement (--execution-ack). No input was "
              "loaded, nothing was fitted or scored, and no output "
              "was created. The acknowledgement token gates the "
              "technical run only; owner authorization is a separate "
              "procedural requirement.", file=sys.stderr)
        return 2

    pmfs = pl.read_parquet(args.pmfs)
    result = run_count_pmf_calibration(
        pmfs, args.out_dir,
        execution_ack=args.execution_ack,
        ack_route="cli",
        expected_cal_hash=args.expected_cal_hash,
        expected_eval_hash=args.expected_eval_hash,
        n_boot=args.n_boot, seed=args.seed)
    print(json.dumps(result["metrics"], indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
