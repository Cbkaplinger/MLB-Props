"""Corrected pooled mean-K RMSE report for pregame-pa-ext-v1 (full_run-2).

DEFECT (versioned correction, no prediction rebuild):

The frozen scorer score_pa_ext.py stores the PER-START SQUARED ERROR
(mean_k - realized_k)**2 in the column `{tag}_rmse_mean_k`, then emitted
the pooled aggregate as

    rmse_mean_k = sqrt( mean( squared_error**2 ) )   # BUG: 4th-power mean

i.e. sqrt(mean(err^4)) over raw errors instead of sqrt(mean(err^2)). The
correct pooled RMSE over per-start squared errors `se` is

    rmse_mean_k = sqrt( mean( se ) )

This script recomputes, from the PERSISTED per-start squared errors in
data/start_metrics_paext.parquet (full_run-2 outputs are read-only here):

  1. corrected pooled RMSE for both registered RAW arms;
  2. per-block RMSE (n, MSE, RMSE per registered block), with a check that
     the row-weighted block-MSE aggregation reproduces the pooled value;
  3. regression evidence: the buggy sqrt(mean(se^2)) form reproduces the
     values in the preserved report_scored.json bit-near-exactly, proving
     the defect and that this correction reads the same inputs;
  4. RMSE bootstrap CI status: full_run-2 reported NO RMSE uncertainty
     (bootstrap_results covers rps/logscore/Brier diffs only), so the
     conditional CI recompute is NOT triggered; see corrected_report.json.

Writes corrected_report.json next to this script. Does NOT modify any
full_run-2 artifact.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

WORK = Path(__file__).resolve().parent.parent          # outputs/full_run_2
PARQUET = WORK / "data" / "start_metrics_paext.parquet"
REPORT = WORK / "report_scored.json"
ARMS = ("h3_raw", "l5_raw")
BLOCK_COL = "block"


def corrected_pooled_rmse(squared_errors: np.ndarray) -> float:
    """Correct pooled RMSE from per-start SQUARED errors: sqrt(mean(se))."""
    se = np.asarray(squared_errors, dtype=np.float64)
    if se.ndim != 1 or se.size == 0:
        raise ValueError("squared_errors must be a non-empty 1-D array")
    if (se < 0).any():
        raise ValueError("input must already be SQUARED errors (non-negative)")
    return float(np.sqrt(se.mean()))


def buggy_pooled_rmse_v1(squared_errors: np.ndarray) -> float:
    """The shipped (buggy) form: sqrt(mean(se**2)) = sqrt(mean(err^4))."""
    se = np.asarray(squared_errors, dtype=np.float64)
    return float(np.sqrt((se ** 2).mean()))


def row_weighted_block_rmse(frame: pl.DataFrame, se_col: str) -> float:
    """sqrt((n1*mse1 + n2*mse2 + ...) / N) over registered blocks."""
    agg = frame.group_by(BLOCK_COL).agg(
        pl.len().alias("n"), pl.col(se_col).mean().alias("mse"))
    n = agg["n"].to_numpy().astype(np.float64)
    mse = agg["mse"].to_numpy()
    return float(np.sqrt((n * mse).sum() / n.sum()))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parquet_sha = sha256(PARQUET)
    report_sha = sha256(REPORT)
    report_orig = json.loads(REPORT.read_text(encoding="utf-8"))
    df = pl.read_parquet(PARQUET)
    if df.height != 7194:
        raise SystemExit(f"unexpected start count: {df.height}")

    out = {
        "card": "pregame-pa-ext-v1",
        "step": "rmse_correction_v2 (pooled mean-K RMSE recomputed from "
                "persisted per-start squared errors)",
        "date": "2026-10-14",
        "inputs": {
            "start_metrics_parquet": str(PARQUET),
            "start_metrics_parquet_sha256": parquet_sha,
            "original_report_scored_json_sha256": report_sha,
        },
        "defect": {
            "shipped_form": "rmse_mean_k = sqrt(mean(squared_error**2)) "
                            "= sqrt(mean(err^4)) over raw errors err",
            "corrected_form": "rmse_mean_k = sqrt(mean(squared_error)) "
                              "= sqrt(mean(err^2)) over raw errors err",
            "no_prediction_rebuild": True,
            "no_full_bootstrap_rerun": True,
        },
        "arms": {},
        "rmse_bootstrap_ci": {
            "status": "not_applicable",
            "reason": "full_run-2 reported NO RMSE uncertainty: "
                      "report_scored.json bootstrap_results contains only "
                      "rps/logscore/Brier paired diffs (execution_log.txt "
                      "confirms). The conditional CI recompute in the "
                      "correction spec was therefore not triggered; the "
                      "persisted per-start squared errors support a "
                      "slate-date bootstrap (2000 resamples, seed 20261001) "
                      "if the owner registers one.",
        },
    }

    for tag in ARMS:
        se_col = f"{tag}_rmse_mean_k"
        se = df[se_col].to_numpy()
        # the persisted column must BE the squared error
        re_se = (df[f"mean_k_{tag}"].to_numpy()
                 - df["realized_k"].to_numpy()) ** 2
        se_is_squared_error = bool(np.array_equal(se, re_se))
        if not se_is_squared_error:
            raise SystemExit(
                f"{se_col} does not equal (mean_k - realized_k)^2; refusing "
                "to correct from unverified inputs")

        corrected = corrected_pooled_rmse(se)
        buggy = buggy_pooled_rmse_v1(se)
        reported = report_orig["aggregate"][tag]["rmse_mean_k"]
        buggy_matches_report = bool(
            np.isclose(buggy, reported, rtol=0, atol=1e-12))

        blocks = (
            df.group_by(BLOCK_COL)
            .agg(pl.len().alias("n"), pl.col(se_col).mean().alias("mse"))
            .sort(BLOCK_COL)
        )
        per_block = {
            row[BLOCK_COL]: {
                "n": int(row["n"]),
                "mse": float(row["mse"]),
                "rmse": float(np.sqrt(row["mse"])),
            }
            for row in blocks.iter_rows(named=True)
        }
        weighted = row_weighted_block_rmse(df, se_col)
        weighted_matches_pooled = bool(np.isclose(weighted, corrected,
                                                  rtol=0, atol=1e-12))

        out["arms"][tag] = {
            "n_starts": int(df.height),
            "persisted_col_is_squared_error": se_is_squared_error,
            "reported_v1_buggy": reported,
            "buggy_recomputed_from_persisted": buggy,
            "buggy_reproduces_report": buggy_matches_report,
            "corrected_pooled_rmse": corrected,
            "row_weighted_block_aggregation": weighted,
            "row_weighted_matches_pooled": weighted_matches_pooled,
            "per_block": per_block,
        }

        print(f"{tag}: reported(buggy)={reported!r} -> corrected pooled "
              f"RMSE={corrected!r}; blocks={list(per_block)}; "
              f"buggy_reproduces_report={buggy_matches_report}; "
              f"weighted==pooled={weighted_matches_pooled}")

    dest = Path(__file__).resolve().parent / "corrected_report.json"
    dest.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
