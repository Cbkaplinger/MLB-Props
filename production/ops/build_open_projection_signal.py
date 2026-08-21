"""Compare model projections to sportsbook open quotes (no dedupe by default).

This is an open-only signal view (not realized profitability). It quantifies:
- model vs book implied probability gap,
- where books disagree with model most,
- edge-shape buckets for calibration diagnostics.

Outputs:
- artifacts/odds_log/open_projection_quotes_raw.parquet
- artifacts/odds_log/open_projection_book_signal.parquet
- artifacts/odds_log/open_projection_edge_bins.parquet
- artifacts/odds_log/open_projection_signal_summary.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
OPEN_CSV = ROOT / "data" / "Odds-Open-Close-2025-2026" / "pitcher_strikeouts_early_open_2025_2026.csv"
PROJ_PATH = ROOT / "artifacts" / "projection_log" / "projections.parquet"
PROJ_BACKFILL_PATH = ROOT / "artifacts" / "projection_log" / "projections_backfill_open_window.parquet"
OUT_DIR = ROOT / "artifacts" / "odds_log"

RAW_OUT = OUT_DIR / "open_projection_quotes_raw.parquet"
BOOK_OUT = OUT_DIR / "open_projection_book_signal.parquet"
BIN_OUT = OUT_DIR / "open_projection_edge_bins.parquet"
SUMMARY_OUT = OUT_DIR / "open_projection_signal_summary.json"


def _american_to_implied_prob(price_expr: pl.Expr) -> pl.Expr:
    p = price_expr.cast(pl.Float64)
    return (
        pl.when(p > 0)
        .then(100.0 / (p + 100.0))
        .otherwise((-p) / ((-p) + 100.0))
    )


def _line_to_col_expr() -> pl.Expr:
    return (
        pl.col("line")
        .cast(pl.Float64)
        .round(1)
        .cast(pl.Utf8)
        .str.replace(".", "_", literal=True)
        .alias("line_stem")
    )


def _load_open_quotes() -> pl.DataFrame:
    if not OPEN_CSV.exists():
        raise FileNotFoundError(f"Missing open source: {OPEN_CSV}")
    return (
        pl.read_csv(OPEN_CSV, try_parse_dates=True, infer_schema_length=10000)
        .with_columns(
            pl.col("fetched_at").cast(pl.Utf8).str.to_datetime(time_zone="UTC", strict=False).alias("fetched_at_ts"),
            pl.col("commence_time").cast(pl.Utf8).str.to_datetime(time_zone="UTC", strict=False).alias("commence_time_ts"),
            pl.col("game_date").cast(pl.Utf8).str.to_date(strict=False).alias("game_date_d"),
            pl.col("pitcher_id").cast(pl.Int64).alias("pitcher_id_i"),
            pl.col("line").cast(pl.Float64),
            pl.col("over_odds").cast(pl.Float64),
            pl.col("under_odds").cast(pl.Float64),
            _line_to_col_expr(),
        )
        .with_columns(
            _american_to_implied_prob(pl.col("over_odds")).alias("p_over_implied"),
            _american_to_implied_prob(pl.col("under_odds")).alias("p_under_implied"),
        )
        .with_columns(
            (pl.col("p_over_implied") + pl.col("p_under_implied")).alias("two_way_prob_sum"),
            (pl.col("p_over_implied") + pl.col("p_under_implied") - 1.0).alias("vig"),
            ((pl.col("commence_time_ts") - pl.col("fetched_at_ts")).dt.total_seconds() / 3600.0).alias("hours_to_pitch"),
        )
        .with_columns(
            (pl.col("p_over_implied") / pl.col("two_way_prob_sum")).alias("p_over_novig"),
        )
    )


def _load_projection_board() -> pl.DataFrame:
    if not PROJ_PATH.exists():
        raise FileNotFoundError(f"Missing projections artifact: {PROJ_PATH}")
    proj = pl.read_parquet(PROJ_PATH)
    if PROJ_BACKFILL_PATH.exists():
        proj_backfill = pl.read_parquet(PROJ_BACKFILL_PATH)
        proj = pl.concat([proj, proj_backfill], how="diagonal_relaxed")
    required = {"game_date", "pitcher", "player_name"}
    missing = sorted(required - set(proj.columns))
    if missing:
        raise ValueError(f"Projection file missing required columns: {missing}")
    return proj.with_columns(
        pl.col("game_date").cast(pl.Date).alias("game_date_d"),
        pl.col("pitcher").cast(pl.Int64).alias("pitcher_id_i"),
    )


def _model_prob_expr() -> pl.Expr:
    # Prefer calibrated columns when available, fallback to raw p_over_*.
    return (
        pl.when(pl.col("line_stem") == "2_5")
        .then(pl.coalesce([pl.col("p_over_2_5_cal"), pl.col("p_over_2_5")]))
        .when(pl.col("line_stem") == "3_5")
        .then(pl.coalesce([pl.col("p_over_3_5_cal"), pl.col("p_over_3_5")]))
        .when(pl.col("line_stem") == "4_5")
        .then(pl.coalesce([pl.col("p_over_4_5_cal"), pl.col("p_over_4_5")]))
        .when(pl.col("line_stem") == "5_5")
        .then(pl.coalesce([pl.col("p_over_5_5_cal"), pl.col("p_over_5_5")]))
        .when(pl.col("line_stem") == "6_5")
        .then(pl.coalesce([pl.col("p_over_6_5_cal"), pl.col("p_over_6_5")]))
        .when(pl.col("line_stem") == "7_5")
        .then(pl.coalesce([pl.col("p_over_7_5_cal"), pl.col("p_over_7_5")]))
        .when(pl.col("line_stem") == "8_5")
        .then(pl.coalesce([pl.col("p_over_8_5_cal"), pl.col("p_over_8_5")]))
        .when(pl.col("line_stem") == "9_5")
        .then(pl.coalesce([pl.col("p_over_9_5_cal"), pl.col("p_over_9_5")]))
        .otherwise(None)
    )


def _build_joined(keep_deduped: bool) -> pl.DataFrame:
    opens = _load_open_quotes()
    if keep_deduped:
        opens = opens.unique(
            subset=[
                "game_date_d",
                "event_id",
                "pitcher_id_i",
                "bookmaker",
                "line",
                "fetched_at_ts",
            ],
            keep="last",
        )

    proj = _load_projection_board()
    joined = opens.join(
        proj,
        on=["game_date_d", "pitcher_id_i"],
        how="left",
        suffix="_proj",
    ).with_columns(
        _model_prob_expr().alias("p_model_over"),
    )
    joined = joined.with_columns(
        (pl.col("p_model_over") - pl.col("p_over_novig")).alias("edge_vs_open_novig"),
        (pl.col("p_model_over") - pl.col("p_over_implied")).alias("edge_vs_open_vigged"),
    )
    return joined


def _book_signal(joined: pl.DataFrame) -> pl.DataFrame:
    return (
        joined.filter(pl.col("p_model_over").is_not_null())
        .group_by(["bookmaker", "bookmaker_title"])
        .agg(
            pl.len().alias("n_quotes"),
            pl.col("game_date_d").n_unique().alias("n_days"),
            pl.col("pitcher_id_i").n_unique().alias("n_pitchers"),
            pl.col("edge_vs_open_novig").mean().alias("mean_edge_novig"),
            pl.col("edge_vs_open_novig").median().alias("median_edge_novig"),
            pl.col("edge_vs_open_novig").std().alias("std_edge_novig"),
            pl.col("vig").mean().alias("mean_vig"),
            pl.col("hours_to_pitch").median().alias("median_hours_to_pitch"),
        )
        .sort(["mean_edge_novig", "n_quotes"], descending=[True, True])
    )


def _edge_bins(joined: pl.DataFrame) -> pl.DataFrame:
    scoped = joined.filter(pl.col("p_model_over").is_not_null()).with_columns(
        pl.col("edge_vs_open_novig")
        .qcut(
            10,
            labels=[
                "q01",
                "q02",
                "q03",
                "q04",
                "q05",
                "q06",
                "q07",
                "q08",
                "q09",
                "q10",
            ],
            allow_duplicates=True,
        )
        .alias("edge_decile")
    )
    return (
        scoped.group_by("edge_decile")
        .agg(
            pl.len().alias("n_quotes"),
            pl.col("edge_vs_open_novig").mean().alias("mean_edge"),
            pl.col("edge_vs_open_novig").median().alias("median_edge"),
            pl.col("p_model_over").mean().alias("mean_model_prob"),
            pl.col("p_over_novig").mean().alias("mean_market_prob"),
            pl.col("vig").mean().alias("mean_vig"),
            pl.col("hours_to_pitch").median().alias("median_hours_to_pitch"),
        )
        .sort("mean_edge")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dedupe",
        action="store_true",
        help="Deduplicate open rows before join. Default keeps all snapshots.",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    joined = _build_joined(keep_deduped=bool(args.dedupe))
    matched = joined.filter(pl.col("p_model_over").is_not_null())
    book = _book_signal(joined)
    bins = _edge_bins(joined)
    open_date_range = joined.select(
        pl.col("game_date_d").min().cast(pl.Utf8).alias("open_min"),
        pl.col("game_date_d").max().cast(pl.Utf8).alias("open_max"),
    ).to_dicts()[0]
    proj = _load_projection_board()
    proj_date_range = proj.select(
        pl.col("game_date_d").min().cast(pl.Utf8).alias("proj_min"),
        pl.col("game_date_d").max().cast(pl.Utf8).alias("proj_max"),
    ).to_dicts()[0]

    joined.write_parquet(RAW_OUT)
    book.write_parquet(BOOK_OUT)
    bins.write_parquet(BIN_OUT)

    summary = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {"open_csv": str(OPEN_CSV), "projections": str(PROJ_PATH)},
        "config": {"dedupe": bool(args.dedupe)},
        "rows": {
            "open_rows_total": joined.height,
            "projection_matched_rows": matched.height,
            "unmatched_rows": joined.height - matched.height,
        },
        "open_date_range": open_date_range,
        "projection_date_range": proj_date_range,
        "notes": [
            "No-dedupe mode retains every snapshot row for calibration/shape studies.",
            "If projection_matched_rows == 0, historical projections need backfill for open-date overlap.",
        ],
    }
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"wrote {RAW_OUT}")
    print(f"wrote {BOOK_OUT}")
    print(f"wrote {BIN_OUT}")
    print(f"wrote {SUMMARY_OUT}")
    print(summary)


if __name__ == "__main__":
    main()
