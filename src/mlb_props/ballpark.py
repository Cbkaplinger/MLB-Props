"""Leakage-safe empirical ballpark strikeout factors (Polars).

Park effects are stored as a small season/team dimension table. For target
season ``Y``, the factor uses only plate appearances from seasons before ``Y``.
This avoids the subtle leakage caused by computing one venue constant over the
entire train/validation/test window.

Factor definition (simple "venue rate vs league", empirical-Bayes regressed):

```text
park_k_factor(park) = EB_rate(park) / league_rate
EB_rate(park)       = (K_park + regress * league_rate) / (PA_park + regress)
```

A factor of 1.00 is league-neutral; > 1 means the park inflates strikeouts.
``regress`` (in PA) pulls small-sample parks toward neutral.

Caveat: this is the *basic* venue-rate method and carries some team-composition
bias (the home team's hitters/pitchers appear disproportionately at their park).
For a bias-corrected number, move to the classic home/road split method; this
module is the transparent first pass the EDA is built on.
"""

from __future__ import annotations

import polars as pl

DEFAULT_REGRESS_PA: float = 500.0


def park_k_factor(pa: pl.DataFrame, regress: float = DEFAULT_REGRESS_PA) -> pl.DataFrame:
    """Compute an empirical, regressed strikeout park factor per stadium.

    Args:
        pa: Plate-appearance frame (from ``statcast.plate_appearances``) carrying
            ``home_team`` (the stadium) and the ``is_k`` flag.
        regress: Empirical-Bayes prior strength in PA.

    Returns:
        One row per ``home_team`` with ``PA``, ``K``, and ``park_k_factor``.
    """
    per = pa.group_by("home_team").agg(
        pl.len().alias("PA"),
        pl.col("is_k").sum().alias("K"),
    )
    league_rate = per["K"].sum() / per["PA"].sum()
    return per.with_columns(
        (
            (pl.col("K") + regress * league_rate)
            / (pl.col("PA") + regress)
            / league_rate
        ).alias("park_k_factor")
    ).sort("park_k_factor", descending=True)


def pregame_park_factors(
    pa: pl.DataFrame,
    target_seasons: object,
    regress: float = DEFAULT_REGRESS_PA,
) -> pl.DataFrame:
    """Build factors for each target season from prior seasons only.

    A neutral ``1.0`` is emitted for target seasons with no prior observations.
    The result is keyed by ``(season, home_team)`` for a leakage-safe Level 3
    join.
    """
    seasons = sorted({int(year) for year in target_seasons})
    dated = pa.with_columns(
        pl.col("game_date").cast(pl.Date).dt.year().alias("_source_season")
    )
    teams = dated.select("home_team").unique()
    outputs: list[pl.DataFrame] = []

    for season in seasons:
        history = dated.filter(pl.col("_source_season") < season)
        factors = (
            park_k_factor(history, regress=regress).select(
                "home_team", "PA", "K", "park_k_factor"
            )
            if history.height
            else teams.with_columns(
                pl.lit(0, dtype=pl.UInt32).alias("PA"),
                pl.lit(0, dtype=pl.UInt32).alias("K"),
                pl.lit(1.0).alias("park_k_factor"),
            )
        )
        outputs.append(factors.with_columns(pl.lit(season).alias("season")))

    return (
        pl.concat(outputs, how="diagonal_relaxed")
        .select("season", "home_team", "PA", "K", "park_k_factor")
        .sort(["season", "home_team"])
    )
