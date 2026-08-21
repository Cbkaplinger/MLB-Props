"""Build open-vs-projection calibration research artifacts.

Uses open snapshots matched to projections, then joins realized strikeouts from
pitcher_games so calibration can be studied without close-line data.

Outputs:
- artifacts/odds_log/open_proj_calibration_rows.parquet
- artifacts/odds_log/open_proj_calibration_bins.parquet
- artifacts/odds_log/open_proj_calibration_by_book.parquet
- artifacts/odds_log/open_proj_calibration_by_line.parquet
- artifacts/odds_log/open_proj_calibration_drift_daily.parquet
- artifacts/odds_log/open_proj_calibration_summary.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
OPEN_RAW_PATH = ROOT / "artifacts" / "odds_log" / "open_projection_quotes_raw.parquet"
PITCHER_GAMES_PATH = ROOT / "data" / "processed" / "pitcher_games.parquet"

OUT_DIR = ROOT / "artifacts" / "odds_log"
ROWS_PATH = OUT_DIR / "open_proj_calibration_rows.parquet"
BINS_PATH = OUT_DIR / "open_proj_calibration_bins.parquet"
BOOK_PATH = OUT_DIR / "open_proj_calibration_by_book.parquet"
LINE_PATH = OUT_DIR / "open_proj_calibration_by_line.parquet"
DRIFT_PATH = OUT_DIR / "open_proj_calibration_drift_daily.parquet"
SUMMARY_PATH = OUT_DIR / "open_proj_calibration_summary.json"


def _load_rows() -> pl.DataFrame:
    if not OPEN_RAW_PATH.exists():
        raise FileNotFoundError(
            f"Missing open-projection panel: {OPEN_RAW_PATH}. "
            "Run production/ops/build_open_projection_signal.py first."
        )
    if not PITCHER_GAMES_PATH.exists():
        raise FileNotFoundError(f"Missing pitcher outcomes: {PITCHER_GAMES_PATH}")

    raw = pl.read_parquet(OPEN_RAW_PATH).with_columns(
        pl.col("game_date_d").cast(pl.Date),
        pl.col("pitcher_id_i").cast(pl.Int64),
        pl.col("line").cast(pl.Float64),
    )
    # Only rows where model projection is available.
    raw = raw.filter(pl.col("p_model_over").is_not_null())

    games = pl.read_parquet(PITCHER_GAMES_PATH).select(
        pl.col("game_date").cast(pl.Date).alias("game_date_d"),
        pl.col("pitcher").cast(pl.Int64).alias("pitcher_id_i"),
        pl.col("season").cast(pl.Int32).alias("season_i"),
        pl.col("K").cast(pl.Float64).alias("actual_k"),
    )
    games = games.sort(["pitcher_id_i", "season_i", "game_date_d"]).with_columns(
        (pl.col("game_date_d").cum_count().over(["pitcher_id_i", "season_i"]) - 1).alias(
            "prior_starts_in_season"
        )
    )

    joined = raw.join(games, on=["game_date_d", "pitcher_id_i"], how="left")
    joined = joined.with_columns(
        (pl.col("actual_k") > pl.col("line")).cast(pl.Int8).alias("actual_over"),
        pl.when(pl.col("prior_starts_in_season").is_null())
        .then(pl.lit("unknown"))
        .when(pl.col("prior_starts_in_season") < 10)
        .then(pl.lit("early_lt10"))
        .when(pl.col("prior_starts_in_season") < 20)
        .then(pl.lit("mid_10_19"))
        .otherwise(pl.lit("mature_20_plus"))
        .alias("maturity_bucket"),
        pl.when(pl.col("hours_to_pitch") < 8.0)
        .then(pl.lit("lt8h"))
        .when(pl.col("hours_to_pitch") < 10.0)
        .then(pl.lit("8to10h"))
        .when(pl.col("hours_to_pitch") < 14.0)
        .then(pl.lit("10to14h"))
        .otherwise(pl.lit("14h_plus"))
        .alias("hours_bucket"),
        pl.col("p_model_over")
        .qcut(
            10,
            labels=["q01", "q02", "q03", "q04", "q05", "q06", "q07", "q08", "q09", "q10"],
            allow_duplicates=True,
        )
        .alias("model_prob_decile"),
    ).with_columns(
        (pl.col("p_model_over") - pl.col("actual_over").cast(pl.Float64)).alias("model_residual")
    )
    return joined


def _calibration_bins(rows: pl.DataFrame) -> pl.DataFrame:
    scoped = rows.filter(pl.col("actual_over").is_not_null())
    grouped = (
        scoped.group_by(["maturity_bucket", "hours_bucket", "model_prob_decile"])
        .agg(
            pl.len().alias("n"),
            pl.col("p_model_over").mean().alias("mean_model_prob"),
            pl.col("actual_over").mean().alias("hit_rate"),
            (pl.col("p_model_over") - pl.col("actual_over").cast(pl.Float64))
            .pow(2)
            .mean()
            .alias("brier"),
            pl.col("edge_vs_open_novig").mean().alias("mean_edge_vs_open"),
            pl.col("vig").mean().alias("mean_vig"),
        )
        .with_columns(
            (pl.col("mean_model_prob") - pl.col("hit_rate")).alias("calibration_gap"),
        )
        .with_columns(pl.col("calibration_gap").abs().alias("abs_calibration_gap"))
    )
    ece = (
        grouped.group_by(["maturity_bucket", "hours_bucket"])
        .agg(
            pl.col("n").sum().alias("n_total"),
            ((pl.col("n") * pl.col("abs_calibration_gap")).sum() / pl.col("n").sum()).alias(
                "ece_weighted"
            ),
        )
        .with_columns(
            pl.when(pl.col("n_total") >= 100)
            .then(pl.col("ece_weighted"))
            .otherwise(None)
            .alias("ece_weighted_stable")
        )
    )
    return grouped.join(ece, on=["maturity_bucket", "hours_bucket"], how="left").sort(
        ["maturity_bucket", "hours_bucket", "model_prob_decile"]
    )


def _by_book(rows: pl.DataFrame) -> pl.DataFrame:
    scoped = rows.filter(pl.col("actual_over").is_not_null())
    return (
        scoped.group_by(["bookmaker", "bookmaker_title", "maturity_bucket"])
        .agg(
            pl.len().alias("n"),
            pl.col("actual_over").mean().alias("hit_rate"),
            pl.col("p_model_over").mean().alias("mean_model_prob"),
            pl.col("model_residual").mean().alias("mean_residual"),
            pl.col("model_residual").abs().mean().alias("mae_prob"),
            (pl.col("p_model_over") - pl.col("actual_over").cast(pl.Float64))
            .pow(2)
            .mean()
            .alias("brier"),
            pl.col("edge_vs_open_novig").mean().alias("mean_edge_vs_open"),
            pl.col("vig").mean().alias("mean_vig"),
        )
        .with_columns((pl.col("mean_model_prob") - pl.col("hit_rate")).alias("calibration_gap"))
        .sort(["n", "mae_prob"], descending=[True, False])
    )


def _by_line(rows: pl.DataFrame) -> pl.DataFrame:
    scoped = rows.filter(pl.col("actual_over").is_not_null())
    return (
        scoped.group_by(["line", "maturity_bucket"])
        .agg(
            pl.len().alias("n"),
            pl.col("actual_over").mean().alias("hit_rate"),
            pl.col("p_model_over").mean().alias("mean_model_prob"),
            pl.col("model_residual").abs().mean().alias("mae_prob"),
            (pl.col("p_model_over") - pl.col("actual_over").cast(pl.Float64))
            .pow(2)
            .mean()
            .alias("brier"),
            pl.col("edge_vs_open_novig").mean().alias("mean_edge_vs_open"),
        )
        .with_columns((pl.col("mean_model_prob") - pl.col("hit_rate")).alias("calibration_gap"))
        .sort(["line", "maturity_bucket"])
    )


def _daily_drift(rows: pl.DataFrame) -> pl.DataFrame:
    scoped = rows.filter(pl.col("actual_over").is_not_null())
    return (
        scoped.group_by(["game_date_d", "bookmaker"])
        .agg(
            pl.len().alias("n"),
            pl.col("model_residual").mean().alias("mean_residual"),
            pl.col("model_residual").abs().mean().alias("mae_prob"),
            pl.col("edge_vs_open_novig").mean().alias("mean_edge_vs_open"),
            pl.col("actual_over").mean().alias("hit_rate"),
            pl.col("p_model_over").mean().alias("mean_model_prob"),
        )
        .with_columns((pl.col("mean_model_prob") - pl.col("hit_rate")).alias("calibration_gap"))
        .sort(["game_date_d", "bookmaker"])
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = _load_rows()
    bins = _calibration_bins(rows)
    by_book = _by_book(rows)
    by_line = _by_line(rows)
    drift = _daily_drift(rows)

    rows.write_parquet(ROWS_PATH)
    bins.write_parquet(BINS_PATH)
    by_book.write_parquet(BOOK_PATH)
    by_line.write_parquet(LINE_PATH)
    drift.write_parquet(DRIFT_PATH)

    rows_scored = rows.filter(pl.col("actual_over").is_not_null())
    summary = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {"open_projection_rows": str(OPEN_RAW_PATH), "pitcher_games": str(PITCHER_GAMES_PATH)},
        "rows": {
            "matched_projection_quotes": int(rows.height),
            "rows_with_outcomes": int(rows_scored.height),
            "outcome_coverage_rate": float(rows_scored.height / max(1, rows.height)),
        },
        "date_range": rows_scored.select(
            pl.col("game_date_d").min().cast(pl.Utf8).alias("min_game_date"),
            pl.col("game_date_d").max().cast(pl.Utf8).alias("max_game_date"),
        ).to_dicts()[0]
        if rows_scored.height
        else None,
        "global_metrics": rows_scored.select(
            pl.col("model_residual").abs().mean().alias("mae_prob"),
            ((pl.col("p_model_over") - pl.col("actual_over").cast(pl.Float64)).pow(2).mean()).alias("brier"),
            (pl.col("p_model_over").mean() - pl.col("actual_over").mean()).alias("calibration_gap"),
            pl.col("edge_vs_open_novig").mean().alias("mean_edge_vs_open"),
        ).to_dicts()[0]
        if rows_scored.height
        else None,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"wrote {ROWS_PATH}")
    print(f"wrote {BINS_PATH}")
    print(f"wrote {BOOK_PATH}")
    print(f"wrote {LINE_PATH}")
    print(f"wrote {DRIFT_PATH}")
    print(f"wrote {SUMMARY_PATH}")
    print(summary)


if __name__ == "__main__":
    main()
