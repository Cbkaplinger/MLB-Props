"""Leakage-safe rolling / season-to-date pitcher features (Polars).

The pitcher-side companion to :mod:`batter_rolling`. It turns the per-start
pitcher table (:func:`pitcher_features.build_pitcher_starts`) into **pregame**
features: for any start ``G`` every value uses only starts *strictly before*
``G`` for that pitcher. Keeping this logic in a tested module makes the pitcher
spine feeding Level 3 reproducible.

Two flavors, mirroring the batter side:

1. **Rolling last-N starts** (``{name}_P{w}``): PA/pitch-weighted for rate stats,
   simple mean for physics/rate columns. ``shift(1)`` drops the current start
   before the rolling window, so the value is known pregame.
2. **Season-to-date** (``{name}_std``): expanding, resets each season, for the
   rate stats.

Rate stats are defined as ``(numerator, denominator)`` count pairs so the rolled
value is a properly weighted rate (``Σnum / Σden``), not an average of ratios.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import polars as pl

_ORDER: tuple[str, ...] = ("pitcher", "game_date", "game_pk")

# Rate features -> (numerator_count, denominator_count) on the per-start table.
DEFAULT_RATE_STATS: dict[str, tuple[str, str]] = {
    "k_rate": ("K", "PA"),
    "bb_rate": ("BB", "PA"),
    "csw_rate": ("CSW", "Pitches"),
    "swstr_rate": ("Whiffs", "Pitches"),   # whiffs per pitch
    "whiff_rate": ("Whiffs", "Swings"),    # whiffs per swing
    "cs_rate": ("CS", "Pitches"),
    "chase_rate": ("Chases", "OutZone"),
    "zone_rate": ("InZone", "Pitches"),
    "contact_rate": ("Contacts", "Swings"),
    "gb_rate": ("GB", "BIP"),
    "hr_rate": ("HR", "PA"),
}

# Per-start values rolled with a simple mean (physics, mechanics, usage, xstats).
_PITCH_TYPES: tuple[str, ...] = ("ff", "si", "fc", "sl", "st", "cu", "ch")
DEFAULT_MEAN_COLS: tuple[str, ...] = (
    *(f"{pt}_{m}" for pt in _PITCH_TYPES for m in ("velo", "spinrate", "ivb", "hb", "vaa")),
    *(f"{pt}_usage_v{h}" for pt in _PITCH_TYPES for h in ("R", "L")),
    "extension", "rel_x", "rel_z", "rel_x_sd", "rel_z_sd",
    "xBA", "wOBA", "xwOBA", "FIP", "xFIP",
)

DEFAULT_RATE_WINDOWS: tuple[int, ...] = (5, 10, 20)
DEFAULT_MEAN_WINDOWS: tuple[int, ...] = (3, 5, 10)


def _prior_rate(num: str, den: str, by: list[str]) -> pl.Expr:
    """Expanding rate over prior rows only (cumulative minus current)."""
    prior_num = pl.col(num).cum_sum().over(by) - pl.col(num)
    prior_den = pl.col(den).cum_sum().over(by) - pl.col(den)
    return pl.when(prior_den > 0).then(prior_num / prior_den).otherwise(None)


def _rolling_rate(num: str, den: str, window: int, min_games: int) -> pl.Expr:
    """PA/pitch-weighted rate over the previous ``window`` starts (current excluded)."""
    roll_num = pl.col(num).shift(1).rolling_sum(window_size=window, min_samples=min_games).over("pitcher")
    roll_den = pl.col(den).shift(1).rolling_sum(window_size=window, min_samples=min_games).over("pitcher")
    return pl.when(roll_den > 0).then(roll_num / roll_den).otherwise(None)


def _rolling_mean(col: str, window: int, min_games: int) -> pl.Expr:
    """Mean of a per-start column over the previous ``window`` starts (current excluded)."""
    return pl.col(col).shift(1).rolling_mean(window_size=window, min_samples=min_games).over("pitcher")


def add_rolling_pitcher_features(
    starts: pl.DataFrame,
    rate_stats: Mapping[str, tuple[str, str]] = DEFAULT_RATE_STATS,
    mean_cols: Iterable[str] = DEFAULT_MEAN_COLS,
    rate_windows: Iterable[int] = DEFAULT_RATE_WINDOWS,
    mean_windows: Iterable[int] = DEFAULT_MEAN_WINDOWS,
    season_to_date: bool = True,
    min_games: int = 1,
) -> pl.DataFrame:
    """Append leakage-safe rolling / season-to-date features to the start table.

    Args:
        starts: Per-start pitcher table (needs ``pitcher, game_date, game_pk`` and
            the numerator/denominator columns referenced by ``rate_stats`` plus
            any ``mean_cols`` present).
        rate_stats: ``{feature: (num_col, den_col)}``. Missing columns are skipped.
        mean_cols: Per-start columns rolled with a simple mean. Missing skipped.
        rate_windows / mean_windows: Rolling window sizes (in starts).
        season_to_date: Also emit expanding ``{name}_std`` for each rate stat.
        min_games: Minimum prior starts required to emit a rolling value.

    Returns:
        ``starts`` (order preserved) with added columns:
            ``season``, ``{rate}_P{w}``, ``{rate}_std`` (if enabled),
            ``{mean_col}_P{w}``.
    """
    rate_windows, mean_windows = list(rate_windows), list(mean_windows)
    rate_stats = {
        name: (num, den)
        for name, (num, den) in rate_stats.items()
        if num in starts.columns and den in starts.columns
    }
    mean_cols = [c for c in mean_cols if c in starts.columns]

    df = starts.with_columns(pl.col("game_date").dt.year().alias("season")).sort(_ORDER)

    rate_exprs: list[pl.Expr] = []
    for name, (num, den) in rate_stats.items():
        rate_exprs += [
            _rolling_rate(num, den, w, min_games).alias(f"{name}_P{w}") for w in rate_windows
        ]
        if season_to_date:
            rate_exprs.append(_prior_rate(num, den, ["pitcher", "season"]).alias(f"{name}_std"))

    mean_exprs = [
        _rolling_mean(col, w, min_games).alias(f"{col}_P{w}")
        for col in mean_cols
        for w in mean_windows
    ]

    return df.with_columns(rate_exprs + mean_exprs).sort(_ORDER)
