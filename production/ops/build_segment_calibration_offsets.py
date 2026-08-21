"""Build segment-aware probability correction offsets for board scoring.

Learns offsets from open-snapshot rows with realized outcomes using:
  (line, over_price_bucket, maturity_bucket)

Output is consumed by src/Python/odds_board.py before edge/floor policy.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
ODDS_DIR = ROOT / "artifacts" / "odds_log"
INPUT_ROWS = ODDS_DIR / "open_proj_calibration_rows.parquet"
OUT_SEGMENTED = ODDS_DIR / "line_price_correction_table_segmented.parquet"
OUT_SUMMARY = ODDS_DIR / "line_price_correction_table_segmented_summary.json"


def _price_bucket(price_expr: pl.Expr) -> pl.Expr:
    p = price_expr.cast(pl.Float64)
    return (
        pl.when(p <= -170)
        .then(pl.lit("fav_le_-170"))
        .when(p <= -140)
        .then(pl.lit("fav_-169_to_-140"))
        .when(p <= -115)
        .then(pl.lit("fav_-139_to_-115"))
        .when(p <= -105)
        .then(pl.lit("coin_-114_to_-105"))
        .when(p <= 105)
        .then(pl.lit("coin_-104_to_+105"))
        .when(p <= 130)
        .then(pl.lit("dog_+106_to_+130"))
        .when(p <= 160)
        .then(pl.lit("dog_+131_to_+160"))
        .otherwise(pl.lit("dog_gt_+160"))
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-n", type=int, default=60, help="Minimum rows per segment.")
    parser.add_argument("--shrink-prior-n", type=float, default=200.0, help="Empirical-Bayes shrinkage weight.")
    parser.add_argument("--offset-cap", type=float, default=0.08, help="Absolute cap for correction offset.")
    args = parser.parse_args()

    if not INPUT_ROWS.exists():
        raise SystemExit(f"Missing input rows: {INPUT_ROWS}")

    rows = pl.read_parquet(INPUT_ROWS)
    needed = {"line", "over_odds", "p_model_over", "actual_over", "maturity_bucket"}
    missing = sorted(needed - set(rows.columns))
    if missing:
        raise SystemExit(f"Missing required columns in {INPUT_ROWS}: {missing}")

    base = (
        rows.filter(pl.col("actual_over").is_not_null() & pl.col("p_model_over").is_not_null())
        .with_columns(
            pl.col("line").cast(pl.Float64),
            _price_bucket(pl.col("over_odds")).alias("over_price_bucket"),
            pl.col("maturity_bucket").cast(pl.Utf8),
            pl.col("p_model_over").cast(pl.Float64),
            pl.col("actual_over").cast(pl.Float64),
        )
    )
    if base.is_empty():
        raise SystemExit("No eligible rows for correction fit.")

    global_stats = base.select(
        pl.len().alias("n_global"),
        pl.col("p_model_over").mean().alias("p_mean_global"),
        pl.col("actual_over").mean().alias("y_mean_global"),
    ).to_dicts()[0]
    p_mean_global = float(global_stats["p_mean_global"])
    y_mean_global = float(global_stats["y_mean_global"])
    gap_global = y_mean_global - p_mean_global

    grouped = (
        base.group_by(["line", "over_price_bucket", "maturity_bucket"])
        .agg(
            pl.len().alias("n"),
            pl.col("p_model_over").mean().alias("p_mean"),
            pl.col("actual_over").mean().alias("y_mean"),
        )
        .with_columns((pl.col("y_mean") - pl.col("p_mean")).alias("raw_gap"))
        .filter(pl.col("n") >= int(args.min_n))
    )

    if grouped.is_empty():
        raise SystemExit("No segments survived min-n filter; lower --min-n.")

    prior_n = float(args.shrink_prior_n)
    cap = float(args.offset_cap)
    corrected = grouped.with_columns(
        (
            ((pl.col("raw_gap") * pl.col("n")) + (pl.lit(gap_global) * prior_n))
            / (pl.col("n") + prior_n)
        ).alias("prob_offset_raw")
    ).with_columns(
        pl.col("prob_offset_raw").clip(-cap, cap).alias("prob_offset")
    )

    # Add maturity-agnostic fallback rows (wildcard) for robust runtime lookup.
    fallback = (
        base.group_by(["line", "over_price_bucket"])
        .agg(
            pl.len().alias("n"),
            pl.col("p_model_over").mean().alias("p_mean"),
            pl.col("actual_over").mean().alias("y_mean"),
        )
        .with_columns((pl.col("y_mean") - pl.col("p_mean")).alias("raw_gap"))
        .filter(pl.col("n") >= int(args.min_n))
        .with_columns(
            (
                ((pl.col("raw_gap") * pl.col("n")) + (pl.lit(gap_global) * prior_n))
                / (pl.col("n") + prior_n)
            ).alias("prob_offset_raw"),
            pl.lit("*").alias("maturity_bucket"),
        )
        .with_columns(pl.col("prob_offset_raw").clip(-cap, cap).alias("prob_offset"))
        .select(corrected.columns)
    )

    out = pl.concat([corrected, fallback], how="diagonal_relaxed").sort(
        ["line", "over_price_bucket", "maturity_bucket"]
    )
    OUT_SEGMENTED.parent.mkdir(parents=True, exist_ok=True)
    out.write_parquet(OUT_SEGMENTED)

    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_rows": str(INPUT_ROWS),
        "output_table": str(OUT_SEGMENTED),
        "config": {
            "min_n": int(args.min_n),
            "shrink_prior_n": prior_n,
            "offset_cap": cap,
        },
        "global": {
            "n": int(global_stats["n_global"]),
            "p_mean": p_mean_global,
            "y_mean": y_mean_global,
            "gap": gap_global,
        },
        "segments": {
            "exact_segment_rows": int(corrected.height),
            "fallback_rows": int(fallback.height),
            "total_rows": int(out.height),
        },
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {OUT_SEGMENTED}")
    print(f"wrote {OUT_SUMMARY}")
    print(summary)


if __name__ == "__main__":
    main()

