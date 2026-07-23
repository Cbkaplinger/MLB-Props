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

Venue overrides handle seasons where one ``home_team`` code represents a
different physical park. The Rays played 2025 at Steinbrenner Field and
returned to Tropicana Field in 2026, while Statcast uses ``TB`` for both.

Caveat: this is the *basic* venue-rate method and carries some team-composition
bias (the home team's hitters/pitchers appear disproportionately at their park).
For a bias-corrected number, move to the classic home/road split method; this
module is the transparent first pass the EDA is built on.

Neutral-site and international games are not yet resolved separately. They
remain assigned to Statcast's listed home team and are partially dampened by
the empirical-Bayes regression.
"""

from __future__ import annotations

import polars as pl

DEFAULT_REGRESS_PA: float = 500.0

# Team/date-range overrides for seasons where a team's home games were NOT
# played at their canonical park. Keyed by (team, start_date, end_date);
# venue label is used only for grouping -- home_team is untouched so Level 3
# joins still key on the real team code.
VENUE_OVERRIDES: dict[tuple[str, str, str], str] = {
    ("TB", "2025-01-01", "2025-12-31"): "TB_steinbrenner",
    # Tampa Bay returned to Tropicana Field in 2026, so this is intentionally
    # closed at the end of 2025.
}


def _resolve_venue(df: pl.DataFrame) -> pl.DataFrame:
    """Add a `venue` column, defaulting to `home_team` unless overridden."""
    venue = pl.col("home_team")
    for (team, start, end), label in VENUE_OVERRIDES.items():
        venue = (
            pl.when(
                (pl.col("home_team") == team)
                & pl.col("game_date").cast(pl.Date).is_between(
                    pl.lit(start).str.to_date(), pl.lit(end).str.to_date()
                )
            )
            .then(pl.lit(label))
            .otherwise(venue)
        )
    return df.with_columns(venue.alias("venue"))


def _target_season_venues(
    dated: pl.DataFrame,
    season: int,
) -> pl.DataFrame:
    """Map teams to venues, including a target season absent from ``dated``."""
    observed = (
        dated.filter(pl.col("_source_season") == season)
        .select("home_team", "venue")
        .unique()
    )
    if observed.height:
        return observed

    prior = dated.filter(pl.col("_source_season") < season)
    source_season = (
        prior["_source_season"].max()
        if prior.height
        else dated["_source_season"].min()
    )
    teams = (
        dated.filter(pl.col("_source_season") == source_season)
        .select("home_team")
        .unique()
        .with_columns(pl.date(season, 7, 1).alias("game_date"))
    )
    return _resolve_venue(teams).select("home_team", "venue")


def park_k_factor(pa: pl.DataFrame, regress: float = DEFAULT_REGRESS_PA) -> pl.DataFrame:
    """Compute an empirical, regressed strikeout park factor per venue.

    Returns one row per resolved ``venue`` with ``PA``, ``K``, and
    ``park_k_factor``.
    """
    pa = _resolve_venue(pa)
    per = pa.group_by("venue").agg(
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

    The result remains keyed by ``(season, home_team)`` for the Level 3 join.
    If a target season is not present in ``pa`` (for example, a future
    projection season), the latest observed team set is resolved using the
    target year's venue rules. A venue with no prior history receives 1.0.
    """
    seasons = sorted({int(year) for year in target_seasons})
    dated = _resolve_venue(pa).with_columns(
        pl.col("game_date").cast(pl.Date).dt.year().alias("_source_season")
    )
    outputs: list[pl.DataFrame] = []

    for season in seasons:
        history = dated.filter(pl.col("_source_season") < season)
        target_venues = _target_season_venues(dated, season)
        computed = (
            park_k_factor(history, regress=regress).select(
                "venue", "PA", "K", "park_k_factor"
            )
            if history.height
            else target_venues.select("venue").unique()
            .with_columns(
                pl.lit(0, dtype=pl.UInt32).alias("PA"),
                pl.lit(0, dtype=pl.UInt32).alias("K"),
                pl.lit(1.0).alias("park_k_factor"),
            )
        )
        factors = (
            target_venues.join(computed, on="venue", how="left")
            .with_columns(
                pl.col("PA").fill_null(0),
                pl.col("K").fill_null(0),
                pl.col("park_k_factor").fill_null(1.0),
            )
        )
        outputs.append(
            factors.select("home_team", "PA", "K", "park_k_factor")
            .with_columns(pl.lit(season).alias("season"))
        )

    return (
        pl.concat(outputs, how="diagonal_relaxed")
        .select("season", "home_team", "PA", "K", "park_k_factor")
        .sort(["season", "home_team"])
    )