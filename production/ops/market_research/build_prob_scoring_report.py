"""Build probability scoring report (ECE + Brier) for model vs market.

Compares predictors against realized binary over outcomes:
- model: p_model_over
- market_vigged: implied from over_odds directly
- market_novig: de-vigged two-way over probability

Outputs:
- artifacts/odds_log/prob_scoring_overall.parquet
- artifacts/odds_log/prob_scoring_by_line.parquet
- artifacts/odds_log/prob_scoring_by_book.parquet
- artifacts/odds_log/prob_scoring_by_maturity.parquet
- artifacts/odds_log/prob_scoring_summary.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
ODDS_DIR = ROOT / "artifacts" / "odds_log"
ROWS_PATH = ODDS_DIR / "open_proj_calibration_rows.parquet"

OVERALL_OUT = ODDS_DIR / "prob_scoring_overall.parquet"
LINE_OUT = ODDS_DIR / "prob_scoring_by_line.parquet"
BOOK_OUT = ODDS_DIR / "prob_scoring_by_book.parquet"
MATURITY_OUT = ODDS_DIR / "prob_scoring_by_maturity.parquet"
SUMMARY_OUT = ODDS_DIR / "prob_scoring_summary.json"


def _american_to_implied_prob(price_expr: pl.Expr) -> pl.Expr:
    p = price_expr.cast(pl.Float64)
    return (
        pl.when(p > 0)
        .then(100.0 / (p + 100.0))
        .otherwise((-p) / ((-p) + 100.0))
    )


def _ece_for_frame(
    frame: pl.DataFrame,
    *,
    p_col: str,
    y_col: str = "actual_over",
    n_bins: int = 10,
) -> float | None:
    if frame.is_empty():
        return None
    df = frame.filter(pl.col(p_col).is_not_null() & pl.col(y_col).is_not_null())
    if df.is_empty():
        return None
    # Equal-width probability bins [0,1].
    binned = df.with_columns(
        pl.col(p_col)
        .clip(1e-6, 1 - 1e-6)
        .cut(
            breaks=[i / n_bins for i in range(1, n_bins)],
            labels=[f"b{i}" for i in range(n_bins)],
            left_closed=True,
        )
        .alias("_bin")
    )
    bins = binned.group_by("_bin").agg(
        pl.len().alias("n"),
        pl.col(p_col).mean().alias("mean_p"),
        pl.col(y_col).mean().alias("mean_y"),
    )
    if bins.is_empty():
        return None
    total_n = int(bins["n"].sum())
    if total_n <= 0:
        return None
    ece = (
        bins.with_columns((pl.col("mean_p") - pl.col("mean_y")).abs().alias("gap"))
        .with_columns((pl.col("n") / total_n * pl.col("gap")).alias("weighted_gap"))[
            "weighted_gap"
        ].sum()
    )
    return float(ece) if ece is not None else None


def _score_block(frame: pl.DataFrame) -> dict[str, float | int | None]:
    n = int(frame.height)
    if n == 0:
        return {
            "n": 0,
            "brier_model": None,
            "brier_market_vigged": None,
            "brier_market_novig": None,
            "ece_model": None,
            "ece_market_vigged": None,
            "ece_market_novig": None,
        }

    out = {
        "n": n,
        "brier_model": float(
            frame.select(
                (pl.col("p_model_over") - pl.col("actual_over").cast(pl.Float64))
                .pow(2)
                .mean()
                .alias("x")
            )["x"][0]
        ),
        "brier_market_vigged": float(
            frame.select(
                (pl.col("p_over_implied_from_price") - pl.col("actual_over").cast(pl.Float64))
                .pow(2)
                .mean()
                .alias("x")
            )["x"][0]
        ),
        "brier_market_novig": float(
            frame.select(
                (pl.col("p_over_novig") - pl.col("actual_over").cast(pl.Float64))
                .pow(2)
                .mean()
                .alias("x")
            )["x"][0]
        ),
        "ece_model": _ece_for_frame(frame, p_col="p_model_over"),
        "ece_market_vigged": _ece_for_frame(frame, p_col="p_over_implied_from_price"),
        "ece_market_novig": _ece_for_frame(frame, p_col="p_over_novig"),
    }
    return out


def _build_group_table(frame: pl.DataFrame, group_cols: list[str]) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    grouped = frame.group_by(group_cols)
    for key, sub in grouped:
        if not isinstance(key, tuple):
            key = (key,)
        base = {col: val for col, val in zip(group_cols, key)}
        base.update(_score_block(sub))
        rows.append(base)
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows)


def main() -> None:
    if not ROWS_PATH.exists():
        raise FileNotFoundError(f"Missing {ROWS_PATH}")
    rows = pl.read_parquet(ROWS_PATH).filter(
        pl.col("actual_over").is_not_null()
        & pl.col("p_model_over").is_not_null()
        & pl.col("p_over_novig").is_not_null()
        & pl.col("over_odds").is_not_null()
    )
    rows = rows.with_columns(
        _american_to_implied_prob(pl.col("over_odds")).alias("p_over_implied_from_price")
    )

    overall = pl.DataFrame([_score_block(rows)])
    by_line = _build_group_table(rows, ["line"]).sort("line")
    by_book = _build_group_table(rows, ["bookmaker"]).sort("n", descending=True)
    by_maturity = _build_group_table(rows, ["maturity_bucket"]).sort("n", descending=True)

    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    overall.write_parquet(OVERALL_OUT)
    by_line.write_parquet(LINE_OUT)
    by_book.write_parquet(BOOK_OUT)
    by_maturity.write_parquet(MATURITY_OUT)

    summary = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows_scored": int(rows.height),
        "overall": overall.to_dicts()[0] if overall.height else {},
        "best_brier_by_line": by_line.select(
            "line", "n", "brier_model", "brier_market_vigged", "brier_market_novig"
        ).to_dicts(),
        "outputs": {
            "overall": str(OVERALL_OUT),
            "by_line": str(LINE_OUT),
            "by_book": str(BOOK_OUT),
            "by_maturity": str(MATURITY_OUT),
        },
    }
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {OVERALL_OUT}")
    print(f"wrote {LINE_OUT}")
    print(f"wrote {BOOK_OUT}")
    print(f"wrote {MATURITY_OUT}")
    print(f"wrote {SUMMARY_OUT}")
    print(summary)


if __name__ == "__main__":
    main()
