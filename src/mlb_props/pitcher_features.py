"""Build the per-start pitcher table from pitch-level Statcast (Polars).

This builds the canonical Level 1 pitcher-game spine directly from raw Savant
exports, so every metric is transparent and the keys (`game_pk`, `pitcher`) are
carried for clean downstream joins.

Design goals (per project convention):
- **Polars only** for the heavy group-bys.
- One row per starting-pitcher game (starters identified from the 1st inning).
- Columns grouped into clearly labeled sections so unused metrics are easy to drop.

The sibling module ``batter_features`` produces the per-batter-per-game table.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import polars as pl

from .statcast import (
    FLY_BALL_TYPES,
    add_event_flags,
    add_plate_discipline_flags,
    add_plate_discipline_rates,
    discipline_count_exprs,
    woba_agg,
    xwoba_agg,
    xwoba_num,
)

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------
# Canonical arsenal buckets tracked by the model (others still count in totals).
PITCH_TYPES: tuple[str, ...] = ("ff", "si", "fc", "sl", "st", "cu", "ch")
CANON_PITCH: dict[str, str] = {
    "FF": "ff", "FA": "ff",
    "SI": "si", "FT": "si",
    "FC": "fc",
    "SL": "sl", "SV": "sl",
    "ST": "st",
    "CU": "cu", "KC": "cu", "CS": "cu",
    "CH": "ch",
}

OUTS_ONE = (
    "field_out", "force_out", "sac_fly", "sac_bunt", "strikeout",
    "fielders_choice_out", "fielders_choice", "other_out",
)
OUTS_TWO = ("grounded_into_double_play", "double_play", "sac_fly_double_play", "strikeout_double_play")
OUTS_THREE = ("triple_play",)

# Baserunning outs recorded while the pitcher is on the mound. These are NOT
# plate appearances but they retire the side and therefore count toward IP, so
# they are included in ``Outs`` (which drives IP = Outs/3 for FIP/xFIP and the
# downstream pitcher-outs projection).
OUTS_BR_ONE = (
    "caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home",
    "pickoff_1b", "pickoff_2b", "pickoff_3b",
    "pickoff_caught_stealing_2b", "pickoff_caught_stealing_3b",
    "pickoff_caught_stealing_home",
)
OUTS_BR_TWO = ("runner_double_play",)

# Published FanGraphs FIP constants (``cFIP`` on the Guts! page). These pin
# league-average FIP to league-average ERA and are fixed for completed seasons.
# The in-progress season updates on FanGraphs during the year -- refresh it.
#   Source: https://www.fangraphs.com/tools/guts
FANGRAPHS_FIP_CONSTANT: dict[int, float] = {
    2021: 3.170,
    2022: 3.112,
    2023: 3.255,
    2024: 3.166,
    2025: 3.135,
    2026: 3.099,  # in-progress; refresh from Guts! until the season is final
}

# Columns needed from the raw pitch-level data.
BUILD_COLUMNS: tuple[str, ...] = (
    "game_pk", "game_date", "player_name", "pitcher", "stand", "p_throws",
    "home_team", "away_team", "inning", "inning_topbot",
    "at_bat_number", "pitch_number", "pitch_type", "type", "description",
    "events", "bb_type", "zone",
    "release_speed", "release_spin_rate", "pfx_x", "pfx_z",
    "release_extension", "release_pos_x", "release_pos_z",
    "vy0", "vz0", "ay", "az",
    "estimated_ba_using_speedangle", "estimated_woba_using_speedangle",
    "woba_value", "woba_denom", "bat_score", "post_bat_score",
)


def _pitch_level(df: pl.DataFrame) -> pl.DataFrame:
    """Add shared event flags plus pitcher-specific pitch bucket, VAA, and outs."""
    # Vertical approach angle at the front of the plate (y = 17/12 ft), from the
    # standard y0 = 50 ft trajectory constants (vy0, vz0, ay, az).
    yf = 17.0 / 12.0
    vy_f = -( (pl.col("vy0") ** 2 - 2 * pl.col("ay") * (50.0 - yf)).sqrt() )
    t = (vy_f - pl.col("vy0")) / pl.col("ay")
    vz_f = pl.col("vz0") + pl.col("az") * t
    vaa = -(vz_f / vy_f).arctan() * (180.0 / math.pi)

    return add_plate_discipline_flags(add_event_flags(df)).with_columns(
        pl.col("pitch_type").replace_strict(CANON_PITCH, default=None).alias("canon_pitch"),
        vaa.alias("vaa"),
        (pl.col("pfx_z") * 12.0).alias("ivb"),
        (pl.col("pfx_x") * 12.0).alias("hb"),
        pl.col("bb_type").is_in(FLY_BALL_TYPES).alias("is_fb"),
        (pl.col("bb_type") == "ground_ball").alias("is_gb"),
        pl.when(pl.col("events").is_in(OUTS_THREE)).then(3)
          .when(pl.col("events").is_in(OUTS_TWO)).then(2)
          .when(pl.col("events").is_in(OUTS_BR_TWO)).then(2)
          .when(pl.col("events").is_in(OUTS_ONE)).then(1)
          .when(pl.col("events").is_in(OUTS_BR_ONE)).then(1)
          .otherwise(0).alias("outs_on_play"),
        (pl.col("post_bat_score") - pl.col("bat_score")).alias("run_delta"),
        # Per-PA xwOBA numerator (Savant construction); null on non-terminal pitches.
        xwoba_num().alias("xwoba_num"),
    )

def _starter_keys(df: pl.DataFrame) -> pl.DataFrame:
    """(game_pk, pitcher) pairs for the pitcher who opened each half of inning 1."""
    return (
        df.filter(pl.col("inning") == 1)
        .sort(["game_pk", "inning_topbot", "at_bat_number", "pitch_number"])
        .group_by(["game_pk", "inning_topbot"], maintain_order=True)
        .agg(pl.col("pitcher").first())
        .select("game_pk", "pitcher")
        .unique()
    )


def _arsenal_exprs() -> list[pl.Expr]:
    """Per-pitch-type velo/spin/ivb/hb/vaa, usage vs R/L, thrown flags, results.

    ``_{pt}_woba_num`` / ``_{pt}_woba_den`` / ``_{pt}_xwoba_num`` are helper sums
    (dropped after :func:`build_pitcher_starts` divides them) that yield the
    wOBA and xwOBA allowed on PAs *ending* with each pitch type.
    """
    exprs: list[pl.Expr] = []
    for pt in PITCH_TYPES:
        m = pl.col("canon_pitch") == pt
        exprs += [
            pl.col("release_speed").filter(m).mean().alias(f"{pt}_velo"),
            pl.col("release_spin_rate").filter(m).mean().alias(f"{pt}_spinrate"),
            pl.col("ivb").filter(m).mean().alias(f"{pt}_ivb"),
            pl.col("hb").filter(m).mean().alias(f"{pt}_hb"),
            pl.col("vaa").filter(m).mean().alias(f"{pt}_vaa"),
            (m.sum() > 0).cast(pl.Int8).alias(f"throws_{pt}"),
            # usage vs a handedness = (that pitch to that hand) / (all pitches to that hand)
            (m & (pl.col("stand") == "R")).sum().alias(f"_{pt}_R"),
            (m & (pl.col("stand") == "L")).sum().alias(f"_{pt}_L"),
            # results allowed on PAs ending with this pitch type
            pl.col("woba_value").filter(m).sum().alias(f"_{pt}_woba_num"),
            pl.col("woba_denom").filter(m).sum().alias(f"_{pt}_woba_den"),
            pl.col("xwoba_num").filter(m).sum().alias(f"_{pt}_xwoba_num"),
        ]
    return exprs


def build_pitcher_starts(df: pl.DataFrame, min_batters_faced: int = 9) -> pl.DataFrame:
    """Aggregate pitch-level Statcast into one row per starting-pitcher game.

    Args:
        df: Pitch-level Statcast for one or more seasons.
        min_batters_faced: Keep only "true starts" where the pitcher faced at
            least this many batters (``PA``). This drops **openers** (who face a
            few hitters by design) and starters who exited early due to injury.
            The default of 9 is roughly one full turn through the order; slide
            it in the 7-9 range to see the effect. Pass ``0`` to disable.
    """
    pl_df = _pitch_level(df)
    starters = _starter_keys(pl_df)
    pl_df = pl_df.join(starters, on=["game_pk", "pitcher"], how="inner")

    n_R = (pl.col("stand") == "R").sum()
    n_L = (pl.col("stand") == "L").sum()

    agg = (
        pl_df.group_by(["game_pk", "pitcher"])
        .agg(
            # identity / context
            pl.col("game_date").first(),
            pl.col("game_date").first().dt.year().alias("season"),
            pl.col("player_name").first(),
            pl.col("home_team").first(),
            pl.col("away_team").first(),
            # A starter throws to only one side, so the first half tells us the
            # pitching team (home pitches the Top) and thus the lineup he faces.
            pl.col("inning_topbot").first().alias("_topbot"),
            pl.col("p_throws").first(),
            # volume
            pl.len().alias("Pitches"),
            (pl.col("type") == "S").sum().alias("Strikes"),
            (pl.col("type") == "B").sum().alias("Balls"),
            (pl.col("type") == "X").sum().alias("BIP"),
            pl.col("is_pa").sum().alias("PA"),
            # outcomes
            pl.col("is_k").sum().alias("K"),
            pl.col("is_bb").sum().alias("BB"),
            pl.col("is_hbp").sum().alias("HBP"),
            pl.col("is_hr").sum().alias("HR"),
            pl.col("is_hit").sum().alias("Hits"),
            pl.col("is_whiff").sum().alias("Whiffs"),
            pl.col("is_called_strike").sum().alias("CS"),
            pl.col("is_fb").sum().alias("FB"),
            pl.col("is_gb").sum().alias("GB"),
            pl.col("outs_on_play").sum().alias("Outs"),
            pl.col("run_delta").sum().alias("Runs"),
            # plate discipline induced/allowed (swings, chases, contact, zone)
            *discipline_count_exprs(),
            # release / mechanics: extension (ft toward plate) and release-point
            # consistency (lower stdev = more repeatable slot = better deception)
            pl.col("release_extension").mean().alias("extension"),
            pl.col("release_pos_x").mean().alias("rel_x"),
            pl.col("release_pos_z").mean().alias("rel_z"),
            pl.col("release_pos_x").std().alias("rel_x_sd"),
            pl.col("release_pos_z").std().alias("rel_z_sd"),
            # quality / expected
            pl.col("estimated_ba_using_speedangle").mean().alias("xBA"),
            woba_agg(),
            xwoba_agg(),
            # handedness split denominators
            n_R.alias("_pit_R"),
            n_L.alias("_pit_L"),
            *_arsenal_exprs(),
        )
        .with_columns((pl.col("CS") + pl.col("Whiffs")).alias("CSW"))
    )

    # Convert per-type handedness counts to usage rates and per-type results to
    # wOBA/xwOBA allowed, then drop the helper sum columns.
    derived_exprs = []
    for pt in PITCH_TYPES:
        derived_exprs += [
            pl.when(pl.col("_pit_R") > 0)
            .then(pl.col(f"_{pt}_R") / pl.col("_pit_R"))
            .otherwise(0.0)
            .alias(f"{pt}_usage_vR"),
            pl.when(pl.col("_pit_L") > 0)
            .then(pl.col(f"_{pt}_L") / pl.col("_pit_L"))
            .otherwise(0.0)
            .alias(f"{pt}_usage_vL"),
            pl.when(pl.col(f"_{pt}_woba_den") > 0)
            .then(pl.col(f"_{pt}_woba_num") / pl.col(f"_{pt}_woba_den"))
            .otherwise(None)
            .alias(f"{pt}_woba"),
            pl.when(pl.col(f"_{pt}_woba_den") > 0)
            .then(pl.col(f"_{pt}_xwoba_num") / pl.col(f"_{pt}_woba_den"))
            .otherwise(None)
            .alias(f"{pt}_xwoba"),
        ]
    agg = agg.with_columns(derived_exprs).with_columns(
        (pl.col("_topbot") == "Top").alias("is_home"),
        pl.when(pl.col("_topbot") == "Top")
        .then(pl.col("away_team"))
        .otherwise(pl.col("home_team"))
        .alias("opp_team"),
    )
    helper_cols = (
        ["_pit_R", "_pit_L", "_topbot"]
        + [f"_{pt}_{h}" for pt in PITCH_TYPES for h in ("R", "L")]
        + [f"_{pt}_{s}" for pt in PITCH_TYPES for s in ("woba_num", "woba_den", "xwoba_num")]
    )
    agg = agg.drop(helper_cols)
    agg = add_plate_discipline_rates(agg)

    if min_batters_faced > 0:
        agg = agg.filter(pl.col("PA") >= min_batters_faced)

    return agg.sort(["game_date", "player_name"])


def league_hr_fb_from_pitches(pitches: pl.DataFrame) -> dict[int, float]:
    """Per-season league HR-per-fly-ball from **all** pitches (every pitcher).

    Use the raw pitch-level frame *before* the starter filter so the rate is a
    true league value, not a starters-only one. The fly-ball definition
    (``bb_type in {fly_ball, popup}`` -- FanGraphs includes popups) is the same
    one the per-start ``FB`` column uses, which keeps xFIP internally consistent:
    summed league expected-HR equals summed actual HR regardless of the exact
    classification.
    """
    per = (
        pitches.select("game_date", "events", "bb_type")
        .with_columns(
            pl.col("game_date").cast(pl.Date).dt.year().alias("season"),
            (pl.col("events") == "home_run").alias("_hr"),
            pl.col("bb_type").is_in(FLY_BALL_TYPES).alias("_fb"),
        )
        .group_by("season")
        .agg(pl.col("_hr").sum().alias("HR"), pl.col("_fb").sum().alias("FB"))
        .filter(pl.col("FB") > 0)
    )
    return {int(s): hr / fb for s, hr, fb in per.select("season", "HR", "FB").iter_rows()}


def add_fip_xfip(
    starts: pl.DataFrame,
    fip_constant: Mapping[int, float] | None = None,
    league_hr_fb: Mapping[int, float] | None = None,
    include_constant: bool = True,
) -> pl.DataFrame:
    """Append FanGraphs-scale FIP and xFIP to a per-start pitcher table.

    The metrics' *core* (what discriminates pitchers) uses only the fielding-
    independent events over innings:

    - ``IP``        = ``Outs / 3``
    - ``FIP_core``  = ``(13*HR + 3*(BB+HBP) - 2*K) / IP``
    - ``xFIP_core`` = ``(13*(FB * lgHR/FB) + 3*(BB+HBP) - 2*K) / IP``

    ``FIP = FIP_core + C_season``. The constant does **not** change pitcher
    ordering or spread; it is a single per-season additive offset that pins
    league-average FIP onto the ERA scale.

    Args:
        fip_constant: ``{season: cFIP}`` map. Defaults to the published FanGraphs
            constants (:data:`FANGRAPHS_FIP_CONSTANT`), so FIP/xFIP land on the
            same ERA scale FanGraphs and Baseball Reference use. Seasons missing
            from the map get a null FIP (add them explicitly). Pass your own map
            to override (e.g. a live 2026 value or a self-computed constant).
        league_hr_fb: ``{season: HR/FB}`` map used by the xFIP core. Strongly
            prefer the league-wide value from :func:`league_hr_fb_from_pitches`
            (all pitchers). If omitted, it falls back to a **starters-only** rate
            computed from ``starts`` (biased; fine for quick looks only).
        include_constant: If ``False``, return raw cores (``C_season = 0``).
            Reasonable when FIP/xFIP are only model features, since a per-season
            offset carries no extra signal for a tree model.

    Note on matching FanGraphs: ``IP = Outs/3`` now counts baserunning outs
    (caught stealing / pickoffs) in addition to batting outs, so it tracks true
    innings pitched. Values mirror FanGraphs closely; small residual differences
    come from event-classification edge cases, not from missing outs.
    """
    constants = FANGRAPHS_FIP_CONSTANT if fip_constant is None else fip_constant
    ip = pl.col("Outs") / 3.0
    core_num = 13 * pl.col("HR") + 3 * (pl.col("BB") + pl.col("HBP")) - 2 * pl.col("K")

    # Normalize the join key dtype (dt.year() is Int32; literal test frames Int64).
    starts = starts.with_columns(pl.col("season").cast(pl.Int32))
    seasons = starts.select("season").unique()

    # League HR/FB per season (supplied all-pitcher value preferred).
    if league_hr_fb is None:
        hr_fb_df = starts.group_by("season").agg(
            pl.when(pl.col("FB").sum() > 0)
            .then(pl.col("HR").sum() / pl.col("FB").sum())
            .otherwise(0.0)
            .alias("lg_hr_fb")
        )
    else:
        hr_fb_df = _season_map_to_df(league_hr_fb, "lg_hr_fb")

    # Per-season additive constant.
    if include_constant:
        const_df = _season_map_to_df(constants, "fip_constant")
    else:
        const_df = seasons.with_columns(pl.lit(0.0).alias("fip_constant"))

    league = seasons.join(hr_fb_df, on="season", how="left").join(const_df, on="season", how="left")

    xcore_num = (
        13 * (pl.col("FB") * pl.col("lg_hr_fb"))
        + 3 * (pl.col("BB") + pl.col("HBP"))
        - 2 * pl.col("K")
    )

    return (
        starts.join(league, on="season", how="left")
        .with_columns(
            pl.when(ip > 0).then(core_num / ip + pl.col("fip_constant")).otherwise(None).alias("FIP"),
            pl.when(ip > 0).then(xcore_num / ip + pl.col("fip_constant")).otherwise(None).alias("xFIP"),
        )
        .drop("fip_constant", "lg_hr_fb")
    )


def _season_map_to_df(mapping: Mapping[int, float], value_name: str) -> pl.DataFrame:
    """Turn a ``{season: value}`` map into a two-column frame for joining."""
    return pl.DataFrame(
        {
            "season": [int(s) for s in mapping],
            value_name: [float(v) for v in mapping.values()],
        },
        schema={"season": pl.Int32, value_name: pl.Float64},
    )