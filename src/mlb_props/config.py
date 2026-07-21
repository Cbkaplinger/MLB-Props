"""Cross-platform project paths.

Paths may be overridden with environment variables so the same code works on
Windows, macOS, and Longleaf without machine-specific branches.
"""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _path_from_env(name: str, default: Path) -> Path:
    """Return a normalized path from an environment variable or default."""
    return Path(os.getenv(name, str(default))).expanduser().resolve()


DATA_DIR = _path_from_env("MLB_PROPS_DATA_DIR", PROJECT_ROOT / "data")
OUTPUT_DIR = _path_from_env("MLB_PROPS_OUTPUT_DIR", PROJECT_ROOT / "artifacts")
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MODEL_DIR = OUTPUT_DIR / "models"
PREDICTION_DIR = OUTPUT_DIR / "predictions"
SHAP_DIR = OUTPUT_DIR / "shap"
OPTUNA_DIR = OUTPUT_DIR / "optuna"

PITCHER_STARTS_PATH = _path_from_env(
    "MLB_PROPS_PITCHER_STARTS",
    DATA_DIR / "processed" / "Pitcher2023-2025.parquet",
)
SAVANT_DATA_DIR = _path_from_env(
    "MLB_PROPS_SAVANT_DATA_DIR",
    DATA_DIR / "raw" / "savant" / "regular",
)
ROSTER_SCRAPER_DIR = PROJECT_ROOT / "RosterScraper"


def ensure_output_directories() -> None:
    """Create local artifact directories when a workflow needs them."""
    for directory in (MODEL_DIR, PREDICTION_DIR, SHAP_DIR, OPTUNA_DIR):
        directory.mkdir(parents=True, exist_ok=True)
