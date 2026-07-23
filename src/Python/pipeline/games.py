"""Level 1 - raw Savant -> game-level tables.

The **top** of the pipeline. Pitch-level Savant is transformed and grouped into
one row per game, then written to ``data/processed/``:

- ``pitcher_games.parquet`` - one row per starting-pitcher game (the spine),
  including the label ``k_rate = K / max(PA, 1)``.
- ``batter_games.parquet``  - one row per ``(game_pk, batter)``.
- ``park_factors.parquet``  - season/stadium strikeout-factor dimension. Each
  target season uses prior seasons only and is joined at Level 3 rather than
  rolled. Other external context tables would follow the same pattern.

Nothing here is leakage-sensitive yet: these are just faithful per-game
aggregates. Leakage-safe rolling happens in Level 2 (:mod:`.rolling`).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import polars as pl

from .. import config
from .. import batter_features, pitcher_features
from ..ballpark import pregame_park_factors
from ..statcast import load_statcast_years, plate_appearances


def _write(df: pl.DataFrame, path: Path) -> Path:
    """Write a frame to parquet, creating the processed dir if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return path


def build_pitcher_games(
    raw: pl.DataFrame,
    min_batters_faced: int = 9,
    with_fip: bool = True,
) -> pl.DataFrame:
    """Per-start pitcher spine with the ``k_rate`` label attached."""
    starts = pitcher_features.build_pitcher_starts(
        raw, min_batters_faced=min_batters_faced
    )
    if with_fip:
        starts = pitcher_features.add_fip_xfip(
            starts,
            league_hr_fb=pitcher_features.league_hr_fb_from_pitches(raw),
        )
    return starts.with_columns(
        (pl.col("K") / pl.col("PA").clip(lower_bound=1)).alias("k_rate")
    )


def build_batter_games(raw: pl.DataFrame) -> pl.DataFrame:
    """Per-(game, batter) table."""
    return batter_features.build_batter_games(raw)


def build_park_factors(raw: pl.DataFrame, years: Iterable[int]) -> pl.DataFrame:
    """Prior-season strikeout factor dimension, including the next season."""
    years = tuple(sorted({int(year) for year in years}))
    return pregame_park_factors(
        plate_appearances(raw),
        (*years, max(years) + 1),
    )


def run(years: Iterable[int] = config.TRAIN_SEASONS) -> dict[str, Path]:
    """Build and write all Level 1 tables. Returns the written paths."""
    years = tuple(years)
    # Load Savant once. The previous wrappers each re-read the same large files.
    columns = tuple(dict.fromkeys(
        (*pitcher_features.BUILD_COLUMNS, *batter_features.BUILD_COLUMNS)
    ))
    raw = load_statcast_years(years, columns=columns)
    paths = {
        "pitcher_games": _write(build_pitcher_games(raw), config.PITCHER_GAMES_PATH),
        "batter_games": _write(build_batter_games(raw), config.BATTER_GAMES_PATH),
        "park_factors": _write(
            build_park_factors(raw, years), config.PARK_FACTORS_PATH
        ),
    }
    for name, path in paths.items():
        print(f"[level 1] wrote {name}: {path}")
    return paths


if __name__ == "__main__":
    run()
