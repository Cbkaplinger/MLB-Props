"""Level 2 - game-level tables -> leakage-safe rolling features.

The **middle** of the pipeline. Reads the Level 1 game files, applies the
leakage-safe rolling / season-to-date manipulations (the windows chosen from
stabilization analysis), and keeps the static identity/context columns the model
and the Level 3 joins need (game keys, date, teams, home/away, batter hand).

Everything raw and same-game is dropped **except** the pitcher label columns
(``K``, ``PA``, ``Outs``, ``k_rate``), which are the training targets, not
features. This keeps the rolling files clean and hard to leak from. Pass
``keep_raw=True`` if you want to inspect the same-game inputs alongside.

Outputs:
- ``pitcher_rolling.parquet``
- ``batter_rolling.parquet``
"""

from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from .. import config
from ..batter_rolling import add_leakage_safe_k
from ..bullpen import (
    add_bullpen_lookback_features,
    bullpen_lookback_column_names,
)
from ..pitcher_rolling import add_rolling_pitcher_features

# Any rolling / season-to-date output column ends with one of these.
_ROLLING_RE = re.compile(r"(_P\d+|_std(_vL|_vR|_shrunk)?)$")

# Static identity/context to carry through (kept when present).
_PITCHER_STATIC = (
    "game_pk", "game_date", "season", "pitcher", "player_name", "pitcher_name",
    "p_throws", "home_team", "away_team", "is_home", "opp_team",
    # Phase A / A.1 TBF covariates (pregame; not same-game labels).
    "days_rest", "days_rest_capped", "is_season_debut", "rest_is_long_gap",
    "rest_gap_severity", "is_career_mlb_debut",
    # Phase C bullpen lookbacks (flat team priors).
    *bullpen_lookback_column_names(),
)
# Pitcher label / target-support columns (same-game, but they are the labels).
_PITCHER_LABELS = ("K", "PA", "Outs", "k_rate")

_BATTER_STATIC = (
    "game_pk", "game_date", "season", "batter", "batter_name", "stand",
    "bat_team", "home_team", "away_team", "is_home", "opp_team",
    "is_initial_lineup", "lineup_slot", "lineup_pa_weight",
)


def _select(df: pl.DataFrame, keep: tuple[str, ...], keep_raw: bool) -> pl.DataFrame:
    """Keep ``keep`` columns (when present) plus every rolling column."""
    if keep_raw:
        return df
    cols = [c for c in df.columns if c in keep or _ROLLING_RE.search(c)]
    return df.select(cols)


def build_pitcher_rolling(
    games: pl.DataFrame,
    keep_raw: bool = False,
    bullpen_team_games: pl.DataFrame | None = None,
    bullpen_appearances: pl.DataFrame | None = None,
    **kw,
) -> pl.DataFrame:
    """Add leakage-safe rolling pitcher features and trim to statics + rolling."""
    rolled = add_rolling_pitcher_features(games, **kw)
    if bullpen_team_games is not None:
        rolled = add_bullpen_lookback_features(
            rolled,
            bullpen_team_games,
            appearances=bullpen_appearances,
        )
    return _select(rolled, _PITCHER_STATIC + _PITCHER_LABELS, keep_raw)


def build_batter_rolling(games: pl.DataFrame, keep_raw: bool = False, **kw) -> pl.DataFrame:
    """Add leakage-safe rolling batter features and trim to statics + rolling."""
    rolled = add_leakage_safe_k(games, **kw)
    return _select(rolled, _BATTER_STATIC, keep_raw)


def _write(df: pl.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return path


def run(keep_raw: bool = False) -> dict[str, Path]:
    """Read Level 1 game files, build rolling features, write Level 2 files."""
    pitcher_games = pl.read_parquet(config.PITCHER_GAMES_PATH)
    batter_games = pl.read_parquet(config.BATTER_GAMES_PATH)
    bullpen_team_games = (
        pl.read_parquet(config.BULLPEN_TEAM_GAMES_PATH)
        if config.BULLPEN_TEAM_GAMES_PATH.exists()
        else None
    )
    bullpen_appearances = (
        pl.read_parquet(config.BULLPEN_APPEARANCES_PATH)
        if config.BULLPEN_APPEARANCES_PATH.exists()
        else None
    )
    if bullpen_team_games is None:
        print(
            "[level 2] warning: missing bullpen_team_games.parquet; "
            "Phase C lookbacks skipped. Re-run Level 1."
        )

    paths = {
        "pitcher_rolling": _write(
            build_pitcher_rolling(
                pitcher_games,
                keep_raw=keep_raw,
                bullpen_team_games=bullpen_team_games,
                bullpen_appearances=bullpen_appearances,
            ),
            config.PITCHER_ROLLING_PATH,
        ),
        "batter_rolling": _write(
            build_batter_rolling(batter_games, keep_raw=keep_raw),
            config.BATTER_ROLLING_PATH,
        ),
    }
    for name, path in paths.items():
        print(f"[level 2] wrote {name}: {path}")
    return paths


if __name__ == "__main__":
    run()
