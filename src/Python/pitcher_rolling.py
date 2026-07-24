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
DEFAULT_MEAN_WINDOWS: tuple[int, ...] = (3, 5, 10)
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
    if starts.select("pitcher", "game_pk").is_duplicated().any():
        raise ValueError("starts contains duplicate (pitcher, game_pk) keys")

    rate_windows, mean_windows = list(rate_windows), list(mean_windows)
    rate_stats = {
        name: (num, den)
        for name, (num, den) in rate_stats.items()
        if num in starts.columns and den in starts.columns
    }
    mean_cols = [c for c in mean_cols if c in starts.columns]

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
    return df.sort(_ORDER)
