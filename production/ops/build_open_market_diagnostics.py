"""Build open-only market diagnostics from preserved historical snapshot CSVs.

Outputs:
- artifacts/odds_log/open_quotes_canonical.parquet
- artifacts/odds_log/open_book_staleness_ranking.parquet
- artifacts/odds_log/open_dispersion_consensus.parquet
- artifacts/odds_log/open_capture_quality.parquet
- artifacts/odds_log/open_difficulty_buckets.parquet
- artifacts/odds_log/open_market_diagnostics_summary.json

This script intentionally does not require close lines. It standardizes and
deduplicates open quotes now so CLV backfill can be added later when closes are
available.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "Odds-Open-Close-2025-2026"
OUT_DIR = ROOT / "artifacts" / "odds_log"

K_SOURCE = DATA_DIR / "pitcher_strikeouts_early_open_2025_2026.csv"
OUTS_SOURCE = DATA_DIR / "pitcher_outs_open_2025_2026.csv"

CANONICAL_PATH = OUT_DIR / "open_quotes_canonical.parquet"
BOOK_PATH = OUT_DIR / "open_book_staleness_ranking.parquet"
DISPERSION_PATH = OUT_DIR / "open_dispersion_consensus.parquet"
CAPTURE_PATH = OUT_DIR / "open_capture_quality.parquet"
DIFFICULTY_PATH = OUT_DIR / "open_difficulty_buckets.parquet"
SUMMARY_PATH = OUT_DIR / "open_market_diagnostics_summary.json"


def _american_to_implied_prob(price_expr: pl.Expr) -> pl.Expr:
    p = price_expr.cast(pl.Float64)
    return (
        pl.when(p > 0)
        .then(100.0 / (p + 100.0))
        .otherwise((-p) / ((-p) + 100.0))
    )


def _load_one(path: Path, market_label: str) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing source CSV: {path}")
    df = pl.read_csv(path, try_parse_dates=True, infer_schema_length=10000)
    required = {
        "fetched_at",
        "event_id",
        "commence_time",
        "bookmaker",
        "bookmaker_title",
        "bookmaker_last_update",
        "api_market",
        "line",
        "over_odds",
        "under_odds",
        "game_date",
        "pitcher_id",
        "pitcher_name",
        "snapshot_type",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{path.name} missing required columns: {missing}")

    return (
        df.with_columns(
            pl.col("fetched_at")
            .cast(pl.Utf8)
            .str.to_datetime(time_zone="UTC", strict=False)
            .alias("fetched_at_ts"),
            pl.col("bookmaker_last_update")
            .cast(pl.Utf8)
            .str.to_datetime(time_zone="UTC", strict=False)
            .alias("bookmaker_last_update_ts"),
            pl.col("commence_time")
            .cast(pl.Utf8)
            .str.to_datetime(time_zone="UTC", strict=False)
            .alias("commence_time_ts"),
            pl.col("requested_snapshot")
            .cast(pl.Utf8)
            .str.to_datetime(time_zone="UTC", strict=False)
            .alias("requested_snapshot_ts"),
            pl.col("historical_snapshot")
            .cast(pl.Utf8)
            .str.to_datetime(time_zone="UTC", strict=False)
            .alias("historical_snapshot_ts"),
            pl.col("game_date").cast(pl.Utf8).str.to_date(strict=False).alias("game_date_d"),
            pl.col("pitcher_id").cast(pl.Int64),
            pl.col("line").cast(pl.Float64),
            pl.col("over_odds").cast(pl.Float64),
            pl.col("under_odds").cast(pl.Float64),
            pl.lit(market_label).alias("market_label"),
        )
        .with_columns(
            _american_to_implied_prob(pl.col("over_odds")).alias("p_over_implied"),
            _american_to_implied_prob(pl.col("under_odds")).alias("p_under_implied"),
        )
        .with_columns(
            (pl.col("p_over_implied") + pl.col("p_under_implied") - 1.0).alias("vig"),
            (
                (pl.col("fetched_at_ts") - pl.col("bookmaker_last_update_ts"))
                .dt.total_seconds()
                / 60.0
            ).alias("minutes_stale_at_fetch"),
            (
                (pl.col("commence_time_ts") - pl.col("fetched_at_ts"))
                .dt.total_seconds()
                / 3600.0
            ).alias("hours_to_first_pitch"),
            (
                (pl.col("requested_snapshot_ts") - pl.col("fetched_at_ts"))
                .dt.total_seconds()
                / 60.0
            ).alias("requested_minus_fetch_minutes"),
        )
    )


def _canonical_quotes() -> pl.DataFrame:
    raw = pl.concat(
        [_load_one(K_SOURCE, "pitcher_strikeouts"), _load_one(OUTS_SOURCE, "pitcher_outs")],
        how="diagonal_relaxed",
    )
    if raw.is_empty():
        return raw

    # Preserve latest fetch per unique quote key.
    key = [
        "game_date_d",
        "event_id",
        "pitcher_id",
        "bookmaker",
        "api_market",
        "line",
        "snapshot_type",
        "fetched_at_ts",
    ]
    return (
        raw.sort("fetched_at_ts")
        .unique(subset=key, keep="last")
        .with_columns(
            pl.concat_str(
                [
                    pl.col("event_id").cast(pl.Utf8),
                    pl.col("pitcher_id").cast(pl.Utf8),
                    pl.col("bookmaker").cast(pl.Utf8),
                    pl.col("api_market").cast(pl.Utf8),
                    pl.col("line").round(3).cast(pl.Utf8),
                    pl.col("fetched_at_ts").cast(pl.Utf8),
                ],
                separator="|",
            ).alias("open_quote_key")
        )
    )


def _book_ranking(canonical: pl.DataFrame) -> pl.DataFrame:
    return (
        canonical.group_by(["market_label", "bookmaker", "bookmaker_title"])
        .agg(
            pl.len().alias("n_quotes"),
            pl.col("event_id").n_unique().alias("n_events"),
            pl.col("pitcher_id").n_unique().alias("n_pitchers"),
            pl.col("minutes_stale_at_fetch").median().alias("median_staleness_min"),
            pl.col("minutes_stale_at_fetch").quantile(0.9).alias("p90_staleness_min"),
            pl.col("vig").mean().alias("mean_vig"),
            pl.col("vig").quantile(0.9).alias("p90_vig"),
            pl.col("hours_to_first_pitch").median().alias("median_hours_to_pitch"),
        )
        .with_columns(
            (
                pl.col("n_quotes")
                / pl.max_horizontal(pl.col("n_quotes").max(), pl.lit(1))
            ).alias("coverage_score"),
            (
                1.0
                / (
                    1.0
                    + pl.col("median_staleness_min")
                    .fill_null(999.0)
                    .clip(lower_bound=0.0)
                )
            ).alias("freshness_score"),
            (
                1.0
                / (1.0 + (pl.col("mean_vig").fill_null(1.0).clip(lower_bound=0.0) * 100.0))
            ).alias("price_quality_score"),
        )
        .with_columns(
            (
                0.45 * pl.col("coverage_score")
                + 0.35 * pl.col("freshness_score")
                + 0.20 * pl.col("price_quality_score")
            ).alias("open_book_score")
        )
        .sort(["market_label", "open_book_score"], descending=[False, True])
    )


def _dispersion(canonical: pl.DataFrame) -> pl.DataFrame:
    key = ["market_label", "game_date_d", "event_id", "pitcher_id", "api_market", "line"]
    return (
        canonical.group_by(key)
        .agg(
            pl.len().alias("n_books"),
            pl.col("bookmaker").n_unique().alias("n_unique_books"),
            pl.col("over_odds").mean().alias("over_odds_mean"),
            pl.col("over_odds").std().alias("over_odds_std"),
            (pl.col("over_odds").max() - pl.col("over_odds").min()).alias("over_odds_range"),
            pl.col("under_odds").mean().alias("under_odds_mean"),
            pl.col("under_odds").std().alias("under_odds_std"),
            (pl.col("under_odds").max() - pl.col("under_odds").min()).alias("under_odds_range"),
            pl.col("vig").mean().alias("mean_vig"),
            pl.col("vig").std().alias("vig_std"),
            pl.col("hours_to_first_pitch").median().alias("median_hours_to_pitch"),
        )
        .with_columns(
            (
                (pl.col("over_odds_std").fill_null(0.0) + pl.col("under_odds_std").fill_null(0.0))
                / 2.0
            ).alias("odds_dispersion_std"),
            (
                (pl.col("over_odds_range").fill_null(0.0) + pl.col("under_odds_range").fill_null(0.0))
                / 2.0
            ).alias("odds_dispersion_range"),
        )
        .with_columns(
            pl.when(pl.col("n_unique_books") >= 3)
            .then(
                0.60 * pl.col("odds_dispersion_std").fill_null(0.0)
                + 0.40 * pl.col("odds_dispersion_range").fill_null(0.0)
            )
            .otherwise(None)
            .alias("consensus_disagreement_score")
        )
        .sort("consensus_disagreement_score", descending=True, nulls_last=True)
    )


def _capture_quality(canonical: pl.DataFrame) -> pl.DataFrame:
    return (
        canonical.group_by(["market_label", "snapshot_type"])
        .agg(
            pl.len().alias("n_quotes"),
            pl.col("hours_to_first_pitch").median().alias("median_hours_to_pitch"),
            pl.col("hours_to_first_pitch").quantile(0.1).alias("p10_hours_to_pitch"),
            pl.col("hours_to_first_pitch").quantile(0.9).alias("p90_hours_to_pitch"),
            pl.col("requested_minus_fetch_minutes").median().alias("median_requested_minus_fetch_min"),
            pl.col("minutes_stale_at_fetch").median().alias("median_staleness_min"),
            pl.col("minutes_stale_at_fetch").quantile(0.9).alias("p90_staleness_min"),
        )
        .sort(["market_label", "snapshot_type"])
    )


def _difficulty_buckets(dispersion: pl.DataFrame) -> pl.DataFrame:
    scored = dispersion.with_columns(
        pl.col("consensus_disagreement_score").fill_null(0.0).alias("_disagree"),
        pl.col("mean_vig").fill_null(0.0).alias("_vig"),
    )
    # Open-only proxy: more disagreement + higher vig = harder to beat.
    scored = scored.with_columns(
        (0.70 * pl.col("_disagree") + 0.30 * (pl.col("_vig") * 100.0)).alias("open_difficulty_score")
    )
    scored = scored.with_columns(
        pl.col("open_difficulty_score")
        .qcut(5, labels=["very_soft", "soft", "mid", "hard", "very_hard"], allow_duplicates=True)
        .alias("difficulty_bucket")
    )
    return scored.sort("open_difficulty_score", descending=True)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    canonical = _canonical_quotes()
    if canonical.is_empty():
        raise SystemExit("No open quote rows loaded; diagnostics not written.")

    book = _book_ranking(canonical)
    dispersion = _dispersion(canonical)
    capture = _capture_quality(canonical)
    difficulty = _difficulty_buckets(dispersion)

    canonical.write_parquet(CANONICAL_PATH)
    book.write_parquet(BOOK_PATH)
    dispersion.write_parquet(DISPERSION_PATH)
    capture.write_parquet(CAPTURE_PATH)
    difficulty.write_parquet(DIFFICULTY_PATH)

    summary = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_files": [str(K_SOURCE), str(OUTS_SOURCE)],
        "rows": {
            "canonical_quotes": canonical.height,
            "book_ranking": book.height,
            "dispersion": dispersion.height,
            "capture_quality": capture.height,
            "difficulty_buckets": difficulty.height,
        },
        "date_range": canonical.select(
            pl.col("game_date_d").min().cast(pl.Utf8).alias("min_game_date"),
            pl.col("game_date_d").max().cast(pl.Utf8).alias("max_game_date"),
        ).to_dicts()[0],
        "outputs": {
            "canonical": str(CANONICAL_PATH),
            "book_ranking": str(BOOK_PATH),
            "dispersion": str(DISPERSION_PATH),
            "capture_quality": str(CAPTURE_PATH),
            "difficulty": str(DIFFICULTY_PATH),
        },
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"wrote {CANONICAL_PATH}")
    print(f"wrote {BOOK_PATH}")
    print(f"wrote {DISPERSION_PATH}")
    print(f"wrote {CAPTURE_PATH}")
    print(f"wrote {DIFFICULTY_PATH}")
    print(f"wrote {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
