"""Team bullpen workload features for the projected-TBF spine (Phase C).

Bullpen = anyone who pitched in a game who is **not** that game's 1st-inning
starter.

Architecture:
- Intermediate **appearance log** (one row per reliever outing) is staging data —
  useful for EDA and for building flats. It is **not** a model input.
- Model inputs are **flat** prior-only team aggregates (L1d / L2d / L3d).
  Ridge / ElasticNet / Poisson / LightGBM cannot consume nested
  ``[(name, hand, pitches), ...]`` lists; encode that information as scalars
  (hand splits, B2B arms, max outing, etc.).

Same-game bullpen usage never enters features — lookbacks use
``game_date < starter.game_date`` only.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

import polars as pl

from .pitcher_features import _starter_keys

DEFAULT_BULLPEN_LOOKBACK_DAYS: tuple[int, ...] = (1, 2, 3)
HEAVY_OUTING_PITCHES: int = 30

_BULLPEN_REQUIRED_RAW = (
    "game_pk",
    "game_date",
    "pitcher",
    "p_throws",
    "home_team",
    "away_team",
    "inning",
    "inning_topbot",
    "at_bat_number",
    "pitch_number",
)

# Flat lookback column stems (suffixed with _L{W}d).
_LOOKBACK_METRICS: tuple[str, ...] = (
    "bullpen_pitches",
    "bullpen_pitchers_used",
    "bullpen_unique_arms",
    "bullpen_appearances",
    "bullpen_L_pitches",
    "bullpen_R_pitches",
    "bullpen_b2b_arms",
    "bullpen_max_pitches",
    "bullpen_heavy_outings",
)


def build_bullpen_appearances(raw: pl.DataFrame) -> pl.DataFrame:
    """Non-starter outings: one row per ``(game_pk, team, pitcher)``.

    This nested/long table is an intermediate event log for feature construction
    and debugging — not a LightGBM/Ridge feature column.
    """
    missing = sorted(set(_BULLPEN_REQUIRED_RAW) - set(raw.columns))
    if missing:
        raise ValueError(f"raw is missing bullpen columns: {missing}")

    df = raw.select(_BULLPEN_REQUIRED_RAW).with_columns(
        pl.col("game_date").cast(pl.Date),
        pl.when(pl.col("inning_topbot") == "Top")
        .then(pl.col("home_team"))
        .otherwise(pl.col("away_team"))
        .alias("team"),
    )
    starters = _starter_keys(df).with_columns(
        pl.lit(1, dtype=pl.Int8).alias("is_starter")
    )
    return (
        df.group_by(["game_pk", "pitcher", "team"])
        .agg(
            pl.col("game_date").first(),
            pl.col("p_throws").first(),
            pl.len().alias("pitches"),
        )
        .join(starters, on=["game_pk", "pitcher"], how="left")
        .with_columns(pl.col("is_starter").fill_null(0).cast(pl.Int8))
        .filter(pl.col("is_starter") == 0)
        .drop("is_starter")
        .with_columns(pl.col("game_date").dt.year().alias("season"))
        .sort(["team", "game_date", "game_pk", "pitcher"])
    )


def _daily_arm_usage(appearances: pl.DataFrame) -> pl.DataFrame:
    """Per ``(team, pitcher, game_date)`` pitch totals + back-to-back flag."""
    daily = (
        appearances.with_columns(pl.col("game_date").cast(pl.Date))
        .group_by(["team", "pitcher", "game_date"])
        .agg(
            pl.col("pitches").sum().alias("pitches"),
            pl.col("p_throws").first(),
            pl.len().alias("appearances"),
        )
        .sort(["team", "pitcher", "game_date"])
    )
    prev = daily.select(
        "team",
        "pitcher",
        pl.col("game_date").alias("prev_date"),
        pl.lit(1, dtype=pl.Int8).alias("pitched_prev"),
    )
    return (
        daily.with_columns((pl.col("game_date") - timedelta(days=1)).alias("prev_date"))
        .join(prev, on=["team", "pitcher", "prev_date"], how="left")
        .with_columns(pl.col("pitched_prev").fill_null(0).cast(pl.Int8).alias("is_b2b"))
        .drop("prev_date", "pitched_prev")
    )


def build_bullpen_team_games(raw: pl.DataFrame) -> pl.DataFrame:
    """Aggregate non-starter pitch volume to one row per ``(game_pk, team)``.

    Teams that use no bullpen (complete game) still appear with zeros so
    lookbacks treat an off-day / CG correctly.
    """
    appearances = build_bullpen_appearances(raw)
    daily_arms = _daily_arm_usage(appearances)

    # Map daily-arm B2B onto game-level outings via (team, pitcher, game_date).
    apps = appearances.join(
        daily_arms.select("team", "pitcher", "game_date", "is_b2b"),
        on=["team", "pitcher", "game_date"],
        how="left",
    ).with_columns(pl.col("is_b2b").fill_null(0))

    team_usage = apps.group_by(["game_pk", "team"]).agg(
        pl.col("game_date").first(),
        pl.col("pitcher").n_unique().alias("bullpen_pitchers_used"),
        pl.col("pitcher").len().alias("bullpen_appearances"),
        pl.col("pitches").sum().alias("bullpen_pitches"),
        pl.col("pitches")
        .filter(pl.col("p_throws") == "L")
        .sum()
        .fill_null(0)
        .alias("bullpen_L_pitches"),
        pl.col("pitches")
        .filter(pl.col("p_throws") == "R")
        .sum()
        .fill_null(0)
        .alias("bullpen_R_pitches"),
        pl.col("pitcher")
        .filter(pl.col("is_b2b") == 1)
        .n_unique()
        .alias("bullpen_b2b_arms"),
        pl.col("pitches").max().alias("bullpen_max_pitches"),
        (pl.col("pitches") >= HEAVY_OUTING_PITCHES)
        .sum()
        .alias("bullpen_heavy_outings"),
    )

    df = raw.select(
        "game_pk", "game_date", "home_team", "away_team"
    ).unique(subset=["game_pk"])
    game_meta = df.with_columns(pl.col("game_date").cast(pl.Date))
    universe = pl.concat(
        [
            game_meta.select(
                "game_pk",
                "game_date",
                pl.col("home_team").alias("team"),
            ),
            game_meta.select(
                "game_pk",
                "game_date",
                pl.col("away_team").alias("team"),
            ),
        ]
    )

    zero_int = [
        "bullpen_pitchers_used",
        "bullpen_appearances",
        "bullpen_pitches",
        "bullpen_L_pitches",
        "bullpen_R_pitches",
        "bullpen_b2b_arms",
        "bullpen_max_pitches",
        "bullpen_heavy_outings",
    ]
    return (
        universe.join(
            team_usage.drop("game_date"),
            on=["game_pk", "team"],
            how="left",
        )
        .with_columns([pl.col(c).fill_null(0).cast(pl.Int32) for c in zero_int])
        .with_columns(pl.col("game_date").cast(pl.Date).dt.year().alias("season"))
        .sort(["team", "game_date", "game_pk"])
    )


def pitcher_team_expr() -> pl.Expr:
    """Team the starter pitches for (not ``opp_team``)."""
    return (
        pl.when(pl.col("is_home"))
        .then(pl.col("home_team"))
        .otherwise(pl.col("away_team"))
        .alias("pitcher_team")
    )


def add_bullpen_lookback_features(
    starts: pl.DataFrame,
    bullpen_team_games: pl.DataFrame,
    *,
    windows_days: Iterable[int] = DEFAULT_BULLPEN_LOOKBACK_DAYS,
    appearances: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Join prior-only team bullpen aggregates onto starter rows.

    For window ``W``, aggregates cover the starter's team games with
    ``game_date`` in ``[asof - W, asof)``. Missing windows fill with 0.

    When ``appearances`` is provided, ``bullpen_unique_arms_L*`` is the true
    distinct-arm count in the window (preferred over summing per-game uniques).
    """
    windows = sorted({int(w) for w in windows_days})
    if not windows or any(w <= 0 for w in windows):
        raise ValueError("windows_days must be positive integers")

    required_starts = {
        "game_pk",
        "game_date",
        "pitcher",
        "home_team",
        "away_team",
        "is_home",
    }
    missing_starts = sorted(required_starts - set(starts.columns))
    if missing_starts:
        raise ValueError(f"starts is missing bullpen join columns: {missing_starts}")

    team_metrics = [
        "bullpen_pitches",
        "bullpen_pitchers_used",
        "bullpen_appearances",
        "bullpen_L_pitches",
        "bullpen_R_pitches",
        "bullpen_b2b_arms",
        "bullpen_max_pitches",
        "bullpen_heavy_outings",
    ]
    required_bp = {"game_pk", "game_date", "team", *team_metrics}
    missing_bp = sorted(required_bp - set(bullpen_team_games.columns))
    if missing_bp:
        raise ValueError(f"bullpen_team_games is missing columns: {missing_bp}")

    daily = (
        bullpen_team_games.with_columns(pl.col("game_date").cast(pl.Date))
        .group_by(["team", "game_date"])
        .agg(
            *[
                (
                    pl.col(col).max()
                    if col == "bullpen_max_pitches"
                    else pl.col(col).sum()
                ).alias(col)
                for col in team_metrics
            ]
        )
        .rename({"team": "pitcher_team", "game_date": "bp_date"})
    )

    out = starts.with_columns(
        pl.col("game_date").cast(pl.Date),
        pitcher_team_expr(),
    )
    keys = ["pitcher", "game_pk"]

    arm_daily = None
    if appearances is not None:
        arm_daily = (
            _daily_arm_usage(appearances)
            .select("team", "pitcher", "game_date")
            .rename({"team": "pitcher_team", "game_date": "bp_date", "pitcher": "bp_pitcher"})
        )

    for window in windows:
        agg_exprs = []
        rename_map = {}
        for col in team_metrics:
            name = f"{col}_L{window}d"
            rename_map[col] = name
            if col == "bullpen_max_pitches":
                agg_exprs.append(pl.col(col).max().alias(name))
            else:
                agg_exprs.append(pl.col(col).sum().alias(name))

        aggregated = (
            out.select(*keys, "game_date", "pitcher_team")
            .join(daily, on="pitcher_team", how="left")
            .filter(
                pl.col("bp_date").is_not_null()
                & (pl.col("bp_date") < pl.col("game_date"))
                & (
                    pl.col("bp_date")
                    >= (pl.col("game_date") - timedelta(days=window))
                )
            )
            .group_by(keys)
            .agg(agg_exprs)
        )
        fill_cols = [f"{col}_L{window}d" for col in team_metrics]
        out = out.join(aggregated, on=keys, how="left").with_columns(
            [pl.col(c).fill_null(0).cast(pl.Int32) for c in fill_cols]
        )

        unique_name = f"bullpen_unique_arms_L{window}d"
        if arm_daily is not None:
            unique = (
                out.select(*keys, "game_date", "pitcher_team")
                .join(arm_daily, on="pitcher_team", how="left")
                .filter(
                    pl.col("bp_date").is_not_null()
                    & (pl.col("bp_date") < pl.col("game_date"))
                    & (
                        pl.col("bp_date")
                        >= (pl.col("game_date") - timedelta(days=window))
                    )
                )
                .group_by(keys)
                .agg(pl.col("bp_pitcher").n_unique().alias(unique_name))
            )
            out = out.join(unique, on=keys, how="left").with_columns(
                pl.col(unique_name).fill_null(0).cast(pl.Int32)
            )
        else:
            # Fallback: summed per-game uniques (overcounts cross-day repeats).
            out = out.with_columns(
                pl.col(f"bullpen_pitchers_used_L{window}d").alias(unique_name)
            )

    return out.drop("pitcher_team")


def bullpen_lookback_column_names(
    windows_days: Iterable[int] = DEFAULT_BULLPEN_LOOKBACK_DAYS,
) -> tuple[str, ...]:
    """Flat bullpen feature names for registries / TBF sets."""
    windows = sorted({int(w) for w in windows_days})
    return tuple(
        f"{metric}_L{window}d"
        for window in windows
        for metric in _LOOKBACK_METRICS
    )
