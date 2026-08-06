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
    FLY_BALL_TYPES,
    add_event_flags,
    add_plate_discipline_flags,
    add_plate_discipline_rates,
    discipline_count_exprs,
    xwoba_num,
)

STATCAST_FIELD_CENTER_X = 125.42
AIR_BALL_TYPES: tuple[str, ...] = ("fly_ball", "line_drive")

# Columns needed from the raw pitch-level data for the batter table.
BUILD_COLUMNS: tuple[str, ...] = (
    "game_pk", "game_date", "batter", "stand", "p_throws",
    "home_team", "away_team", "inning_topbot",
    "at_bat_number", "events", "description", "type", "zone",
    "pitch_type", "bb_type", "launch_speed", "launch_angle",
    "launch_speed_angle", "estimated_ba_using_speedangle", "hc_x",
    "estimated_woba_using_speedangle", "woba_value", "woba_denom",
    "delta_run_exp",
)


def build_batter_games(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate pitch-level Statcast into one row per (game_pk, batter).

    Note: mid-plate-appearance pinch-hit substitutions can leave the
    original batter with PA = 0 (and K = BB = HBP = 0) in this table.
    Statcast assigns the incoming substitute a new ``at_bat_number`` rather
    than continuing the original batter's count, so the original batter's
    pitches never carry a terminal ``events`` value. This is expected, not
    a data error -- downstream K%/wOBA aggregations must guard against
    division by a zero PA/woba_denom rather than assume PA > 0.
    """
    cleaned = df.with_columns(
        pl.col(column).cast(pl.Float64).fill_nan(None)
        for column in (
            "launch_speed",
            "launch_angle",
            "estimated_ba_using_speedangle",
            "estimated_woba_using_speedangle",
            "woba_value",
            "delta_run_exp",
            "hc_x",
        )
    )
    flagged = add_plate_discipline_flags(add_event_flags(cleaned)).with_columns(
        pl.when(pl.col("inning_topbot") == "Top")
        .then(pl.col("away_team"))
        .otherwise(pl.col("home_team"))
        .alias("bat_team"),
        pl.col("bb_type").is_in(FLY_BALL_TYPES).alias("is_fb"),
        pl.col("bb_type").is_in(AIR_BALL_TYPES).alias("is_air_ball"),
        (
            pl.col("bb_type").is_in(AIR_BALL_TYPES)
            & (
                ((pl.col("stand") == "R") & (pl.col("hc_x") < STATCAST_FIELD_CENTER_X))
                | ((pl.col("stand") == "L") & (pl.col("hc_x") > STATCAST_FIELD_CENTER_X))
            )
        ).alias("is_pull_air"),
        (
            pl.col("is_pa")
            & ~pl.col("is_k")
            & ~pl.col("is_bb")
            & ~pl.col("is_hbp")
            & ~pl.col("is_hr")
            & ~pl.col("events").is_in(["sac_bunt", "catcher_interf"])
        ).alias("is_babip_opportunity"),
        (pl.col("is_hit") & ~pl.col("is_hr")).alias("is_babip_hit"),
        xwoba_num().alias("xwoba_num"),
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
            pl.col("at_bat_number").min().alias("_first_ab"),
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
            pl.col("is_fb").sum().alias("FB"),
            pl.col("is_air_ball").sum().alias("AirBalls"),
            pl.col("is_pull_air").sum().alias("PullAir"),
            pl.col("is_babip_hit").sum().alias("BABIP_num"),
            pl.col("is_babip_opportunity").sum().alias("BABIP_den"),
            (
                (pl.col("type") == "X") & (pl.col("launch_speed") >= 95.0)
            ).sum().alias("HardHit"),
            (
                (pl.col("type") == "X") & (pl.col("launch_speed_angle") == 6)
            ).sum().alias("Barrels"),
            (
                (pl.col("type") == "X")
                & pl.col("launch_angle").is_between(8.0, 32.0, closed="both")
            ).sum().alias("SweetSpot"),
            pl.when(pl.col("type") == "X")
            .then(pl.col("launch_speed"))
            .sum()
            .alias("EV_num"),
            (
                (pl.col("type") == "X") & pl.col("launch_speed").is_not_null()
            ).sum().alias("EV_den"),
            pl.when(pl.col("type") == "X")
            .then(pl.col("launch_angle"))
            .sum()
            .alias("LA_num"),
            (
                (pl.col("type") == "X") & pl.col("launch_angle").is_not_null()
            ).sum().alias("LA_den"),
            pl.when(pl.col("type") == "X")
            .then(pl.col("estimated_ba_using_speedangle"))
            .sum()
            .alias("xBA_num"),
            (
                (pl.col("type") == "X")
                & pl.col("estimated_ba_using_speedangle").is_not_null()
            ).sum().alias("xBA_den"),
            pl.col("woba_value").sum().alias("wOBA_num"),
            pl.col("woba_denom").sum().alias("wOBA_den"),
            pl.col("xwoba_num").sum().alias("xwOBA_num"),
            pl.col("delta_run_exp").sum().alias("RV_num"),
            pl.col("delta_run_exp").is_not_null().sum().alias("RV_den"),
            # plate discipline (swings, chases, contact, zone)
            *discipline_count_exprs(),
            # splits vs pitcher handedness (for vs-LHP / vs-RHP rates)
            (pl.col("is_pa") & vL).sum().alias("PA_vL"),
            (pl.col("is_k") & vL).sum().alias("K_vL"),
            (pl.col("is_bb") & vL).sum().alias("BB_vL"),
            (pl.col("is_pa") & vR).sum().alias("PA_vR"),
            (pl.col("is_k") & vR).sum().alias("K_vR"),
            (pl.col("is_bb") & vR).sum().alias("BB_vR"),
            vL.sum().alias("Pitches_vL"),
            vR.sum().alias("Pitches_vR"),
            (pl.col("is_swing") & vL).sum().alias("Swings_vL"),
            (pl.col("is_swing") & vR).sum().alias("Swings_vR"),
            (pl.col("is_whiff") & vL).sum().alias("Whiffs_vL"),
            (pl.col("is_whiff") & vR).sum().alias("Whiffs_vR"),
            (pl.col("is_in_zone") & vL).sum().alias("InZone_vL"),
            (pl.col("is_in_zone") & vR).sum().alias("InZone_vR"),
            (pl.col("is_zswing") & vL).sum().alias("ZSwings_vL"),
            (pl.col("is_zswing") & vR).sum().alias("ZSwings_vR"),
            (pl.col("is_zcontact") & vL).sum().alias("ZContacts_vL"),
            (pl.col("is_zcontact") & vR).sum().alias("ZContacts_vR"),
        )
        .sort(["game_pk", "bat_team", "_first_ab", "batter"])
        .with_columns(
            (pl.col("CS") + pl.col("Whiffs")).alias("CSW"),
            (pl.col("bat_team") == pl.col("home_team")).alias("is_home"),
            pl.col("_first_ab")
            .rank("ordinal")
            .over(["game_pk", "bat_team"])
            .cast(pl.Int8)
            .alias("lineup_slot"),
            pl.when(pl.col("bat_team") == pl.col("home_team"))
            .then(pl.col("away_team"))
            .otherwise(pl.col("home_team"))
            .alias("opp_team"),
        )
        .with_columns(
            (pl.col("lineup_slot") <= 9).alias("is_initial_lineup"),
        )
        .drop("_first_ab")
        .sort(["game_date", "game_pk", "batter"])
    )
    return add_plate_discipline_rates(out).with_columns(
        pl.when(pl.col("BABIP_den") > 0)
        .then(pl.col("BABIP_num") / pl.col("BABIP_den"))
        .otherwise(None)
        .alias("babip"),
        pl.when(pl.col("EV_den") > 0)
        .then(pl.col("HardHit") / pl.col("EV_den"))
        .otherwise(None)
        .alias("hard_hit_rate"),
        pl.when(pl.col("xBA_den") > 0)
        .then(pl.col("Barrels") / pl.col("xBA_den"))
        .otherwise(None)
        .alias("barrel_rate"),
        pl.when(pl.col("LA_den") > 0)
        .then(pl.col("SweetSpot") / pl.col("LA_den"))
        .otherwise(None)
        .alias("sweet_spot_rate"),
        pl.when(pl.col("EV_den") > 0)
        .then(pl.col("EV_num") / pl.col("EV_den"))
        .otherwise(None)
        .alias("avg_exit_velocity"),
        pl.when(pl.col("LA_den") > 0)
        .then(pl.col("LA_num") / pl.col("LA_den"))
        .otherwise(None)
        .alias("avg_launch_angle"),
        pl.when(pl.col("xBA_den") > 0)
        .then(pl.col("xBA_num") / pl.col("xBA_den"))
        .otherwise(None)
        .alias("xBA"),
        pl.when(pl.col("wOBA_den") > 0)
        .then(pl.col("wOBA_num") / pl.col("wOBA_den"))
        .otherwise(None)
        .alias("wOBA"),
        pl.when(pl.col("wOBA_den") > 0)
        .then(pl.col("xwOBA_num") / pl.col("wOBA_den"))
        .otherwise(None)
        .alias("xwOBA"),
        pl.when(pl.col("FB") > 0)
        .then(pl.col("HR") / pl.col("FB"))
        .otherwise(None)
        .alias("hr_fb_rate"),
        pl.when(pl.col("BIP") > 0)
        .then(pl.col("FB") / pl.col("BIP"))
        .otherwise(None)
        .alias("fb_rate"),
        pl.when(pl.col("BIP") > 0)
        .then(pl.col("PullAir") / pl.col("BIP"))
        .otherwise(None)
        .alias("pull_air_rate"),
        pl.when(pl.col("RV_den") > 0)
        .then(100.0 * pl.col("RV_num") / pl.col("RV_den"))
        .otherwise(None)
        .alias("rv_per_100"),
    )
