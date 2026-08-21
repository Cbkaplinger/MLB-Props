"""Build an actionable bookmaker quality scorecard from open-era diagnostics.

Combines:
- calibration quality (lower MAE/Brier and smaller absolute calibration gap),
- pricing tax (lower vig preferred),
- model-vs-open edge stability (lower std preferred; mean edge tracked, not over-weighted).

Outputs:
- artifacts/odds_log/book_quality_scorecard.parquet
- artifacts/odds_log/book_quality_scorecard_latest.csv
- artifacts/odds_log/book_quality_scorecard_summary.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
ODDS_DIR = ROOT / "artifacts" / "odds_log"

CAL_BOOK_PATH = ODDS_DIR / "open_proj_calibration_by_book.parquet"
BOOK_SIGNAL_PATH = ODDS_DIR / "open_projection_book_signal.parquet"

OUT_PATH = ODDS_DIR / "book_quality_scorecard.parquet"
OUT_CSV = ODDS_DIR / "book_quality_scorecard_latest.csv"
OUT_SUMMARY = ODDS_DIR / "book_quality_scorecard_summary.json"

MIN_SAMPLES = 750


def _weighted_book_metrics() -> pl.DataFrame:
    cal = pl.read_parquet(CAL_BOOK_PATH)
    return cal.group_by(["bookmaker", "bookmaker_title"]).agg(
        pl.col("n").sum().alias("n_samples"),
        ((pl.col("mae_prob") * pl.col("n")).sum() / pl.col("n").sum()).alias("mae_prob_w"),
        ((pl.col("brier") * pl.col("n")).sum() / pl.col("n").sum()).alias("brier_w"),
        ((pl.col("calibration_gap") * pl.col("n")).sum() / pl.col("n").sum()).alias(
            "calibration_gap_w"
        ),
        ((pl.col("mean_vig") * pl.col("n")).sum() / pl.col("n").sum()).alias("mean_vig_w"),
        ((pl.col("mean_edge_vs_open") * pl.col("n")).sum() / pl.col("n").sum()).alias(
            "edge_vs_open_w"
        ),
    )


def _normalize_to_unit_interval(df: pl.DataFrame, col: str, ascending_good: bool) -> pl.Expr:
    c = pl.col(col).cast(pl.Float64)
    c_min = df.select(pl.col(col).min()).item()
    c_max = df.select(pl.col(col).max()).item()
    if c_min is None or c_max is None or float(c_max) == float(c_min):
        return pl.lit(0.5)
    scaled = (c - float(c_min)) / (float(c_max) - float(c_min))
    return scaled if not ascending_good else (1.0 - scaled)


def main() -> None:
    if not CAL_BOOK_PATH.exists():
        raise FileNotFoundError(
            f"Missing {CAL_BOOK_PATH}. Run production/ops/build_open_projection_calibration_suite.py first."
        )
    if not BOOK_SIGNAL_PATH.exists():
        raise FileNotFoundError(
            f"Missing {BOOK_SIGNAL_PATH}. Run production/ops/build_open_projection_signal.py first."
        )

    weighted = _weighted_book_metrics()
    signal = pl.read_parquet(BOOK_SIGNAL_PATH).select(
        "bookmaker",
        "bookmaker_title",
        "n_quotes",
        "std_edge_novig",
        "mean_edge_novig",
    )

    merged = weighted.join(signal, on=["bookmaker", "bookmaker_title"], how="left")
    merged = merged.with_columns(
        pl.col("calibration_gap_w").abs().alias("abs_calibration_gap_w"),
        (pl.col("n_samples") >= MIN_SAMPLES).alias("is_eligible"),
    )

    # Independent component scores in [0,1], higher = better.
    score_base = merged.with_columns(
        _normalize_to_unit_interval(merged, "mae_prob_w", ascending_good=True).alias("score_mae"),
        _normalize_to_unit_interval(merged, "brier_w", ascending_good=True).alias("score_brier"),
        _normalize_to_unit_interval(merged, "abs_calibration_gap_w", ascending_good=True).alias(
            "score_cal_gap"
        ),
        _normalize_to_unit_interval(merged, "mean_vig_w", ascending_good=True).alias("score_vig"),
        _normalize_to_unit_interval(merged, "std_edge_novig", ascending_good=True).alias(
            "score_edge_stability"
        ),
    )

    # Quality score: calibration dominates, then vig, then stability.
    scored = score_base.with_columns(
        (
            0.30 * pl.col("score_mae")
            + 0.25 * pl.col("score_brier")
            + 0.15 * pl.col("score_cal_gap")
            + 0.20 * pl.col("score_vig")
            + 0.10 * pl.col("score_edge_stability")
        ).alias("book_quality_score")
    )

    scored = scored.with_columns(
        pl.when(~pl.col("is_eligible"))
        .then(pl.lit("insufficient_sample"))
        .when(pl.col("book_quality_score") >= 0.75)
        .then(pl.lit("tier_a"))
        .when(pl.col("book_quality_score") >= 0.55)
        .then(pl.lit("tier_b"))
        .otherwise(pl.lit("tier_c"))
        .alias("quality_tier")
    ).sort(["is_eligible", "book_quality_score"], descending=[True, True])

    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    scored.write_parquet(OUT_PATH)
    scored.write_csv(OUT_CSV)

    eligible = scored.filter(pl.col("is_eligible"))
    summary = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "min_samples": MIN_SAMPLES,
        "n_books_total": int(scored.height),
        "n_books_eligible": int(eligible.height),
        "top_eligible_books": eligible.select(
            "bookmaker",
            "bookmaker_title",
            "n_samples",
            "book_quality_score",
            "quality_tier",
            "mean_vig_w",
            "std_edge_novig",
        )
        .head(5)
        .to_dicts(),
        "outputs": {
            "parquet": str(OUT_PATH),
            "csv": str(OUT_CSV),
        },
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"wrote {OUT_PATH}")
    print(f"wrote {OUT_CSV}")
    print(f"wrote {OUT_SUMMARY}")
    print(summary)


if __name__ == "__main__":
    main()
