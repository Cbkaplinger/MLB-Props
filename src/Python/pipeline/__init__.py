"""Three-level feature pipeline (clear, editable stages).

Each level reads the previous level's parquet output and writes its own, so the
data flow is explicit and any single stage can be edited/re-run in isolation.

    Level 1  ``games.py``     raw Savant  ->  per-game tables (+ park factors)
    Level 2  ``rolling.py``   per-game    ->  leakage-safe rolling + statics
    Level 3  ``training.py``  rolling     ->  model-ready training frames

Artifact locations live in :mod:`Python.config` (``*_GAMES_PATH``,
``*_ROLLING_PATH``, ``*_TRAINING_PATH``, ``PARK_FACTORS_PATH``).

Run the whole thing::

    from Python.pipeline import run_all
    run_all(years=(2023, 2024, 2025))

or a single stage from the shell::

    python -m Python.pipeline.games
    python -m Python.pipeline.rolling
    python -m Python.pipeline.training
"""

from __future__ import annotations

from collections.abc import Iterable

from .. import config
from . import games, rolling, training


def run_all(years: Iterable[int] = config.TRAIN_SEASONS) -> None:
    """Run all three levels end to end for the given seasons."""
    games.run(years)
    rolling.run()
    training.run()


__all__ = ["games", "rolling", "training", "run_all"]
