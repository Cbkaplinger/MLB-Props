from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_train_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "Models"
        / "Strikeout-Model"
        / "train.py"
    )
    spec = importlib.util.spec_from_file_location("strikeout_train", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chronological_split_keeps_dates_disjoint() -> None:
    module = _load_train_module()
    dates = pd.date_range("2025-04-01", periods=10, freq="D").repeat(2)
    frame = pd.DataFrame({"game_date": dates, "value": range(len(dates))})

    train, validation, test = module.chronological_split(frame)

    assert train["game_date"].max() < validation["game_date"].min()
    assert validation["game_date"].max() < test["game_date"].min()
    assert len(train) + len(validation) + len(test) == len(frame)
    assert not set(train.index) & set(validation.index)
    assert not set(validation.index) & set(test.index)


def test_chronological_split_rejects_unsorted_rows() -> None:
    module = _load_train_module()
    frame = pd.DataFrame(
        {
            "game_date": pd.to_datetime(
                ["2025-04-02", "2025-04-01", "2025-04-03"]
            )
        }
    )
    with pytest.raises(ValueError, match="sorted by game_date"):
        module.chronological_split(frame)


def test_chronological_split_requires_three_dates() -> None:
    module = _load_train_module()
    frame = pd.DataFrame(
        {"game_date": pd.to_datetime(["2025-04-01", "2025-04-02"])}
    )
    with pytest.raises(ValueError, match="three distinct dates"):
        module.chronological_split(frame)
