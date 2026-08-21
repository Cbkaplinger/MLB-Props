"""Backfill historical projections for dates covered by open market snapshots.

Purpose:
- Build model projections on the open-data date range so open-vs-model
  comparisons have overlap.
- Keep holdout hygiene: uses frozen model artifacts; does not retrain.

Outputs:
- artifacts/projection_log/projections_backfill_open_window.parquet
- artifacts/projection_log/projections_backfill_open_window_summary.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]

OPEN_K_CSV = ROOT / "data" / "Odds-Open-Close-2025-2026" / "pitcher_strikeouts_early_open_2025_2026.csv"
PITCHER_TRAINING_PATH = ROOT / "data" / "processed" / "pitcher_training.parquet"
OUT_DIR = ROOT / "artifacts" / "projection_log"
OUT_PATH = OUT_DIR / "projections_backfill_open_window.parquet"
SUMMARY_PATH = OUT_DIR / "projections_backfill_open_window_summary.json"


def main() -> None:
    if not OPEN_K_CSV.exists():
        raise FileNotFoundError(f"Missing open snapshot source: {OPEN_K_CSV}")
    if not PITCHER_TRAINING_PATH.exists():
        raise FileNotFoundError(
            f"Missing pitcher training frame: {PITCHER_TRAINING_PATH}. "
            "Run production/ops/refresh_features.py first."
        )

    # Local imports keep startup lean and avoid accidental side effects.
    from Python.count_layer import PROJECTION_K_LINES
    from Python.live_assembly import daily_projection_board, score_frame

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    open_dates = (
        pl.read_csv(OPEN_K_CSV, infer_schema_length=10000)
        .select(pl.col("game_date").cast(pl.Utf8).str.to_date(strict=False).alias("game_date"))
        .drop_nulls()
        .unique()
        .sort("game_date")
    )
    if open_dates.is_empty():
        raise SystemExit("No valid game_date values found in open snapshot CSV.")

    train = pl.read_parquet(PITCHER_TRAINING_PATH).with_columns(
        pl.col("game_date").cast(pl.Date)
    )
    scoped = train.join(open_dates, on="game_date", how="inner")
    if scoped.is_empty():
        raise SystemExit(
            "No pitcher_training rows overlap open snapshot dates. "
            "Check training frame coverage vs open CSV dates."
        )

    scored_pd, report = score_frame(scoped.to_pandas(), lines=PROJECTION_K_LINES)
    board = daily_projection_board(scored_pd, lines=PROJECTION_K_LINES, preferred_only=False)

    logged_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = board.with_columns(
        pl.lit(logged_at).alias("logged_at_utc"),
        pl.lit(True).alias("is_backfill_open_window"),
        pl.lit("pitcher_training_historical").alias("backfill_source"),
    )
    # One model row per (date, pitcher) for stable joins.
    out = out.unique(subset=["game_date", "pitcher"], keep="last")
    out.write_parquet(OUT_PATH)

    summary = {
        "captured_utc": logged_at,
        "inputs": {
            "open_csv": str(OPEN_K_CSV),
            "pitcher_training": str(PITCHER_TRAINING_PATH),
        },
        "rows": {
            "open_unique_dates": int(open_dates.height),
            "training_rows_scoped": int(scoped.height),
            "projections_backfilled": int(out.height),
        },
        "date_range": out.select(
            pl.col("game_date").min().cast(pl.Utf8).alias("min_game_date"),
            pl.col("game_date").max().cast(pl.Utf8).alias("max_game_date"),
        ).to_dicts()[0],
        "report": {
            "mean_expected_K": report.get("mean_expected_K"),
            "calibration_applied": report.get("calibration_applied"),
            "calibration_version": report.get("calibration_version"),
        },
        "output": str(OUT_PATH),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"wrote {OUT_PATH}")
    print(f"wrote {SUMMARY_PATH}")
    print(summary)


if __name__ == "__main__":
    main()
