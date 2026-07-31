"""Gates for live / paper projections that are outside model support.

These rows can still produce numerically valid ``p_over_*`` and huge apparent
edges (e.g. long-layoff TBF collapse → expected_K < 1 → under 3.5 looks like
free money). Never size bets on them.

Postgame grading also excludes **abbreviated outings** (openers / early injury
exits) via ``actual_PA < MIN_STARTER_ACTUAL_PA``, matching the training cohort
(``PA >= 9`` true-start filter).
"""

from __future__ import annotations

from typing import Any

import polars as pl

from Python import config

# Shared with grading / notebook intent.
EXTREME_REST_DAYS = 120
# Starter K props assume a full outing. Ridge can emit ~4 PA after weird rest;
# that is not a usable strikeout projection.
MIN_STARTER_PROJECTED_TBF = 12.0
MIN_STARTER_EXPECTED_K = 1.5
# Postgame: openers + 1st-inning injury exits (same default as Level 1 starts).
MIN_STARTER_ACTUAL_PA = int(getattr(config, "MIN_STARTER_BATTERS_FACED", 9))


def projection_oos_reason(
    *,
    projected_tbf: float | None = None,
    days_rest: float | None = None,
    expected_K: float | None = None,
) -> str | None:
    """Return a short reason if the *pregame* projection is out of support."""
    if projected_tbf is not None and float(projected_tbf) <= 0.0:
        return "projected_tbf<=0"
    if projected_tbf is not None and float(projected_tbf) < MIN_STARTER_PROJECTED_TBF:
        return f"projected_tbf<{MIN_STARTER_PROJECTED_TBF:g}"
    if expected_K is not None and float(expected_K) < MIN_STARTER_EXPECTED_K:
        return f"expected_K<{MIN_STARTER_EXPECTED_K:g}"
    if days_rest is not None and float(days_rest) >= EXTREME_REST_DAYS:
        return f"days_rest>={EXTREME_REST_DAYS}"
    return None


def abbreviated_outing_reason(
    *,
    actual_PA: float | None,
    min_pa: int = MIN_STARTER_ACTUAL_PA,
) -> str | None:
    """Postgame opener / early-exit gate (needs actual batters faced)."""
    if actual_PA is None:
        return None
    if float(actual_PA) < float(min_pa):
        return f"actual_PA<{min_pa:g}"
    return None


def row_oos_reason(row: dict[str, Any]) -> str | None:
    return projection_oos_reason(
        projected_tbf=row.get("projected_tbf"),
        days_rest=row.get("days_rest"),
        expected_K=row.get("expected_K"),
    )


def is_projection_in_support(row: dict[str, Any]) -> bool:
    return row_oos_reason(row) is None


def mark_out_of_support(frame: pl.DataFrame) -> pl.DataFrame:
    """Add pregame ``is_out_of_support`` (+ ``oos_reason`` when possible)."""
    if frame.is_empty():
        return frame.with_columns(
            pl.lit(False).alias("is_out_of_support"),
            pl.lit(None, dtype=pl.Utf8).alias("oos_reason"),
        )
    flag = pl.lit(False)
    if "projected_tbf" in frame.columns:
        flag = flag | (pl.col("projected_tbf") <= 0.0).fill_null(False)
        flag = flag | (
            pl.col("projected_tbf") < MIN_STARTER_PROJECTED_TBF
        ).fill_null(False)
    if "expected_K" in frame.columns:
        flag = flag | (pl.col("expected_K") < MIN_STARTER_EXPECTED_K).fill_null(False)
    if "days_rest" in frame.columns:
        flag = flag | (pl.col("days_rest") >= EXTREME_REST_DAYS).fill_null(False)

    reason = pl.lit(None, dtype=pl.Utf8)
    if "projected_tbf" in frame.columns:
        reason = (
            pl.when(pl.col("projected_tbf") <= 0.0)
            .then(pl.lit("projected_tbf<=0"))
            .when(pl.col("projected_tbf") < MIN_STARTER_PROJECTED_TBF)
            .then(pl.lit(f"projected_tbf<{MIN_STARTER_PROJECTED_TBF:g}"))
            .otherwise(reason)
        )
    if "expected_K" in frame.columns:
        reason = (
            pl.when(reason.is_null() & (pl.col("expected_K") < MIN_STARTER_EXPECTED_K))
            .then(pl.lit(f"expected_K<{MIN_STARTER_EXPECTED_K:g}"))
            .otherwise(reason)
        )
    if "days_rest" in frame.columns:
        reason = (
            pl.when(reason.is_null() & (pl.col("days_rest") >= EXTREME_REST_DAYS))
            .then(pl.lit(f"days_rest>={EXTREME_REST_DAYS}"))
            .otherwise(reason)
        )
    return frame.with_columns(
        flag.alias("is_out_of_support"),
        reason.alias("oos_reason"),
    )


def mark_abbreviated_outing(
    frame: pl.DataFrame,
    *,
    min_pa: int = MIN_STARTER_ACTUAL_PA,
) -> pl.DataFrame:
    """Flag openers / early injury exits from postgame ``actual_PA``.

    Rows without actuals stay ``is_abbreviated_outing=False`` (not yet known).
    """
    if frame.is_empty() or "actual_PA" not in frame.columns:
        return frame.with_columns(
            pl.lit(False).alias("is_abbreviated_outing"),
            pl.lit(None, dtype=pl.Utf8).alias("abbrev_reason"),
        )
    flag = pl.col("actual_PA").is_not_null() & (pl.col("actual_PA") < float(min_pa))
    reason = (
        pl.when(flag)
        .then(pl.lit(f"actual_PA<{min_pa:g}"))
        .otherwise(pl.lit(None, dtype=pl.Utf8))
    )
    return frame.with_columns(
        flag.alias("is_abbreviated_outing"),
        reason.alias("abbrev_reason"),
    )
