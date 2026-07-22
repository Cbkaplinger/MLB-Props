"""Build the per-batter-per-game table from pitch-level Statcast (Polars).

One row per (game_pk, batter): the hitter's full outcome line for that game,
plus splits vs LHP/RHP so downstream code can build leakage-safe season-to-date
K% (overall and by pitcher hand) and aggregate it into opposing-lineup features.

This is the batter-side companion to ``pitcher_features`` and shares the
event-flag / xwOBA primitives from ``statcast``.
"""

from __future__ import annotations

import polars as pl

from .statcast import (
    add_event_flags,
    add_plate_discipline_flags,
    add_plate_discipline_rates,
    discipline_count_exprs,
    woba_agg,
    xwoba_agg,
)

# Columns needed from the raw pitch-level data for the batter table.
BUILD_COLUMNS: tuple[str, ...] = (
    "game_pk", "game_date", "batter", "stand", "p_throws",
    "home_team", "away_team", "inning_topbot",
    "events", "description", "type", "zone",
    "estimated_woba_using_speedangle", "woba_value", "woba_denom",
)


def build_batter_games(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate pitch-level Statcast into one row per (game_pk, batter)."""
    flagged = add_plate_discipline_flags(add_event_flags(df)).with_columns(
        pl.when(pl.col("inning_topbot") == "Top")
          .then(pl.col("away_team"))
          .otherwise(pl.col("home_team"))
          .alias("bat_team"),
    )

    vL = pl.col("p_throws") == "L"
    vR = pl.col("p_throws") == "R"

    out = (
        flagged.group_by(["game_pk", "batter"])
        .agg(
            pl.col("game_date").first(),
            pl.col("bat_team").first(),
            pl.col("home_team").first(),
            pl.col("away_team").first(),
            pl.col("stand").drop_nulls().mode().first().alias("stand"),
            # overall line
            pl.len().alias("Pitches"),
            pl.col("is_pa").sum().alias("PA"),
            pl.col("is_k").sum().alias("K"),
            pl.col("is_bb").sum().alias("BB"),
            pl.col("is_hbp").sum().alias("HBP"),
            pl.col("is_hr").sum().alias("HR"),
            pl.col("is_hit").sum().alias("Hits"),
            pl.col("is_whiff").sum().alias("Whiffs"),
            pl.col("is_called_strike").sum().alias("CS"),
            (pl.col("type") == "X").sum().alias("BIP"),
            # plate discipline (swings, chases, contact, zone)
            *discipline_count_exprs(),
            # splits vs pitcher handedness (for vs-LHP / vs-RHP K%)
            (pl.col("is_pa") & vL).sum().alias("PA_vL"),
            (pl.col("is_k") & vL).sum().alias("K_vL"),
            (pl.col("is_pa") & vR).sum().alias("PA_vR"),
            (pl.col("is_k") & vR).sum().alias("K_vR"),
            # quality
            xwoba_agg(),
            woba_agg(),
        )
        .with_columns(
            (pl.col("CS") + pl.col("Whiffs")).alias("CSW"),
            (pl.col("bat_team") == pl.col("home_team")).alias("is_home"),
            pl.when(pl.col("bat_team") == pl.col("home_team"))
            .then(pl.col("away_team"))
            .otherwise(pl.col("home_team"))
            .alias("opp_team"),
        )
        .sort(["game_date", "game_pk", "batter"])
    )
    return add_plate_discipline_rates(out)
