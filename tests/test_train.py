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


def test_load_frame_excludes_holdout_season(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_train_module()
    path = tmp_path / "pitcher_training.parquet"
    pd.DataFrame(
        {
            "season": [2023, 2024, 2025],
            "game_date": pd.to_datetime(
                ["2023-04-01", "2024-04-01", "2025-04-01"]
            ),
            "player_name": ["A", "B", "C"],
            "k_rate": [0.20, 0.25, 0.30],
            "k_rate_P5": [0.18, 0.23, 0.28],
        }
    ).to_parquet(path)
    monkeypatch.setattr(module, "PITCHER_TRAINING_PATH", path)

    frame, features = module.load_frame()

    assert tuple(frame["season"]) == module.TRAIN_SEASONS
    assert features == ["k_rate_P5"]
