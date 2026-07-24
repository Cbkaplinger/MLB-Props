"""Level 1 - raw Savant -> game-level tables.

The **top** of the pipeline. Pitch-level Savant is transformed and grouped into
one row per game, then written to ``data/processed/``:

- ``pitcher_games.parquet`` - one row per starting-pitcher game (the spine),
  including the label ``k_rate = K / max(PA, 1)``.
- ``pitch_type_games.parquet`` - one row per starter/game/canonical pitch type,
  retaining numerator/denominator pairs for feature research.
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

from .. import batter_features, config, identity, pitcher_features
from ..ballpark import pregame_park_factors
from ..statcast import (
    load_statcast_years,
    plate_appearances,
    regular_season_schedule,
    validate_statcast_season,
)


def _write(df: pl.DataFrame, path: Path) -> Path:
    """Write a frame to parquet, creating the processed dir if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return path


def build_pitcher_games(
    raw: pl.DataFrame,
    min_batters_faced: int = config.MIN_STARTER_BATTERS_FACED,
    with_fip: bool = True,
    player_map: pl.DataFrame | None = None,
    hr_fb_history: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Per-start pitcher spine with label and readable-name metadata."""
    starts = pitcher_features.build_pitcher_starts(
        raw, min_batters_faced=min_batters_faced
    )
    if with_fip:
        rate_source = raw.select("game_date", "events", "bb_type")
        if hr_fb_history is not None:
            rate_source = pl.concat(
                [
                    hr_fb_history.select("game_date", "events", "bb_type"),
                    rate_source,
                ],
                how="vertical_relaxed",
            )
        starts = starts.join(
            pitcher_features.prior_date_league_hr_fb(rate_source),
            on="game_date",
            how="left",
            validate="m:1",
        )
        starts = pitcher_features.add_fip_xfip(
            starts,
            league_hr_fb_column="lg_hr_fb_prior",
        )
    starts = starts.with_columns(
        (pl.col("K") / pl.col("PA").clip(lower_bound=1)).alias("k_rate")
    )
    return identity.enrich_pitcher_names(starts, player_map)


def build_batter_games(
    raw: pl.DataFrame,
    player_map: pl.DataFrame | None = None,
    prior_league_k_rate: float | None = None,
) -> pl.DataFrame:
    """Per-(game, batter) table with optional readable-name metadata."""
    games = batter_features.build_batter_games(raw)
    if prior_league_k_rate is not None:
        games = games.with_columns(
            pl.lit(prior_league_k_rate).alias("prior_league_k_rate")
        )
    if player_map is None:
        return games
    return identity.enrich_batter_names(
        games,
        player_map,
        resolve_missing=True,
    )


def build_park_factors(
    raw: pl.DataFrame,
    years: Iterable[int],
    prior_history: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Prior-season strikeout factor dimension, including the next season."""
    years = tuple(sorted({int(year) for year in years}))
    park_source = raw
    if prior_history is not None:
        park_columns = (
            "game_pk", "game_date", "home_team",
            "at_bat_number", "pitch_number", "events",
        )
        park_source = pl.concat(
            [
                prior_history.select(park_columns),
                raw.select(park_columns),
            ],
            how="vertical_relaxed",
        )
    return pregame_park_factors(
        plate_appearances(park_source),
        (*years, max(years) + 1),
    )


def _validate_raw_seasons(raw: pl.DataFrame, years: Iterable[int]) -> None:
    """Verify each requested season against MLB's official game IDs."""
    for year in years:
        _, _, official_game_pks = regular_season_schedule(year)
        validate_statcast_season(
            raw.filter(pl.col("game_year") == year),
            year,
            official_game_pks=official_game_pks,
        )


def run(
    years: Iterable[int] = config.TRAIN_SEASONS,
    *,
    min_batters_faced: int = config.MIN_STARTER_BATTERS_FACED,
    refresh_player_map: bool = False,
    verify_schedule: bool = True,
) -> dict[str, Path]:
    """Build and write all Level 1 tables. Returns the written paths."""
    years = tuple(years)
    # Load Savant once. The previous wrappers each re-read the same large files.
    columns = tuple(dict.fromkeys(
        ("game_year", *pitcher_features.BUILD_COLUMNS, *batter_features.BUILD_COLUMNS)
    ))
    raw = load_statcast_years(years, columns=columns)
    prior_year = min(years) - 1
    prior_history = load_statcast_years(
        (prior_year,),
        columns=(
            "game_pk", "game_date", "game_year", "home_team",
            "at_bat_number", "pitch_number", "events", "bb_type",
        ),
    )
    if verify_schedule:
        _validate_raw_seasons(raw, years)
        _validate_raw_seasons(prior_history, (prior_year,))
    prior_pa = plate_appearances(prior_history)
    prior_league_k_rate = float(prior_pa["is_k"].sum() / prior_pa.height)
    player_map = identity.load_player_map(refresh=refresh_player_map)
    paths = {
        "player_id_map": config.PLAYER_ID_MAP_PATH,
        "pitcher_games": _write(
            build_pitcher_games(
                raw,
                min_batters_faced=min_batters_faced,
                player_map=player_map,
                hr_fb_history=prior_history,
            ),
            config.PITCHER_GAMES_PATH,
        ),
        "pitch_type_games": _write(
            pitcher_features.build_pitch_type_games(
                raw,
                min_batters_faced=min_batters_faced,
            ),
            config.PITCH_TYPE_GAMES_PATH,
        ),
        "batter_games": _write(
            build_batter_games(
                raw,
                player_map=player_map,
                prior_league_k_rate=prior_league_k_rate,
            ),
            config.BATTER_GAMES_PATH,
        ),
        "park_factors": _write(
            build_park_factors(raw, years, prior_history),
            config.PARK_FACTORS_PATH,
        ),
    }
    for name, path in paths.items():
        print(f"[level 1] wrote {name}: {path}")
    return paths


if __name__ == "__main__":
    run()
