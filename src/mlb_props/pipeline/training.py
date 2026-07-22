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

This layer only *joins*, so all leakage guarantees from Level 2 are preserved.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .. import config

_LINEUP_RATE_COLUMNS = {
    "opp_lineup_whiff": "whiff_rate_std",
    "opp_lineup_chase": "chase_rate_std",
}


def opposing_lineup_features(
    starts: pl.DataFrame,
    batters: pl.DataFrame,
) -> pl.DataFrame:
    """Aggregate each opposing batter's pregame rates onto a pitcher start."""
    keys = starts.select("game_pk", "pitcher", "p_throws", "opp_team")
    optional = [
        column for column in _LINEUP_RATE_COLUMNS.values()
        if column in batters.columns
    ]
    joined = keys.join(
        batters.select(
            "game_pk", "bat_team", "k_rate_std", "k_rate_std_vL",
            "k_rate_std_vR", *optional,
        ),
        left_on=["game_pk", "opp_team"],
        right_on=["game_pk", "bat_team"],
        how="left",
    ).with_columns(
        pl.when(pl.col("p_throws") == "R")
        .then(pl.col("k_rate_std_vR"))
        .otherwise(pl.col("k_rate_std_vL"))
        .alias("_k_vs_hand")
    )

    aggregations = [
        pl.col("k_rate_std").mean().alias("opp_lineup_k"),
        pl.col("_k_vs_hand").mean().alias("opp_lineup_k_vs_hand"),
    ]
    aggregations.extend(
        pl.col(source).mean().alias(output)
        for output, source in _LINEUP_RATE_COLUMNS.items()
        if source in optional
    )
    return joined.group_by("game_pk", "pitcher").agg(aggregations)


def build_pitcher_training(
    pitcher_rolling: pl.DataFrame,
    batter_rolling: pl.DataFrame,
    park_factors: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Spine + opposing-lineup + park -> model-ready pitcher frame."""
    lineup = opposing_lineup_features(pitcher_rolling, batter_rolling)
    out = pitcher_rolling.join(lineup, on=["game_pk", "pitcher"], how="left")
    if park_factors is not None:
        out = out.join(
            park_factors.select("season", "home_team", "park_k_factor"),
            on=["season", "home_team"],
            how="left",
        )
    return out.sort(["game_date", "player_name"])


def build_batter_training(
    batter_rolling: pl.DataFrame,
    park_factors: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Batter rolling + park factor -> model-ready batter frame."""
    out = batter_rolling
    if park_factors is not None and "home_team" in out.columns:
        out = out.join(
            park_factors.select("season", "home_team", "park_k_factor"),
            on=["season", "home_team"],
            how="left",
        )
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
    park_factors = (
        pl.read_parquet(config.PARK_FACTORS_PATH)
        if config.PARK_FACTORS_PATH.exists()
        else None
    )

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
