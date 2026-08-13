"""Shared notebook helpers for production analysis views."""

from __future__ import annotations

import polars as pl


def keep_best_available_lines(df: pl.DataFrame) -> pl.DataFrame:
    """Keep one row per game/player/side using highest edge line available."""
    if df.is_empty() or "edge" not in df.columns:
        return df
    key_cols = [c for c in ["game_date", "player_name", "side"] if c in df.columns]
    if len(key_cols) < 2:
        return df
    tie_cols = [c for c in ["edge", "stake", "best_price", "line"] if c in df.columns]
    ranked = df.sort(
        key_cols + tie_cols,
        descending=([False] * len(key_cols)) + ([True] * len(tie_cols)),
    )
    return ranked.unique(subset=key_cols, keep="first")


def side_clv_roi_health(
    df: pl.DataFrame,
    *,
    side_col: str = "side",
    stake_col: str = "stake",
    pnl_col: str = "pnl",
    clv_col: str = "clv_pp",
) -> pl.DataFrame:
    """Aggregate side-level n, stake, pnl, roi, and mean CLV."""
    if df.is_empty() or side_col not in df.columns:
        return pl.DataFrame()
    needed = {stake_col, pnl_col, clv_col}
    if not needed.issubset(set(df.columns)):
        return pl.DataFrame()
    return (
        df.group_by(side_col)
        .agg(
            pl.len().alias("n"),
            pl.col(stake_col).cast(pl.Float64).sum().alias("stake"),
            pl.col(pnl_col).cast(pl.Float64).sum().alias("pnl"),
            (
                pl.col(pnl_col).cast(pl.Float64).sum()
                / pl.col(stake_col).cast(pl.Float64).sum()
            ).alias("roi"),
            pl.col(clv_col).cast(pl.Float64).drop_nulls().mean().alias("mean_clv_pp"),
        )
        .sort(side_col)
    )


def has_over_clv_red_flag(
    side_health: pl.DataFrame,
    *,
    side_col: str = "side",
    over_label: str = "over",
    clv_mean_col: str = "mean_clv_pp",
) -> bool:
    """Return True when over-side CLV is missing or non-positive."""
    if side_health.is_empty() or side_col not in side_health.columns:
        return False
    if clv_mean_col not in side_health.columns:
        return False
    over_rows = side_health.filter(pl.col(side_col) == over_label)
    if over_rows.is_empty():
        return False
    over_clv = over_rows.select(clv_mean_col).item()
    return over_clv is None or float(over_clv) <= 0
