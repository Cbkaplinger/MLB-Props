"""Analyze calibration gaps by line and American-odds price bands.

Inputs:
- artifacts/odds_log/open_proj_calibration_rows.parquet
- artifacts/odds_log/book_quality_scorecard.parquet

Outputs:
- artifacts/odds_log/line_price_calibration_grid.parquet
- artifacts/odds_log/line_price_common_odds.parquet
- artifacts/odds_log/line_price_book_baseline_view.parquet
- artifacts/odds_log/book_baseline_replacement.json
- artifacts/odds_log/line_price_calibration_summary.json
"""

from __future__ import annotations

import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
ODDS_DIR = ROOT / "artifacts" / "odds_log"

ROWS_PATH = ODDS_DIR / "open_proj_calibration_rows.parquet"
SCORECARD_PATH = ODDS_DIR / "book_quality_scorecard.parquet"

GRID_OUT = ODDS_DIR / "line_price_calibration_grid.parquet"
COMMON_OUT = ODDS_DIR / "line_price_common_odds.parquet"
BASELINE_VIEW_OUT = ODDS_DIR / "line_price_book_baseline_view.parquet"
BASELINE_JSON = ODDS_DIR / "book_baseline_replacement.json"
SUMMARY_OUT = ODDS_DIR / "line_price_calibration_summary.json"


def _american_to_implied_prob(price_expr: pl.Expr) -> pl.Expr:
    p = price_expr.cast(pl.Float64)
    return (
        pl.when(p > 0)
        .then(100.0 / (p + 100.0))
        .otherwise((-p) / ((-p) + 100.0))
    )


def _price_bucket_expr(price_col: str) -> pl.Expr:
    p = pl.col(price_col).cast(pl.Float64)
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


def _load_rows() -> pl.DataFrame:
    if not ROWS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {ROWS_PATH}. Run production/ops/build_open_projection_calibration_suite.py first."
        )
    rows = pl.read_parquet(ROWS_PATH)
    rows = rows.filter(
        pl.col("actual_over").is_not_null()
        & pl.col("line").is_not_null()
        & pl.col("over_odds").is_not_null()
        & pl.col("p_model_over").is_not_null()
    ).with_columns(
        _american_to_implied_prob(pl.col("over_odds")).alias("p_over_implied_from_price"),
        _price_bucket_expr("over_odds").alias("over_price_bucket"),
    )
    return rows.with_columns(
        (pl.col("p_model_over") - pl.col("p_over_implied_from_price")).alias("gap_model_vs_vigged"),
        (pl.col("p_model_over") - pl.col("actual_over").cast(pl.Float64)).alias("gap_model_vs_actual"),
        (pl.col("p_over_implied_from_price") - pl.col("actual_over").cast(pl.Float64)).alias(
            "gap_market_vigged_vs_actual"
        ),
    )


def _build_grid(rows: pl.DataFrame) -> pl.DataFrame:
    return (
        rows.group_by(["line", "over_price_bucket", "maturity_bucket"])
        .agg(
            pl.len().alias("n"),
            pl.col("over_odds").mean().alias("mean_over_odds"),
            pl.col("p_over_implied_from_price").mean().alias("mean_market_prob_vigged"),
            pl.col("p_over_novig").mean().alias("mean_market_prob_novig"),
            pl.col("p_model_over").mean().alias("mean_model_prob"),
            pl.col("actual_over").mean().alias("hit_rate"),
            pl.col("gap_model_vs_vigged").mean().alias("model_minus_vigged"),
            pl.col("edge_vs_open_novig").mean().alias("model_minus_novig"),
            pl.col("gap_model_vs_actual").mean().alias("model_minus_actual"),
            pl.col("gap_market_vigged_vs_actual").mean().alias("market_vigged_minus_actual"),
            ((pl.col("p_model_over") - pl.col("actual_over").cast(pl.Float64)).pow(2).mean()).alias(
                "brier_model"
            ),
            (
                (pl.col("p_over_implied_from_price") - pl.col("actual_over").cast(pl.Float64))
                .pow(2)
                .mean()
            ).alias("brier_market_vigged"),
        )
        .with_columns((pl.col("brier_model") - pl.col("brier_market_vigged")).alias("delta_brier_model_minus_market"))
        .sort(["line", "over_price_bucket", "maturity_bucket"])
    )


def _common_odds(rows: pl.DataFrame) -> pl.DataFrame:
    common = (
        rows.group_by(["line", "over_odds"])
        .agg(
            pl.len().alias("n"),
            pl.col("p_over_implied_from_price").mean().alias("market_prob_vigged"),
            pl.col("p_model_over").mean().alias("model_prob"),
            pl.col("actual_over").mean().alias("hit_rate"),
            pl.col("edge_vs_open_novig").mean().alias("model_minus_novig"),
        )
        .with_columns(
            (pl.col("model_prob") - pl.col("market_prob_vigged")).alias("model_minus_vigged"),
            (pl.col("model_prob") - pl.col("hit_rate")).alias("model_minus_actual"),
        )
    )
    return common.filter(pl.col("n") >= 100).sort(["line", "n"], descending=[False, True])


def _baseline_view(
    rows: pl.DataFrame,
    *,
    baseline_books: list[str] | None = None,
) -> tuple[pl.DataFrame, dict[str, object]]:
    if not SCORECARD_PATH.exists():
        raise FileNotFoundError(
            f"Missing {SCORECARD_PATH}. Run production/ops/build_book_quality_scorecard.py first."
        )
    score = pl.read_parquet(SCORECARD_PATH)
    if baseline_books:
        baseline_books = [b.strip().lower() for b in baseline_books if b.strip()]
    else:
        baseline_books = (
            score.filter(pl.col("is_eligible"))
            .sort("book_quality_score", descending=True)
            .select("bookmaker")
            .head(3)["bookmaker"]
            .to_list()
        )
    base = rows.filter(pl.col("bookmaker").is_in(baseline_books))
    view = (
        base.group_by(["bookmaker", "line", "over_price_bucket"])
        .agg(
            pl.len().alias("n"),
            pl.col("p_over_implied_from_price").mean().alias("mean_market_prob_vigged"),
            pl.col("p_over_novig").mean().alias("mean_market_prob_novig"),
            pl.col("p_model_over").mean().alias("mean_model_prob"),
            pl.col("actual_over").mean().alias("hit_rate"),
            pl.col("edge_vs_open_novig").mean().alias("model_minus_novig"),
            (pl.col("p_model_over") - pl.col("actual_over").cast(pl.Float64)).mean().alias(
                "model_minus_actual"
            ),
        )
        .sort(["bookmaker", "line", "over_price_bucket"])
    )
    payload = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline_books": baseline_books,
        "selection_rule": (
            "manual baseline list"
            if baseline_books
            else "top_3 eligible books from book_quality_scorecard"
        ),
    }
    return view, payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-books",
        type=str,
        default=None,
        help="Comma-separated baseline bookmakers (e.g. 'draftkings,fanduel').",
    )
    args = parser.parse_args()

    rows = _load_rows()
    grid = _build_grid(rows)
    common = _common_odds(rows)
    baseline_list = (
        [p.strip() for p in args.baseline_books.split(",")]
        if args.baseline_books
        else ["draftkings", "fanduel"]
    )
    baseline_view, baseline_payload = _baseline_view(rows, baseline_books=baseline_list)

    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    grid.write_parquet(GRID_OUT)
    common.write_parquet(COMMON_OUT)
    baseline_view.write_parquet(BASELINE_VIEW_OUT)
    BASELINE_JSON.write_text(json.dumps(baseline_payload, indent=2), encoding="utf-8")

    minus_120 = (
        common.filter(pl.col("over_odds") == -120)
        .sort("n", descending=True)
        .head(10)
        .to_dicts()
    )
    summary = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reference_probs": {
            "american_-120_implied_prob_vigged": float(120.0 / (120.0 + 100.0)),
            "american_+120_implied_prob_vigged": float(100.0 / (120.0 + 100.0)),
        },
        "rows_used": int(rows.height),
        "outputs": {
            "grid": str(GRID_OUT),
            "common_odds": str(COMMON_OUT),
            "baseline_view": str(BASELINE_VIEW_OUT),
            "baseline_json": str(BASELINE_JSON),
        },
        "minus_120_examples": minus_120,
    }
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"wrote {GRID_OUT}")
    print(f"wrote {COMMON_OUT}")
    print(f"wrote {BASELINE_VIEW_OUT}")
    print(f"wrote {BASELINE_JSON}")
    print(f"wrote {SUMMARY_OUT}")
    print(summary)


if __name__ == "__main__":
    main()
