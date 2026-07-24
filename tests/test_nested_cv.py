from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd


EDA_DIR = (
    Path(__file__).resolve().parents[1]
    / "Models"
    / "Strikeout-Model"
    / "Strikeout-EDA"
)
sys.path.insert(0, str(EDA_DIR))

nested_cv = importlib.import_module("nested_cv")


def test_nested_folds_keep_inner_data_inside_outer_train() -> None:
    dates = pd.date_range("2023-03-30", "2024-09-30", freq="D").repeat(2)
    frame = pd.DataFrame(
        {
            "game_date": dates,
            "value": range(len(dates)),
        }
    )

    folds = nested_cv.nested_research_folds(frame)

    assert set(folds) == {"outer_2024_h1", "outer_2024_h2"}
    for nested in folds.values():
        outer_train = nested.outer.train
        outer_validation = nested.outer.validation
        assert outer_train["game_date"].max() < outer_validation["game_date"].min()
        assert not set(outer_train.index) & set(outer_validation.index)
        assert not set(outer_train["game_date"]) & set(
            outer_validation["game_date"]
        )

        for inner in nested.inner.values():
            assert inner.train["game_date"].max() < inner.validation[
                "game_date"
            ].min()
            assert not set(inner.train["game_date"]) & set(
                inner.validation["game_date"]
            )
            inner_rows = set(inner.train.index) | set(inner.validation.index)
            assert inner_rows <= set(outer_train.index)
            assert not inner_rows & set(outer_validation.index)
            assert inner.validation["game_date"].max() <= outer_train[
                "game_date"
            ].max()


def test_legacy_research_folds_api_is_retired() -> None:
    feature_ablation = importlib.import_module("feature_ablation")
    assert not hasattr(feature_ablation, "_research_folds")
