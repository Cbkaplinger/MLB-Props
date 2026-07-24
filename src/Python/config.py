"""Cross-platform project paths configured through environment variables."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _path_from_env(name: str, default: Path) -> Path:
    """Return a normalized path from an environment variable or default."""
    return Path(os.getenv(name, str(default))).expanduser().resolve()


DATA_DIR = _path_from_env("MLB_PROPS_DATA_DIR", PROJECT_ROOT / "Data")
OUTPUT_DIR = _path_from_env("MLB_PROPS_OUTPUT_DIR", PROJECT_ROOT / "artifacts")
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MODEL_DIR = OUTPUT_DIR / "models"

# ---------------------------------------------------------------------------
# Three-level feature pipeline artifacts (see src/Python/pipeline/).
# Level 1 (games)  : raw Savant -> one row per game (pitcher start / batter game)
# Level 2 (rolling): game-level -> leakage-safe rolling/season-to-date + statics
# Level 3 (train)  : rolling -> model-ready frames (spine + lineup/park joins)
# Park factors are a small dimension table joined at Level 3.
# ---------------------------------------------------------------------------
# Level 1 -- game-level
PITCHER_GAMES_PATH = PROCESSED_DATA_DIR / "pitcher_games.parquet"
PITCH_TYPE_GAMES_PATH = PROCESSED_DATA_DIR / "pitch_type_games.parquet"
BATTER_GAMES_PATH = PROCESSED_DATA_DIR / "batter_games.parquet"
# Level 2 -- rolling / season-to-date
PITCHER_ROLLING_PATH = PROCESSED_DATA_DIR / "pitcher_rolling.parquet"
BATTER_ROLLING_PATH = PROCESSED_DATA_DIR / "batter_rolling.parquet"
# Level 3 -- model-ready training frames
PITCHER_TRAINING_PATH = PROCESSED_DATA_DIR / "pitcher_training.parquet"
BATTER_TRAINING_PATH = PROCESSED_DATA_DIR / "batter_training.parquet"
# Dimension tables (computed once over the window, joined at Level 3)
PARK_FACTORS_PATH = PROCESSED_DATA_DIR / "park_factors.parquet"
PLAYER_ID_MAP_PATH = DATA_DIR / "dimensions" / "player_id_map.parquet"

SAVANT_DATA_DIR = _path_from_env(
    "MLB_PROPS_SAVANT_DATA_DIR",
    DATA_DIR / "Savant-Data" / "regular",
)

# Postgame-defined research cohort used by the current Level 1 build.
MIN_STARTER_BATTERS_FACED: int = 9

# Season configuration. Feature research is restricted to 2023-2024 so the
# complete 2025 season remains a historical holdout. After evaluation, the
# production model may fit all training seasons before projecting 2026.
TRAIN_SEASONS: tuple[int, ...] = (2023, 2024, 2025)
FEATURE_RESEARCH_SEASONS: tuple[int, ...] = (2023, 2024)
HOLDOUT_SEASON: int = 2025
PROJECTION_SEASON: int = 2026


def ensure_output_directories() -> None:
    """Create local artifact directories when a workflow needs them."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
