"""Build a conservative line/price/maturity probability correction table.

Purpose:
- Convert empirical calibration gaps into bounded probability offsets.
- Provide a clean artifact to adjust model probabilities before fair pricing.

Input:
- artifacts/odds_log/line_price_calibration_grid.parquet

Outputs:
- artifacts/odds_log/line_price_correction_table.parquet
- artifacts/odds_log/line_price_correction_table_latest.csv
- artifacts/odds_log/line_price_correction_summary.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
ODDS_DIR = ROOT / "artifacts" / "odds_log"
GRID_PATH = ODDS_DIR / "line_price_calibration_grid.parquet"

OUT_PATH = ODDS_DIR / "line_price_correction_table.parquet"
OUT_CSV = ODDS_DIR / "line_price_correction_table_latest.csv"
OUT_SUMMARY = ODDS_DIR / "line_price_correction_summary.json"

MIN_N = 250
MAX_ABS_OFFSET = 0.06
SHRINK_REF_N = 800.0


def main() -> None:
    if not GRID_PATH.exists():
        raise FileNotFoundError(
            f"Missing {GRID_PATH}. Run production/ops/build_line_price_calibration_gap.py first."
        )

    grid = pl.read_parquet(GRID_PATH)
    eligible = grid.filter(pl.col("n") >= MIN_N).with_columns(
        # Desired correction = push model toward realized rate.
        (-pl.col("model_minus_actual")).alias("raw_offset"),
    )
    # Shrink small-N segments and cap extremes.
    table = eligible.with_columns(
        (pl.col("n") / (pl.col("n") + SHRINK_REF_N)).alias("shrink_w"),
    ).with_columns(
        (pl.col("raw_offset") * pl.col("shrink_w"))
        .clip(lower_bound=-MAX_ABS_OFFSET, upper_bound=MAX_ABS_OFFSET)
        .alias("prob_offset"),
    ).with_columns(
        pl.when(pl.col("prob_offset") > 0).then(pl.lit("raise_prob")).otherwise(
            pl.lit("lower_prob")
        ).alias("direction")
    ).select(
        "line",
        "over_price_bucket",
        "maturity_bucket",
        "n",
        "mean_model_prob",
        "hit_rate",
        "model_minus_actual",
        "raw_offset",
        "shrink_w",
        "prob_offset",
        "direction",
        "delta_brier_model_minus_market",
    ).sort(["line", "over_price_bucket", "maturity_bucket"])

    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    table.write_parquet(OUT_PATH)
    table.write_csv(OUT_CSV)

    summary = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "parameters": {
            "min_n": MIN_N,
            "max_abs_offset": MAX_ABS_OFFSET,
            "shrink_ref_n": SHRINK_REF_N,
        },
        "rows": {
            "eligible_segments": int(table.height),
            "raise_prob_segments": int(table.filter(pl.col("direction") == "raise_prob").height),
            "lower_prob_segments": int(table.filter(pl.col("direction") == "lower_prob").height),
        },
        "largest_adjustments": table.with_columns(
            pl.col("prob_offset").abs().alias("abs_offset")
        ).sort("abs_offset", descending=True).head(12).to_dicts(),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"wrote {OUT_PATH}")
    print(f"wrote {OUT_CSV}")
    print(f"wrote {OUT_SUMMARY}")
    print(summary)


if __name__ == "__main__":
    main()
