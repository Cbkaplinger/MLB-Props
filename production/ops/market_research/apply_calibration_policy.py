"""Apply rule-based acceptance policy to line-price correction segments."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
ODDS_DIR = ROOT / "artifacts" / "odds_log"
POLICY_PATH = Path(__file__).with_name("calibration_policy.json")

CORR_PATH = ODDS_DIR / "line_price_correction_table.parquet"
DRIFT_PATH = ODDS_DIR / "open_model_regime_drift_flips.parquet"
EXEC_PATH = ODDS_DIR / "open_model_execution_sensitivity.parquet"

OUT_PATH = ODDS_DIR / "line_price_correction_table_approved.parquet"
OUT_SUMMARY = ODDS_DIR / "line_price_correction_policy_summary.json"


def main() -> None:
    if not POLICY_PATH.exists():
        raise FileNotFoundError(f"Missing policy file: {POLICY_PATH}")
    for p in (CORR_PATH, DRIFT_PATH, EXEC_PATH):
        if not p.exists():
            raise FileNotFoundError(f"Missing dependency artifact: {p}")

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    accept = policy["acceptance"]
    guard = policy["guardrails"]

    corr = pl.read_parquet(CORR_PATH)
    drift = pl.read_parquet(DRIFT_PATH).select(
        "line", "over_price_bucket", "maturity_bucket", "flip_rate"
    )
    execs = pl.read_parquet(EXEC_PATH).select(
        "line", "maturity_bucket", "brier_gain_from_correction"
    )

    merged = (
        corr.join(drift, on=["line", "over_price_bucket", "maturity_bucket"], how="left")
        .join(execs, on=["line", "maturity_bucket"], how="left")
        .with_columns(
            pl.col("flip_rate").fill_null(1.0),
        )
    )

    approved = merged.with_columns(
        (
            (pl.col("n") >= int(accept["min_segment_n"]))
            & (pl.col("flip_rate") <= float(accept["max_flip_rate"]))
            & (
                (pl.col("brier_gain_from_correction").is_not_null())
                if bool(guard["require_non_null_brier_gain"])
                else pl.lit(True)
            )
            & (pl.col("brier_gain_from_correction").fill_null(-1.0) >= float(accept["min_brier_gain"]))
            & (pl.col("prob_offset").abs() <= float(accept["max_abs_offset"]))
            & (pl.col("prob_offset").abs() >= float(accept["min_abs_offset_to_apply"]))
        ).alias("is_approved")
    ).with_columns(
        pl.when(pl.col("is_approved"))
        .then(pl.col("prob_offset"))
        .otherwise(pl.lit(float(guard["fallback_offset_when_rejected"])))
        .alias("prob_offset_final")
    )

    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    approved.write_parquet(OUT_PATH)

    summary = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy": policy,
        "rows_total": int(approved.height),
        "rows_approved": int(approved.filter(pl.col("is_approved")).height),
        "rows_rejected": int(approved.filter(~pl.col("is_approved")).height),
        "top_approved": approved.filter(pl.col("is_approved"))
        .with_columns(pl.col("prob_offset_final").abs().alias("abs_offset"))
        .sort("abs_offset", descending=True)
        .head(10)
        .to_dicts(),
        "output": str(OUT_PATH),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(f"wrote {OUT_SUMMARY}")
    print(summary)


if __name__ == "__main__":
    main()
