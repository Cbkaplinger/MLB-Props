"""Build segment-level deployment matrix with ON/OFF reason codes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
ODDS_DIR = ROOT / "artifacts" / "odds_log"

APPROVED_PATH = ODDS_DIR / "line_price_correction_table_approved.parquet"
EXEC_PATH = ODDS_DIR / "open_model_execution_sensitivity.parquet"
SCORING_LINE_PATH = ODDS_DIR / "prob_scoring_by_line.parquet"
DRIFT_PATH = ODDS_DIR / "open_model_regime_drift_flips.parquet"

OUT_PATH = ODDS_DIR / "calibration_deploy_matrix.parquet"
OUT_SUMMARY = ODDS_DIR / "calibration_deploy_matrix_summary.json"

RECENT_FLIP_SPIKE_THRESHOLD = 0.45
RECENT_FLIP_MIN_DAYS = 7


def main() -> None:
    for p in (APPROVED_PATH, EXEC_PATH, SCORING_LINE_PATH, DRIFT_PATH):
        if not p.exists():
            raise FileNotFoundError(f"Missing dependency: {p}")

    appr = pl.read_parquet(APPROVED_PATH)
    execs = pl.read_parquet(EXEC_PATH).select(
        "line", "maturity_bucket", "brier_gain_from_correction", "n"
    ).rename({"n": "n_exec"})
    line_score = pl.read_parquet(SCORING_LINE_PATH).select(
        "line", "n", "brier_model", "brier_market_novig", "ece_model", "ece_market_novig"
    ).rename({"n": "n_line"})
    drift = pl.read_parquet(DRIFT_PATH).select(
        "line",
        "over_price_bucket",
        "maturity_bucket",
        "n_days_recent_14d",
        "flip_rate_recent_14d",
    )

    merged = appr.join(
        execs, on=["line", "maturity_bucket"], how="left"
    ).join(
        line_score, on=["line"], how="left"
    ).join(
        drift, on=["line", "over_price_bucket", "maturity_bucket"], how="left"
    )

    merged = merged.with_columns(
        pl.when(pl.col("is_approved"))
        .then(pl.lit("ON"))
        .otherwise(pl.lit("OFF"))
        .alias("deploy_state"),
        pl.when(pl.col("is_approved"))
        .then(pl.lit("approved_by_policy"))
        .when(pl.col("n") < 250)
        .then(pl.lit("low_segment_n"))
        .when(
            (pl.col("n_days_recent_14d").fill_null(0) >= RECENT_FLIP_MIN_DAYS)
            & (pl.col("flip_rate_recent_14d").fill_null(0.0) >= RECENT_FLIP_SPIKE_THRESHOLD)
        )
        .then(pl.lit("recent_drift_flip_spike"))
        .when(pl.col("flip_rate") > 0.35)
        .then(pl.lit("high_flip_rate"))
        .when(pl.col("brier_gain_from_correction").is_null())
        .then(pl.lit("missing_exec_sensitivity"))
        .when(pl.col("brier_gain_from_correction") < 0)
        .then(pl.lit("negative_exec_gain"))
        .otherwise(pl.lit("policy_rejected_other"))
        .alias("reason_code"),
    ).select(
        "line",
        "over_price_bucket",
        "maturity_bucket",
        "n",
        "flip_rate",
        "n_days_recent_14d",
        "flip_rate_recent_14d",
        "prob_offset_final",
        "is_approved",
        "deploy_state",
        "reason_code",
        "brier_gain_from_correction",
        "brier_model",
        "brier_market_novig",
        "ece_model",
        "ece_market_novig",
    ).sort(["line", "over_price_bucket", "maturity_bucket"])

    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    merged.write_parquet(OUT_PATH)

    summary = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows_total": int(merged.height),
        "rows_on": int(merged.filter(pl.col("deploy_state") == "ON").height),
        "rows_off": int(merged.filter(pl.col("deploy_state") == "OFF").height),
        "recent_flip_spike_threshold": RECENT_FLIP_SPIKE_THRESHOLD,
        "recent_flip_min_days": RECENT_FLIP_MIN_DAYS,
        "off_reason_counts": merged.filter(pl.col("deploy_state") == "OFF")
        .group_by("reason_code")
        .agg(pl.len().alias("n"))
        .sort("n", descending=True)
        .to_dicts(),
        "output": str(OUT_PATH),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(f"wrote {OUT_SUMMARY}")
    print(summary)


if __name__ == "__main__":
    main()
