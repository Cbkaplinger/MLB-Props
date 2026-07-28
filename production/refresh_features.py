"""Rebuild Level 1–3 feature tables for production scoring.

Includes research seasons plus the projection year so live as-of joins have
current form. Does not change TRAIN_SEASONS / feature-research windows.

Examples:
    python production/refresh_features.py
    python production/refresh_features.py --skip-training
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.pipeline import games, rolling, training  # noqa: E402


def production_years() -> tuple[int, ...]:
    years = tuple(dict.fromkeys((*config.PIPELINE_SEASONS, config.PROJECTION_SEASON)))
    return years


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-training",
        action="store_true",
        help="Stop after Level 2 (rolling). Live scoring needs rolling; L3 is optional.",
    )
    parser.add_argument(
        "--refresh-player-map",
        action="store_true",
        help="Force refresh of the MLB player ID map at Level 1.",
    )
    args = parser.parse_args()

    years = production_years()
    print(f"Level 1 games for seasons: {years}")
    paths = games.run(years, refresh_player_map=args.refresh_player_map)
    for name, path in paths.items():
        print(f"  {name}: {path}")

    print("Level 2 rolling…")
    rolling.run()
    print(f"  pitcher_rolling: {config.PITCHER_ROLLING_PATH}")
    print(f"  batter_rolling: {config.BATTER_ROLLING_PATH}")

    if args.skip_training:
        print("Skipped Level 3 (--skip-training).")
        return

    print("Level 3 training frames…")
    training.run()
    print(f"  pitcher_training: {config.PITCHER_TRAINING_PATH}")
    print(f"  batter_training: {config.BATTER_TRAINING_PATH}")


if __name__ == "__main__":
    main()
