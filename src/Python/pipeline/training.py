"""Level 3 - rolling features -> model-ready training frames.

The **bottom** of the pipeline. Reads the Level 2 rolling files (and the park
dimension table) and produces frames that go straight into the training script
with minimal further transformation:

- ``pitcher_training.parquet`` - the strikeout-model spine: pitcher rolling
  features + opposing-lineup aggregates (from the batter rolling file) + park
  factor. Label column ``k_rate`` is present; drop it and the other label
  columns (``K``, ``PA``, ``Outs``) from ``X`` at fit time.
- ``batter_training.parquet`` - batter rolling features + park factor, ready for
  a batter-side model. (Opposing-starter features are the analogous cross-join to
  add here later, mirroring the pitcher side's opposing-lineup join.)

Season-opening pitcher rows intentionally retain null opponent-lineup features:
every batter has zero prior-season PA before their first game, so no leakage-safe
season-to-date rate exists yet. Training must impute these nulls or use a model
that handles them natively rather than backfilling from the game being predicted.

This layer only *joins*, so all leakage guarantees from Level 2 are preserved.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .. import config

_BASE_LINEUP_RATE_COLUMNS = {
    "opp_lineup_whiff": "whiff_rate_std",
    "opp_lineup_swstr": "swstr_rate_std",
    "opp_lineup_chase": "chase_rate_std",
    "opp_lineup_zswing": "zswing_rate_std",
    "opp_lineup_swing": "swing_rate_std",
    "opp_lineup_zcontact": "zcontact_rate_std",
    "opp_lineup_bb": "bb_rate_std",
    **{
        f"opp_lineup_{output}_P{window}": f"{source}_P{window}"
        for output, source in (
            ("zswing", "zswing_rate"),
            ("swing", "swing_rate"),
            ("zcontact", "zcontact_rate"),
            ("bb", "bb_rate"),
        )
        for window in (5, 10, 20)
    },
}
_RESEARCH_LINEUP_BASES = {
    "k": "k_rate",
    "whiff": "whiff_rate",
    "swstr": "swstr_rate",
    "chase": "chase_rate",
    "zswing": "zswing_rate",
    "swing": "swing_rate",
    "zcontact": "zcontact_rate",
    "bb": "bb_rate",
    "babip": "babip",
    "hard_hit": "hard_hit_rate",
    "barrel": "barrel_rate",
    "sweet_spot": "sweet_spot_rate",
    "avg_ev": "avg_exit_velocity",
    "avg_la": "avg_launch_angle",
    "xba": "xBA",
    "woba": "wOBA",
    "xwoba": "xwOBA",
    "hr": "hr_rate",
    "fb": "fb_rate",
    "hr_fb": "hr_fb_rate",
    "pull_air": "pull_air_rate",
    "rv_per_pitch": "rv_per_pitch",
}
_RESEARCH_LINEUP_RATE_COLUMNS = {
    f"opp_lineup_{output}{suffix}": f"{source}_{'std' if not suffix else suffix[1:]}"
    for output, source in _RESEARCH_LINEUP_BASES.items()
    for suffix in ("", "_P5", "_P10", "_P20")
}
_LINEUP_RATE_COLUMNS = {
    **_RESEARCH_LINEUP_RATE_COLUMNS,
    **_BASE_LINEUP_RATE_COLUMNS,
}
_REQUIRED_BATTER_COLUMNS = {
    "batter",
    "game_pk",
    "bat_team",
    "is_initial_lineup",
    "k_rate_std",
    "k_rate_std_vL",
    "k_rate_std_vR",
    *_BASE_LINEUP_RATE_COLUMNS.values(),
}


def opposing_lineup_features(
    starts: pl.DataFrame,
    batters: pl.DataFrame,
) -> pl.DataFrame:
    """Aggregate each opposing batter's pregame rates onto a pitcher start.

    Every hitter rate is computed before this join. Level 3 emits the existing
    flat lineup mean plus research-only batting-order-opportunity weighted means
    and weighted standard deviations. It never rolls a realized team lineup
    aggregate, which would mix changing rosters and risk same-game leakage.

    Season-opening games (including early neutral-site openers) will have
    null lineup features here: batters have zero season-to-date PA before
    their own first game, so the K and discipline rates are null for the whole
    opposing lineup. This is intentional -- it preserves the leakage boundary
    rather than backfilling with a synthetic constant.
    Downstream training must handle these nulls explicitly (imputation or native
    NaN-tolerant model).
    """
    missing = sorted(_REQUIRED_BATTER_COLUMNS - set(batters.columns))
    if missing:
        raise ValueError(f"batter rolling data is missing lineup columns: {missing}")

    keys = starts.select("game_pk", "pitcher", "p_throws", "opp_team")
    available_rates = {
        output: source
        for output, source in _LINEUP_RATE_COLUMNS.items()
        if source in batters.columns
    }
    optional_columns = [
        column
        for column in ("lineup_slot", "lineup_pa_weight")
        if column in batters.columns
    ]
    rate_source_columns = [
        source
        for source in dict.fromkeys(available_rates.values())
        if source not in {"k_rate_std", "k_rate_std_vL", "k_rate_std_vR"}
    ]
    has_lineup_weight = "lineup_pa_weight" in batters.columns
    joined = keys.join(
        batters.filter(pl.col("is_initial_lineup")).select(
            "game_pk", "batter", "bat_team", "k_rate_std", "k_rate_std_vL",
            "k_rate_std_vR", *optional_columns,
            *rate_source_columns,
        ),
        left_on=["game_pk", "opp_team"],
        right_on=["game_pk", "bat_team"],
        how="left",
    ).with_columns(
        pl.when(pl.col("p_throws") == "R")
        .then(pl.col("k_rate_std_vR"))
        .when(pl.col("p_throws") == "L")
        .then(pl.col("k_rate_std_vL"))
        .otherwise(None)
        .alias("_k_vs_hand"),
        (
            pl.col("lineup_pa_weight")
            if has_lineup_weight
            else pl.lit(1.0)
        ).alias("_lineup_weight"),
    )

    def weighted_mean(source: str, output: str) -> pl.Expr:
        valid = pl.col(source).is_not_null() & (pl.col("_lineup_weight") > 0)
        denominator = pl.when(valid).then(pl.col("_lineup_weight")).otherwise(0.0).sum()
        numerator = (
            pl.when(valid)
            .then(pl.col(source) * pl.col("_lineup_weight"))
            .otherwise(0.0)
            .sum()
        )
        return pl.when(denominator > 0).then(numerator / denominator).otherwise(None).alias(output)

    def weighted_sd(source: str, output: str) -> pl.Expr:
        valid = pl.col(source).is_not_null() & (pl.col("_lineup_weight") > 0)
        denominator = pl.when(valid).then(pl.col("_lineup_weight")).otherwise(0.0).sum()
        mean = (
            pl.when(valid)
            .then(pl.col(source) * pl.col("_lineup_weight"))
            .otherwise(0.0)
            .sum()
            / denominator
        )
        second_moment = (
            pl.when(valid)
            .then(pl.col(source).pow(2) * pl.col("_lineup_weight"))
            .otherwise(0.0)
            .sum()
            / denominator
        )
        variance = (second_moment - mean.pow(2)).clip(lower_bound=0.0)
        return pl.when(denominator > 0).then(variance.sqrt()).otherwise(None).alias(output)

    aggregations = [
        pl.col("batter").count().alias("opp_lineup_size"),
        pl.col("k_rate_std").mean().alias("opp_lineup_k"),
        pl.col("_k_vs_hand").mean().alias("opp_lineup_k_vs_hand"),
        weighted_mean("_k_vs_hand", "opp_lineup_k_vs_hand_order_weighted"),
        weighted_sd("_k_vs_hand", "opp_lineup_k_vs_hand_order_sd"),
    ]
    aggregations.extend(
        pl.col(source).mean().alias(output)
        for output, source in available_rates.items()
        if output not in {"opp_lineup_k"}
    )
    aggregations.extend(
        expression
        for output, source in available_rates.items()
        for expression in (
            weighted_mean(source, f"{output}_order_weighted"),
            weighted_sd(source, f"{output}_order_sd"),
        )
    )
    return joined.group_by("game_pk", "pitcher").agg(aggregations)


def _join_park_factors(
    frame: pl.DataFrame,
    park_factors: pl.DataFrame,
) -> pl.DataFrame:
    """Join a complete, unique park dimension or fail loudly."""
    keys = ["season", "home_team"]
    dimension = park_factors.select(*keys, "park_k_factor")

    if dimension.select(keys).is_duplicated().any():
        raise ValueError("park_factors contains duplicate (season, home_team) keys")

    required_seasons = set(frame["season"].drop_nulls().unique().to_list())
    available_seasons = set(
        dimension["season"].drop_nulls().unique().to_list()
    )
    missing_seasons = sorted(required_seasons - available_seasons)
    if missing_seasons:
        raise ValueError(
            f"park_factors is missing rolling-data seasons: {missing_seasons}"
        )

    out = frame.join(
        dimension,
        on=keys,
        how="left",
        validate="m:1",
    )
    if out.height != frame.height:
        raise ValueError(
            f"park-factor join changed row count: {frame.height} -> {out.height}"
        )

    if out["park_k_factor"].null_count():
        missing_keys = (
            out.filter(pl.col("park_k_factor").is_null())
            .select(keys)
            .unique()
            .sort(keys)
            .head(10)
            .to_dicts()
        )
        raise ValueError(
            "park_factors is missing (season, home_team) keys; "
            f"sample={missing_keys}"
        )
    return out


def build_pitcher_training(
    pitcher_rolling: pl.DataFrame,
    batter_rolling: pl.DataFrame,
    park_factors: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Spine + opposing-lineup + park -> model-ready pitcher frame."""
    lineup = opposing_lineup_features(pitcher_rolling, batter_rolling)
    invalid_sizes = lineup.filter(pl.col("opp_lineup_size") != 9)
    if invalid_sizes.height:
        sample = invalid_sizes.select(
            "game_pk", "pitcher", "opp_lineup_size"
        ).head(10).to_dicts()
        raise ValueError(
            "opposing initial-lineup coverage must contain exactly 9 batters; "
            f"sample={sample}"
        )
    lineup_keys = ["game_pk", "pitcher"]
    if lineup.select(lineup_keys).is_duplicated().any():
        raise ValueError("opposing lineup contains duplicate (game_pk, pitcher) keys")

    out = pitcher_rolling.join(
        lineup,
        on=lineup_keys,
        how="left",
        validate="1:1",
    )
    if out.height != pitcher_rolling.height:
        raise ValueError(
            "lineup join changed row count: "
            f"{pitcher_rolling.height} -> {out.height}"
        )
    if park_factors is not None:
        out = _join_park_factors(out, park_factors)
    return out.sort(["game_date", "player_name"])


def build_batter_training(
    batter_rolling: pl.DataFrame,
    park_factors: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Batter rolling + park factor -> model-ready batter frame.

    Opposing-starter features are not yet implemented, so this frame is not
    feature-complete for a batter-side production model.
    """
    out = batter_rolling
    if park_factors is not None and "home_team" in out.columns:
        out = _join_park_factors(out, park_factors)
    sort_keys = [c for c in ("game_date", "game_pk", "batter") if c in out.columns]
    return out.sort(sort_keys) if sort_keys else out


def _write(df: pl.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return path


def run() -> dict[str, Path]:
    """Read Level 2 + park factors, build training frames, write Level 3 files."""
    pitcher_rolling = pl.read_parquet(config.PITCHER_ROLLING_PATH)
    batter_rolling = pl.read_parquet(config.BATTER_ROLLING_PATH)
    if not config.PARK_FACTORS_PATH.exists():
        raise FileNotFoundError(
            f"Missing park-factor dimension: {config.PARK_FACTORS_PATH}"
        )
    park_factors = pl.read_parquet(config.PARK_FACTORS_PATH)

    paths = {
        "pitcher_training": _write(
            build_pitcher_training(pitcher_rolling, batter_rolling, park_factors),
            config.PITCHER_TRAINING_PATH,
        ),
        "batter_training": _write(
            build_batter_training(batter_rolling, park_factors),
            config.BATTER_TRAINING_PATH,
        ),
    }
    for name, path in paths.items():
        print(f"[level 3] wrote {name}: {path}")
    return paths


if __name__ == "__main__":
    run()
