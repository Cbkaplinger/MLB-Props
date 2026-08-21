"""Nested chronological folds for protected 2023-2024 feature research."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ChronologicalFold:
    """One date-disjoint train/validation split."""

    train: pd.DataFrame
    validation: pd.DataFrame


@dataclass(frozen=True)
class NestedFold:
    """An outer confirmation split and inner selection splits."""

    outer: ChronologicalFold
    inner: dict[str, ChronologicalFold]


def _split(
    frame: pd.DataFrame,
    *,
    validation_start: str,
    validation_end: str | None,
) -> ChronologicalFold:
    start = pd.Timestamp(validation_start)
    end = pd.Timestamp(validation_end) if validation_end is not None else None
    train = frame[frame["game_date"] < start]
    validation = frame[frame["game_date"] >= start]
    if end is not None:
        validation = validation[validation["game_date"] < end]
    return ChronologicalFold(train=train, validation=validation)


def _validate_fold(name: str, fold: ChronologicalFold) -> None:
    if fold.train.empty or fold.validation.empty:
        raise ValueError(f"{name} produced an empty partition")
    if fold.train["game_date"].max() >= fold.validation["game_date"].min():
        raise ValueError(f"{name} has overlapping train/validation dates")
    if set(fold.train.index) & set(fold.validation.index):
        raise ValueError(f"{name} has overlapping train/validation rows")


def nested_research_folds(frame: pd.DataFrame) -> dict[str, NestedFold]:
    """Return outer confirmation folds with selection-only inner folds.

    The retired ``_research_folds`` design exposed the same validation periods
    for selection and reported improvement. Here, each inner validation period
    lies wholly inside its corresponding outer training partition.
    """
    if not frame["game_date"].is_monotonic_increasing:
        raise ValueError("nested folds require rows sorted by game_date")

    folds = {
        "outer_2024_h1": NestedFold(
            outer=_split(
                frame,
                validation_start="2024-01-01",
                validation_end="2024-07-01",
            ),
            inner={
                "inner_2023_mid": _split(
                    frame[frame["game_date"] < pd.Timestamp("2024-01-01")],
                    validation_start="2023-06-01",
                    validation_end="2023-08-01",
                ),
                "inner_2023_late": _split(
                    frame[frame["game_date"] < pd.Timestamp("2024-01-01")],
                    validation_start="2023-08-01",
                    validation_end="2024-01-01",
                ),
            },
        ),
        "outer_2024_h2": NestedFold(
            outer=_split(
                frame,
                validation_start="2024-07-01",
                validation_end=None,
            ),
            inner={
                "inner_2023_h2": _split(
                    frame[frame["game_date"] < pd.Timestamp("2024-07-01")],
                    validation_start="2023-07-01",
                    validation_end="2024-01-01",
                ),
                "inner_2024_late_h1": _split(
                    frame[frame["game_date"] < pd.Timestamp("2024-07-01")],
                    validation_start="2024-05-15",
                    validation_end="2024-07-01",
                ),
            },
        ),
    }

    for outer_name, nested in folds.items():
        _validate_fold(outer_name, nested.outer)
        outer_train_indices = set(nested.outer.train.index)
        outer_validation_indices = set(nested.outer.validation.index)
        for inner_name, inner in nested.inner.items():
            qualified_name = f"{outer_name}/{inner_name}"
            _validate_fold(qualified_name, inner)
            inner_indices = set(inner.train.index) | set(inner.validation.index)
            if not inner_indices <= outer_train_indices:
                raise ValueError(
                    f"{qualified_name} is not contained in outer training rows"
                )
            if inner_indices & outer_validation_indices:
                raise ValueError(f"{qualified_name} touches outer validation rows")
            if inner.validation["game_date"].max() > nested.outer.train[
                "game_date"
            ].max():
                raise ValueError(
                    f"{qualified_name} validation extends beyond outer training"
                )
    return folds


def fold_metadata(folds: dict[str, NestedFold]) -> dict[str, object]:
    """Serialize nested boundaries for artifact metadata."""

    def describe(fold: ChronologicalFold) -> dict[str, object]:
        return {
            "train_range": [
                str(fold.train["game_date"].min().date()),
                str(fold.train["game_date"].max().date()),
            ],
            "validation_range": [
                str(fold.validation["game_date"].min().date()),
                str(fold.validation["game_date"].max().date()),
            ],
            "train_rows": len(fold.train),
            "validation_rows": len(fold.validation),
        }

    return {
        outer_name: {
            "outer": describe(nested.outer),
            "inner": {
                inner_name: describe(inner)
                for inner_name, inner in nested.inner.items()
            },
        }
        for outer_name, nested in folds.items()
    }
