"""Leakage-safe rolling / season-to-date pitcher features (Polars).

The pitcher-side companion to :mod:`batter_rolling`. It turns the per-start
pitcher table (:func:`pitcher_features.build_pitcher_starts`) into **pregame**
features: for any start ``G`` every value uses only starts *strictly before*
``G`` for that pitcher. Keeping this logic in a tested module makes the pitcher
spine feeding Level 3 reproducible.

Two flavors, mirroring the batter side:

1. **Rolling last-N starts** (``{name}_P{w}``): PA/pitch-weighted for rate stats,
   simple mean for physics/rate columns. The current start and every other
   start on the same calendar date are excluded, so doubleheader ordering
   cannot leak outcomes.
2. **Season-to-date** (``{name}_std``): expanding, resets each season, for the
   rate stats.

Rate stats are defined as ``(numerator, denominator)`` count pairs so the rolled
value is a properly weighted rate (``Σnum / Σden``), not an average of ratios.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import polars as pl

from .pitcher_features import FANGRAPHS_FIP_CONSTANT, PITCH_TYPES, siera_mlb_expr

_ORDER: tuple[str, ...] = ("pitcher", "game_date", "game_pk")

# Rate features -> (numerator_count, denominator_count) on the per-start table.
DEFAULT_RATE_STATS: dict[str, tuple[str, str]] = {
    "k_rate": ("K", "PA"),
    "bb_rate": ("BB", "PA"),
    "csw_rate": ("CSW", "Pitches"),
    "swstr_rate": ("Whiffs", "Pitches"),   # whiffs per pitch
    "whiff_rate": ("Whiffs", "Swings"),    # whiffs per swing
    "ball_rate": ("Balls", "Pitches"),
    "cs_rate": ("CS", "Pitches"),
    "chase_rate": ("Chases", "OutZone"),
    "zone_rate": ("InZone", "Pitches"),
    "contact_rate": ("Contacts", "Swings"),
    "zswing_rate": ("ZSwings", "InZone"),
    "swing_rate": ("Swings", "Pitches"),
    "zcontact_rate": ("ZContacts", "ZSwings"),
    "gb_rate": ("GB", "BIP"),
    "hr_rate": ("HR", "PA"),
    "bip_rate": ("BIP", "Pitches"),
    "babip": ("BABIP_num", "BABIP_den"),
    "first_pitch_strike_rate": ("FirstPitchStrikes", "FirstPitches"),
    "ahead_rate": ("AheadPitches", "Pitches"),
    "behind_rate": ("BehindPitches", "Pitches"),
    "two_strike_reach_rate": ("TwoStrikePA", "PA"),
    "putaway_rate": ("PutAwayK", "TwoStrikePitches"),
    "xBA": ("xBA_num", "xBA_den"),
    "wOBA": ("wOBA_num", "wOBA_den"),
    "xwOBA": ("xwOBA_num", "wOBA_den"),
}

# Per-start values rolled with a simple mean (physics, mechanics, and usage).
_PITCH_TYPES: tuple[str, ...] = PITCH_TYPES
DEFAULT_MEAN_COLS: tuple[str, ...] = (
    *(f"{pt}_{m}" for pt in _PITCH_TYPES for m in ("velo", "spinrate", "ivb", "hb", "vaa")),
    *(f"{pt}_usage_v{h}" for pt in _PITCH_TYPES for h in ("R", "L")),
    "extension", "rel_x", "rel_z", "rel_x_sd", "rel_z_sd",
)

DEFAULT_RATE_WINDOWS: tuple[int, ...] = (5, 10, 20)
# P1 added for Step 9c physics form (mid-season arsenal changes); production
# registry swaps five stems onto P1 and drops their P3/P5 (see registries.py).
DEFAULT_MEAN_WINDOWS: tuple[int, ...] = (1, 3, 5, 10)
# Lagged starter volume for the projected-TBF spine (pregame means of prior starts).
DEFAULT_WORKLOAD_COLS: tuple[str, ...] = ("PA", "Outs", "Pitches")
DEFAULT_WORKLOAD_WINDOWS: tuple[int, ...] = (5, 10, 20)
DEFAULT_REST_LONG_GAP_DAYS: int = 15
_FIP_COUNTS: tuple[str, ...] = ("HR", "BB", "HBP", "K", "FB", "Outs")
_SIERA_COUNTS: tuple[str, ...] = ("K", "BB", "GB", "OFB", "PU", "PA")


def _prior_rate(num: str, den: str, by: list[str]) -> pl.Expr:
    """Expanding rate over prior rows only (cumulative minus current)."""
    prior_num = pl.col(num).cum_sum().over(by) - pl.col(num)
    prior_den = pl.col(den).cum_sum().over(by) - pl.col(den)
    return pl.when(prior_den > 0).then(prior_num / prior_den).otherwise(None)


def add_prior_season_shrunk_k(
    starts: pl.DataFrame,
    *,
    prior_strength_pa: float,
    fallback_league_k_rate: float | None = None,
) -> pl.DataFrame:
    """Add a leakage-safe, prior-season-shrunk pitcher K rate.

    The estimate combines current-season counts strictly before the projected
    date with ``prior_strength_pa`` pseudo-PA at the pitcher's completed
    previous-season K rate. Pitchers without previous-season MLB starts use the
    completed previous-season league starter rate. The first loaded season uses
    ``fallback_league_k_rate`` or remains null.

    This function is intentionally separate from
    :func:`add_rolling_pitcher_features`: callers must opt in explicitly, and
    the feature is not automatically added to Level 2 or Level 3.
    """
    if prior_strength_pa <= 0:
        raise ValueError("prior_strength_pa must be positive")
    required = {"pitcher", "game_pk", "game_date", "K", "PA"}
    missing = sorted(required - set(starts.columns))
    if missing:
        raise ValueError(f"starts is missing shrinkage columns: {missing}")
    if starts.select("pitcher", "game_pk").is_duplicated().any():
        raise ValueError("starts contains duplicate (pitcher, game_pk) keys")

    df = starts.with_columns(
        pl.col("game_date").cast(pl.Date),
        pl.col("game_date").cast(pl.Date).dt.year().alias("season"),
    ).sort(_ORDER)

    pitcher_prior = (
        df.group_by("pitcher", "season")
        .agg(
            pl.col("K").sum().alias("_prior_season_k"),
            pl.col("PA").sum().alias("_prior_season_pa"),
        )
        .with_columns((pl.col("season") + 1).alias("season"))
        .with_columns(
            pl.when(pl.col("_prior_season_pa") > 0)
            .then(pl.col("_prior_season_k") / pl.col("_prior_season_pa"))
            .otherwise(None)
            .alias("_pitcher_prior_rate")
        )
        .select("pitcher", "season", "_pitcher_prior_rate")
    )
    league_prior = (
        df.group_by("season")
        .agg(
            pl.col("K").sum().alias("_league_k"),
            pl.col("PA").sum().alias("_league_pa"),
        )
        .with_columns((pl.col("season") + 1).alias("season"))
        .with_columns(
            pl.when(pl.col("_league_pa") > 0)
            .then(pl.col("_league_k") / pl.col("_league_pa"))
            .otherwise(None)
            .alias("_league_prior_rate")
        )
        .select("season", "_league_prior_rate")
    )

    current_prior_k = pl.col("K").cum_sum().over(["pitcher", "season"]) - pl.col("K")
    current_prior_pa = (
        pl.col("PA").cum_sum().over(["pitcher", "season"]) - pl.col("PA")
    )
    fallback = pl.lit(fallback_league_k_rate, dtype=pl.Float64)
    return (
        df.join(pitcher_prior, on=["pitcher", "season"], how="left")
        .join(league_prior, on="season", how="left")
        .with_columns(
            current_prior_k.alias("_current_prior_k"),
            current_prior_pa.alias("_current_prior_pa"),
        )
        .with_columns(
            pl.col("_current_prior_k")
            .first()
            .over(["pitcher", "game_date"]),
            pl.col("_current_prior_pa")
            .first()
            .over(["pitcher", "game_date"]),
            pl.coalesce(
                "_pitcher_prior_rate",
                "_league_prior_rate",
                fallback,
            ).alias("_shrink_prior_rate"),
        )
        .with_columns(
            (
                (
                    pl.col("_current_prior_k")
                    + prior_strength_pa * pl.col("_shrink_prior_rate")
                )
                / (pl.col("_current_prior_pa") + prior_strength_pa)
            ).alias("k_rate_std_shrunk")
        )
        .drop(
            "_pitcher_prior_rate",
            "_league_prior_rate",
            "_current_prior_k",
            "_current_prior_pa",
            "_shrink_prior_rate",
        )
        .sort(_ORDER)
    )


def _rolling_rate(num: str, den: str, window: int, min_games: int) -> pl.Expr:
    """PA/pitch-weighted rate over the previous ``window`` starts (current excluded)."""
    roll_num = pl.col(num).shift(1).rolling_sum(window_size=window, min_samples=min_games).over("pitcher")
    roll_den = pl.col(den).shift(1).rolling_sum(window_size=window, min_samples=min_games).over("pitcher")
    return pl.when(roll_den > 0).then(roll_num / roll_den).otherwise(None)


def _rolling_mean(col: str, window: int, min_games: int) -> pl.Expr:
    """Mean of a per-start column over the previous ``window`` starts (current excluded)."""
    return pl.col(col).shift(1).rolling_mean(window_size=window, min_samples=min_games).over("pitcher")


def add_starter_rest_features(
    starts: pl.DataFrame,
    *,
    long_gap_days: int = DEFAULT_REST_LONG_GAP_DAYS,
) -> pl.DataFrame:
    """Add leakage-safe in-season rest features for starter appearances.

    Rest is computed from our starter calendar within season (not Savant rest).
    Season debuts are null rest + ``is_season_debut=1`` (no offseason carry).
    Gaps longer than ``long_gap_days`` are capped and flagged as long gaps, with
    ``rest_gap_severity`` (0–3) distinguishing short IL-ish gaps from long rehab.
    ``is_career_mlb_debut`` flags the first starter row in the loaded MLB history
    (no minor-league stats). Same-calendar-date starts share the first-row rest
    values so doubleheaders do not invent zero-day rest from each other.
    """
    if long_gap_days <= 0:
        raise ValueError("long_gap_days must be positive")
    required = {"pitcher", "game_pk", "game_date"}
    missing = sorted(required - set(starts.columns))
    if missing:
        raise ValueError(f"starts is missing rest columns: {missing}")
    if starts.select("pitcher", "game_pk").is_duplicated().any():
        raise ValueError("starts contains duplicate (pitcher, game_pk) keys")

    df = starts.with_columns(
        pl.col("game_date").cast(pl.Date),
        pl.col("game_date").cast(pl.Date).dt.year().alias("season"),
    ).sort(_ORDER)

    prev_date = pl.col("game_date").shift(1).over(["pitcher", "season"])
    days_rest = (pl.col("game_date") - prev_date).dt.total_days()
    df = df.with_columns(
        days_rest.alias("__days_rest_raw"),
        prev_date.is_null().cast(pl.Int8).alias("__is_season_debut"),
    ).with_columns(
        pl.col("__days_rest_raw").first().over(["pitcher", "game_date"]),
        pl.col("__is_season_debut").first().over(["pitcher", "game_date"]),
    ).with_columns(
        pl.when(pl.col("__is_season_debut") == 1)
        .then(None)
        .otherwise(pl.col("__days_rest_raw"))
        .alias("days_rest"),
        pl.col("__is_season_debut").alias("is_season_debut"),
    ).with_columns(
        pl.when(pl.col("days_rest").is_null())
        .then(None)
        .otherwise(pl.min_horizontal(pl.col("days_rest"), pl.lit(long_gap_days)))
        .alias("days_rest_capped"),
        pl.when(pl.col("days_rest").is_null())
        .then(pl.lit(0, dtype=pl.Int8))
        .otherwise((pl.col("days_rest") > long_gap_days).cast(pl.Int8))
        .alias("rest_is_long_gap"),
    ).with_columns(
        # 0 = normal/debut; 1 = 16-35d; 2 = 36-60d; 3 = 61+d (TJ / long rehab).
        pl.when(pl.col("days_rest").is_null() | (pl.col("rest_is_long_gap") == 0))
        .then(pl.lit(0, dtype=pl.Int8))
        .when(pl.col("days_rest") <= 35)
        .then(pl.lit(1, dtype=pl.Int8))
        .when(pl.col("days_rest") <= 60)
        .then(pl.lit(2, dtype=pl.Int8))
        .otherwise(pl.lit(3, dtype=pl.Int8))
        .alias("rest_gap_severity"),
        # First starter row in the loaded history (MLB-only; no MiLB). Early
        # seasons in a short window will over-flag true veterans — acceptable.
        pl.col("game_date")
        .shift(1)
        .over("pitcher")
        .is_null()
        .cast(pl.Int8)
        .alias("__is_career_mlb_debut"),
    ).with_columns(
        pl.col("__is_career_mlb_debut")
        .first()
        .over(["pitcher", "game_date"])
        .alias("is_career_mlb_debut"),
    ).drop("__days_rest_raw", "__is_season_debut", "__is_career_mlb_debut")
    return df.sort(_ORDER)


def _add_rolling_fip(
    df: pl.DataFrame,
    windows: list[int],
    min_games: int,
    min_outs: int = 9,
) -> pl.DataFrame:
    """Add denominator-weighted FIP/xFIP over prior starts."""
    required = {*_FIP_COUNTS, "lg_hr_fb_prior", "season"}
    if not required.issubset(df.columns):
        return df

    temporary = [
        (column, window, f"__fip_{column}_{window}")
        for window in windows
        for column in _FIP_COUNTS
    ]
    df = df.with_columns(
        pl.col(column)
        .shift(1)
        .rolling_sum(window_size=window, min_samples=min_games)
        .over("pitcher")
        .alias(temp)
        for column, window, temp in temporary
    ).with_columns(
        pl.col(temp)
        .first()
        .over(["pitcher", "game_date"])
        .alias(temp)
        for _column, _window, temp in temporary
    )

    constant = pl.col("season").replace_strict(
        FANGRAPHS_FIP_CONSTANT,
        default=None,
        return_dtype=pl.Float64,
    )
    expressions: list[pl.Expr] = []
    for window in windows:
        values = {
            column: pl.col(f"__fip_{column}_{window}").cast(pl.Float64)
            for column in _FIP_COUNTS
        }
        ip = values["Outs"] / 3.0
        base = 3 * (values["BB"] + values["HBP"]) - 2 * values["K"]
        valid = (values["Outs"] >= min_outs) & constant.is_not_null()
        expressions.extend(
            [
                pl.when(valid)
                .then((13 * values["HR"] + base) / ip + constant)
                .otherwise(None)
                .alias(f"FIP_P{window}"),
                pl.when(valid & pl.col("lg_hr_fb_prior").is_not_null())
                .then(
                    (
                        13 * values["FB"] * pl.col("lg_hr_fb_prior")
                        + base
                    )
                    / ip
                    + constant
                )
                .otherwise(None)
                .alias(f"xFIP_P{window}"),
            ]
        )
    return df.with_columns(expressions).drop(
        [temp for _column, _window, temp in temporary]
    )


def _rolling_sum_column(
    column: str,
    window: int,
    min_games: int,
    *,
    over: str | list[str] = "pitcher",
) -> pl.Expr:
    return (
        pl.col(column)
        .shift(1)
        .rolling_sum(window_size=window, min_samples=min_games)
        .over(over)
    )


def _add_rolling_arsenal(
    df: pl.DataFrame,
    min_games: int,
) -> pl.DataFrame:
    """Add requested prior-two-start arsenal presence and weighted usage."""
    specs: list[tuple[pl.Expr, str]] = []
    for pitch_type in _PITCH_TYPES:
        thrown = f"throws_{pitch_type}"
        pitches = f"{pitch_type}_pitches"
        if thrown in df.columns:
            specs.append(
                (
                    pl.col(thrown)
                    .shift(1)
                    .rolling_max(window_size=2, min_samples=min_games)
                    .over("pitcher")
                    .cast(pl.Int8),
                    f"has_thrown_{pitch_type}_P2",
                )
            )
        if pitches in df.columns and "Pitches" in df.columns:
            numerator = _rolling_sum_column(pitches, 2, min_games)
            denominator = _rolling_sum_column("Pitches", 2, min_games)
            specs.append(
                (
                    pl.when(denominator > 0)
                    .then(numerator / denominator)
                    .otherwise(None),
                    f"{pitch_type}_usage_P2",
                )
            )
    if not specs:
        return df
    temporary = [f"__arsenal_{index}" for index in range(len(specs))]
    return (
        df.with_columns(
            expr.alias(temp)
            for temp, (expr, _name) in zip(temporary, specs, strict=True)
        )
        .with_columns(
            pl.col(temp).first().over(["pitcher", "game_date"]).alias(name)
            for temp, (_expr, name) in zip(temporary, specs, strict=True)
        )
        .drop(temporary)
    )


def _add_rolling_arm_angle(
    df: pl.DataFrame,
    windows: list[int],
    min_games: int,
) -> pl.DataFrame:
    if not {"arm_angle_num", "arm_angle_den"}.issubset(df.columns):
        return df
    specs: list[tuple[pl.Expr, str]] = []
    for window in windows:
        numerator = _rolling_sum_column("arm_angle_num", window, min_games)
        denominator = _rolling_sum_column("arm_angle_den", window, min_games)
        specs.append(
            (
                pl.when(denominator > 0)
                .then(numerator / denominator)
                .otherwise(None),
                f"arm_angle_P{window}",
            )
        )
    temporary = [f"__arm_angle_{index}" for index in range(len(specs))]
    return (
        df.with_columns(
            expr.alias(temp)
            for temp, (expr, _name) in zip(temporary, specs, strict=True)
        )
        .with_columns(
            pl.col(temp).first().over(["pitcher", "game_date"]).alias(name)
            for temp, (_expr, name) in zip(temporary, specs, strict=True)
        )
        .drop(temporary)
    )


def _add_rolling_siera_and_rv(
    df: pl.DataFrame,
    windows: list[int],
    min_games: int,
) -> pl.DataFrame:
    specs: list[tuple[pl.Expr, str]] = []
    if set(_SIERA_COUNTS).issubset(df.columns):
        for window in windows:
            values = {
                column: _rolling_sum_column(column, window, min_games)
                for column in _SIERA_COUNTS
            }
            specs.append(
                (
                    siera_mlb_expr(
                        values["K"],
                        values["BB"],
                        values["GB"],
                        values["OFB"],
                        values["PU"],
                        values["PA"],
                    ),
                    f"siera_mlb_P{window}",
                )
            )
    if {"RV_num", "RV_den"}.issubset(df.columns):
        for window in windows:
            numerator = _rolling_sum_column("RV_num", window, min_games)
            denominator = _rolling_sum_column("RV_den", window, min_games)
            specs.append(
                (
                    pl.when(denominator > 0)
                    .then(100.0 * numerator / denominator)
                    .otherwise(None),
                    f"rv_per_100_P{window}",
                )
            )
    if not specs:
        return df
    temporary = [f"__composite_{index}" for index in range(len(specs))]
    return (
        df.with_columns(
            expr.alias(temp)
            for temp, (expr, _name) in zip(temporary, specs, strict=True)
        )
        .with_columns(
            pl.col(temp).first().over(["pitcher", "game_date"]).alias(name)
            for temp, (_expr, name) in zip(temporary, specs, strict=True)
        )
        .drop(temporary)
    )


def add_pitch_type_rv_features(
    starts: pl.DataFrame,
    pitch_type_games: pl.DataFrame,
    *,
    prior_strength_pitches: float,
    windows: Iterable[int] = (5, 10, 20),
    min_games: int = 1,
) -> pl.DataFrame:
    """Join empirical-Bayes pitch-type RV candidates onto the start spine.

    The league-by-pitch-type prior uses only dates strictly before the projected
    date. Pitcher counts use complete prior starts, including zero pitches of a
    type, so a five-start window means five starts rather than five appearances
    of that pitch.
    """
    if prior_strength_pitches <= 0:
        raise ValueError("prior_strength_pitches must be positive")
    required_starts = {"game_pk", "pitcher", "game_date"}
    required_types = {
        "game_pk",
        "pitcher",
        "game_date",
        "pitch_type",
        "RV_num",
        "RV_den",
    }
    if missing := sorted(required_starts - set(starts.columns)):
        raise ValueError(f"starts is missing pitch-type RV keys: {missing}")
    if missing := sorted(required_types - set(pitch_type_games.columns)):
        raise ValueError(f"pitch_type_games is missing RV columns: {missing}")

    dates = starts.select("game_pk", "pitcher", "game_date")
    pitch_types = pl.DataFrame({"pitch_type": list(_PITCH_TYPES)})
    grid = (
        dates.join(pitch_types, how="cross")
        .join(
            pitch_type_games.select(
                "game_pk", "pitcher", "pitch_type", "RV_num", "RV_den"
            ),
            on=["game_pk", "pitcher", "pitch_type"],
            how="left",
            validate="1:1",
        )
        .with_columns(
            pl.col("RV_num").fill_null(0.0),
            pl.col("RV_den").fill_null(0),
        )
    )
    daily_totals = pitch_type_games.group_by("pitch_type", "game_date").agg(
        pl.col("RV_num").sum().alias("_daily_rv"),
        pl.col("RV_den").sum().alias("_daily_den"),
    )
    daily = (
        dates.select("game_date")
        .unique()
        .join(pitch_types, how="cross")
        .join(
            daily_totals,
            on=["pitch_type", "game_date"],
            how="left",
            validate="1:1",
        )
        .with_columns(
            pl.col("_daily_rv").fill_null(0.0),
            pl.col("_daily_den").fill_null(0),
        )
        .sort(["pitch_type", "game_date"])
        .with_columns(
            pl.col("_daily_rv")
            .cum_sum()
            .shift(1)
            .over("pitch_type")
            .fill_null(0.0)
            .alias("_league_prior_rv"),
            pl.col("_daily_den")
            .cum_sum()
            .shift(1)
            .over("pitch_type")
            .fill_null(0)
            .alias("_league_prior_den"),
        )
        .select(
            "pitch_type",
            "game_date",
            "_league_prior_rv",
            "_league_prior_den",
        )
    )
    grid = (
        grid.join(daily, on=["pitch_type", "game_date"], how="left")
        .sort(["pitcher", "pitch_type", "game_date", "game_pk"])
        .with_columns(
            pl.when(pl.col("_league_prior_den") > 0)
            .then(pl.col("_league_prior_rv") / pl.col("_league_prior_den"))
            .otherwise(None)
            .alias("_league_prior_mean")
        )
    )

    windows = list(windows)
    specs: list[tuple[pl.Expr, str]] = []
    for window in windows:
        numerator = _rolling_sum_column(
            "RV_num", window, min_games, over=["pitcher", "pitch_type"]
        )
        denominator = _rolling_sum_column(
            "RV_den", window, min_games, over=["pitcher", "pitch_type"]
        )
        specs.append(
            (
                pl.when(pl.col("_league_prior_mean").is_not_null())
                .then(
                    100.0
                    * (
                        numerator
                        + prior_strength_pitches * pl.col("_league_prior_mean")
                    )
                    / (denominator + prior_strength_pitches)
                )
                .otherwise(None),
                f"rv_shrunk_P{window}",
            )
        )
    temporary = [f"__pitch_type_rv_{index}" for index in range(len(specs))]
    grid = (
        grid.with_columns(
            expr.alias(temp)
            for temp, (expr, _name) in zip(temporary, specs, strict=True)
        )
        .with_columns(
            pl.col(temp)
            .first()
            .over(["pitcher", "pitch_type", "game_date"])
            .alias(name)
            for temp, (_expr, name) in zip(temporary, specs, strict=True)
        )
        .drop(temporary)
    )

    out = starts
    for pitch_type in _PITCH_TYPES:
        selected = grid.filter(pl.col("pitch_type") == pitch_type).select(
            "game_pk",
            "pitcher",
            *(
                pl.col(f"rv_shrunk_P{window}").alias(
                    f"{pitch_type}_rv_shrunk_P{window}"
                )
                for window in windows
            ),
        )
        out = out.join(
            selected,
            on=["game_pk", "pitcher"],
            how="left",
            validate="1:1",
        )
    return out


# Per-pitch-type command/stuff-blended rate candidates (Tier 1 research, see
# docs/research/pitch_type_strike_csw_findings.md). Not in DEFAULT_RATE_STATS /
# DEFAULT_MEAN_COLS and not wired into pipeline.rolling.build_pitcher_rolling by
# default -- opt in via add_pitch_type_rate_features until/unless a lift test
# clears the promotion bar.
DEFAULT_PITCH_TYPE_RATE_STATS: dict[str, tuple[str, str]] = {
    # Named "strike"/"csw" (not "strike_rate"/"csw_rate") so per-pitch-type
    # columns don't collide with the reserved deterministic-redundancy naming
    # in features.py (aggregate csw_rate/strike_rate are excluded there as
    # exact algebraic identities of other already-modeled aggregate rates;
    # that identity does not hold per pitch type since we don't yet track
    # per-pitch-type cs_rate/ball_rate to complete it).
    "strike": ("StrikesPlusBIP", "Pitches"),
    "csw": ("CSW", "Pitches"),
    "swstr_rate": ("Whiffs", "Pitches"),
}
DEFAULT_PITCH_TYPE_RATE_WINDOWS: tuple[int, ...] = (5, 10, 20, 30)

# Tier 2 (docs/research/pitch_type_strike_csw_findings.md): per-pitch-type wOBA/xwOBA
# allowed. Denominator is PAs *ending* on that pitch type (not pitches), which is a
# much smaller per-start sample than the Tier-1 rate stats above (median 2-7 per
# start vs. 12-31 pitches/start), so windows run wider and shrinkage matters even
# more. Also opt-in only, via add_pitch_type_rate_features.
DEFAULT_PITCH_TYPE_WOBA_STATS: dict[str, tuple[str, str]] = {
    "wOBA": ("wOBA_num", "wOBA_den"),
    "xwOBA": ("xwOBA_num", "wOBA_den"),
}
DEFAULT_PITCH_TYPE_WOBA_WINDOWS: tuple[int, ...] = (10, 20, 30, 40)


def add_pitch_type_rate_features(
    starts: pl.DataFrame,
    pitch_type_games: pl.DataFrame,
    *,
    stats: Mapping[str, tuple[str, str]] = DEFAULT_PITCH_TYPE_RATE_STATS,
    prior_strength: float,
    windows: Iterable[int] = DEFAULT_PITCH_TYPE_RATE_WINDOWS,
    min_games: int = 1,
    pitch_types: Iterable[str] = _PITCH_TYPES,
) -> pl.DataFrame:
    """Join shrunk + unshrunk per-pitch-type rate candidates onto the start spine.

    Generalizes :func:`add_pitch_type_rv_features` to any numerator/denominator
    rate stat (``strike_rate``, ``csw_rate``, ``swstr_rate``, ...). Per pitch
    type, per ``stat``, per ``window`` this emits two experimental columns:

    - ``{pt}_{stat}_shrunk_P{w}``: empirical-Bayes shrunk toward the pitch-type
      league rate as of strictly prior dates (same recipe as the RV helper --
      ``(Σnum + m·league_prior) / (Σden + m)``).
    - ``{pt}_{stat}_P{w}``: the plain pitch-weighted rolling rate with no
      shrinkage, so a lift test can compare shrunk vs. unshrunk directly and
      confirm shrinkage is pulling its weight for low-usage pitch types.

    The league prior uses only dates strictly before the projected date, and
    pitcher rolling counts use complete prior starts (including zero pitches
    of a type), matching :func:`add_pitch_type_rv_features`.
    """
    if prior_strength <= 0:
        raise ValueError("prior_strength must be positive")
    if not stats:
        raise ValueError("stats must be non-empty")
    required_starts = {"game_pk", "pitcher", "game_date"}
    if missing := sorted(required_starts - set(starts.columns)):
        raise ValueError(f"starts is missing pitch-type rate keys: {missing}")
    required_types = {"game_pk", "pitcher", "game_date", "pitch_type"}
    for num_col, den_col in stats.values():
        required_types |= {num_col, den_col}
    if missing := sorted(required_types - set(pitch_type_games.columns)):
        raise ValueError(f"pitch_type_games is missing rate columns: {missing}")

    pitch_types = list(pitch_types)
    windows = list(windows)
    dates = starts.select("game_pk", "pitcher", "game_date")
    pitch_type_frame = pl.DataFrame({"pitch_type": pitch_types})

    out = starts
    for stat_name, (num_col, den_col) in stats.items():
        grid = (
            dates.join(pitch_type_frame, how="cross")
            .join(
                pitch_type_games.select(
                    "game_pk", "pitcher", "pitch_type", num_col, den_col
                ),
                on=["game_pk", "pitcher", "pitch_type"],
                how="left",
                validate="1:1",
            )
            .with_columns(
                pl.col(num_col).fill_null(0.0),
                pl.col(den_col).fill_null(0),
            )
        )
        daily_totals = pitch_type_games.group_by("pitch_type", "game_date").agg(
            pl.col(num_col).sum().alias("_daily_num"),
            pl.col(den_col).sum().alias("_daily_den"),
        )
        daily = (
            dates.select("game_date")
            .unique()
            .join(pitch_type_frame, how="cross")
            .join(daily_totals, on=["pitch_type", "game_date"], how="left")
            .with_columns(
                pl.col("_daily_num").fill_null(0.0),
                pl.col("_daily_den").fill_null(0),
            )
            .sort(["pitch_type", "game_date"])
            .with_columns(
                pl.col("_daily_num")
                .cum_sum()
                .shift(1)
                .over("pitch_type")
                .fill_null(0.0)
                .alias("_league_prior_num"),
                pl.col("_daily_den")
                .cum_sum()
                .shift(1)
                .over("pitch_type")
                .fill_null(0)
                .alias("_league_prior_den"),
            )
            .select(
                "pitch_type",
                "game_date",
                "_league_prior_num",
                "_league_prior_den",
            )
        )
        grid = (
            grid.join(daily, on=["pitch_type", "game_date"], how="left")
            .sort(["pitcher", "pitch_type", "game_date", "game_pk"])
            .with_columns(
                pl.when(pl.col("_league_prior_den") > 0)
                .then(pl.col("_league_prior_num") / pl.col("_league_prior_den"))
                .otherwise(None)
                .alias("_league_prior_mean")
            )
        )

        specs: list[tuple[pl.Expr, str]] = []
        for window in windows:
            numerator = _rolling_sum_column(
                num_col, window, min_games, over=["pitcher", "pitch_type"]
            )
            denominator = _rolling_sum_column(
                den_col, window, min_games, over=["pitcher", "pitch_type"]
            )
            specs.append(
                (
                    pl.when(pl.col("_league_prior_mean").is_not_null())
                    .then(
                        (numerator + prior_strength * pl.col("_league_prior_mean"))
                        / (denominator + prior_strength)
                    )
                    .otherwise(None),
                    f"{stat_name}_shrunk_P{window}",
                )
            )
            specs.append(
                (
                    pl.when(denominator > 0)
                    .then(numerator / denominator)
                    .otherwise(None),
                    f"{stat_name}_P{window}",
                )
            )
        temporary = [
            f"__pitch_type_rate_{stat_name}_{index}" for index in range(len(specs))
        ]
        grid = (
            grid.with_columns(
                expr.alias(temp)
                for temp, (expr, _name) in zip(temporary, specs, strict=True)
            )
            .with_columns(
                pl.col(temp)
                .first()
                .over(["pitcher", "pitch_type", "game_date"])
                .alias(name)
                for temp, (_expr, name) in zip(temporary, specs, strict=True)
            )
            .drop(temporary)
        )
        for pitch_type in pitch_types:
            selected = grid.filter(pl.col("pitch_type") == pitch_type).select(
                "game_pk",
                "pitcher",
                *(
                    pl.col(name).alias(f"{pitch_type}_{name}")
                    for _expr, name in specs
                ),
            )
            out = out.join(
                selected,
                on=["game_pk", "pitcher"],
                how="left",
                validate="1:1",
            )
    return out


def add_rolling_pitcher_features(
    starts: pl.DataFrame,
    rate_stats: Mapping[str, tuple[str, str]] = DEFAULT_RATE_STATS,
    mean_cols: Iterable[str] = DEFAULT_MEAN_COLS,
    rate_windows: Iterable[int] = DEFAULT_RATE_WINDOWS,
    mean_windows: Iterable[int] = DEFAULT_MEAN_WINDOWS,
    workload_cols: Iterable[str] = DEFAULT_WORKLOAD_COLS,
    workload_windows: Iterable[int] = DEFAULT_WORKLOAD_WINDOWS,
    season_to_date: bool = True,
    min_games: int = 1,
    *,
    add_rest: bool = True,
    rest_long_gap_days: int = DEFAULT_REST_LONG_GAP_DAYS,
) -> pl.DataFrame:
    """Append leakage-safe rolling / season-to-date features to the start table.

    Args:
        starts: Per-start pitcher table (needs ``pitcher, game_date, game_pk`` and
            the numerator/denominator columns referenced by ``rate_stats`` plus
            any ``mean_cols`` present).
        rate_stats: ``{feature: (num_col, den_col)}``. Missing columns are skipped.
        mean_cols: Per-start columns rolled with a simple mean. Missing skipped.
        rate_windows / mean_windows: Rolling window sizes (in starts).
        workload_cols / workload_windows: Lagged starter volume means for TBF
            (``PA_P*``, ``Outs_P*``, ``Pitches_P*``). Missing columns skipped.
        season_to_date: Also emit expanding ``{name}_std`` for each rate stat.
        min_games: Minimum prior starts required to emit a rolling value.
        add_rest: Emit in-season ``days_rest`` / debut / long-gap flags.
        rest_long_gap_days: Cap / flag threshold for unusually long rest gaps.

    Returns:
        ``starts`` (order preserved) with added columns:
            ``season``, ``{rate}_P{w}``, ``{rate}_std`` (if enabled),
            ``{mean_col}_P{w}``, workload ``{col}_P{w}``, and optional rest.
    """
    if starts.select("pitcher", "game_pk").is_duplicated().any():
        raise ValueError("starts contains duplicate (pitcher, game_pk) keys")

    rate_windows, mean_windows = list(rate_windows), list(mean_windows)
    workload_windows = list(workload_windows)
    rate_stats = {
        name: (num, den)
        for name, (num, den) in rate_stats.items()
        if num in starts.columns and den in starts.columns
    }
    mean_cols = [c for c in mean_cols if c in starts.columns]
    workload_cols = [c for c in workload_cols if c in starts.columns]

    df = starts.with_columns(pl.col("game_date").dt.year().alias("season")).sort(_ORDER)

    feature_specs: list[tuple[pl.Expr, str]] = []
    for name, (num, den) in rate_stats.items():
        feature_specs.extend(
            (_rolling_rate(num, den, w, min_games), f"{name}_P{w}")
            for w in rate_windows
        )
        if season_to_date:
            feature_specs.append(
                (_prior_rate(num, den, ["pitcher", "season"]), f"{name}_std")
            )

    feature_specs.extend(
        (_rolling_mean(col, w, min_games), f"{col}_P{w}")
        for col in mean_cols
        for w in mean_windows
    )
    feature_specs.extend(
        (_rolling_mean(col, w, min_games), f"{col}_P{w}")
        for col in workload_cols
        for w in workload_windows
    )

    temporary = [f"__pregame_{index}" for index in range(len(feature_specs))]
    df = df.with_columns(
        expr.alias(column)
        for column, (expr, _name) in zip(temporary, feature_specs, strict=True)
    )
    df = df.with_columns(
        pl.col(column)
        .first()
        .over(["pitcher", "game_date"])
        .alias(name)
        for column, (_expr, name) in zip(temporary, feature_specs, strict=True)
    )
    df = df.drop(temporary)
    df = _add_rolling_arsenal(df, min_games)
    df = _add_rolling_arm_angle(df, mean_windows, min_games)
    df = _add_rolling_siera_and_rv(df, mean_windows, min_games)
    df = _add_rolling_fip(df, mean_windows, min_games)
    if add_rest:
        df = add_starter_rest_features(df, long_gap_days=rest_long_gap_days)
    return df.sort(_ORDER)
