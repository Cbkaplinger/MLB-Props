from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from Python import training


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

    # Use pre_freeze_248 so this test isolates holdout-season exclusion without
    # coupling to the full production registry's P1/lineup-discipline columns.
    frame, features = module.load_frame(feature_set="pre_freeze_248")

    assert tuple(frame["season"]) == module.TRAIN_SEASONS
    assert features == ["k_rate_P5"]


def test_resolve_sample_weights_none_returns_none() -> None:
    frame = pd.DataFrame({"PA": [9, 22, 27]})
    assert training.resolve_sample_weights(frame, "none") is None


def test_resolve_sample_weights_pa_returns_positive_weights() -> None:
    frame = pd.DataFrame({"PA": [9, 22, 27]})
    weights = training.resolve_sample_weights(frame, "pa")
    assert weights is not None
    np.testing.assert_allclose(weights, [9.0, 22.0, 27.0])


def test_resolve_sample_weights_pa_rejects_nonpositive() -> None:
    frame = pd.DataFrame({"PA": [9, 0, 27]})
    with pytest.raises(ValueError, match="strictly positive"):
        training.resolve_sample_weights(frame, "pa")


def test_resolve_sample_weights_pa_rejects_missing_column() -> None:
    frame = pd.DataFrame({"k_rate": [0.2, 0.3]})
    with pytest.raises(ValueError, match="requires a PA column"):
        training.resolve_sample_weights(frame, "pa")


def test_partition_metrics_includes_pa_weighted_when_requested() -> None:
    y_true = pd.Series([0.1, 0.2, 0.3])
    prediction = np.array([0.12, 0.18, 0.35])
    weights = np.array([10.0, 20.0, 30.0])

    report = training.partition_metrics(
        y_true, prediction, pa_weights=weights, include_pa_weighted=True
    )

    assert set(report) == {"unweighted", "pa_weighted"}
    assert report["unweighted"]["mae"] != report["pa_weighted"]["mae"]


def test_partition_metrics_omits_weighted_block_without_weights() -> None:
    y_true = pd.Series([0.1, 0.2, 0.3])
    prediction = np.array([0.12, 0.18, 0.35])

    report = training.partition_metrics(y_true, prediction)

    assert set(report) == {"unweighted"}


def test_fit_regressor_routes_pa_weights_to_ridge() -> None:
    rng = np.random.default_rng(0)
    n = 40
    train = pd.DataFrame(
        {
            "k_rate": rng.uniform(0.1, 0.4, n),
            "feat_a": rng.normal(size=n),
            "PA": rng.integers(9, 30, n).astype(float),
        }
    )
    model = training.build_model("ridge")
    train_weight = training.resolve_sample_weights(train, "pa")

    training.fit_regressor(
        model,
        "ridge",
        train[["feat_a"]],
        train["k_rate"],
        train_weight=train_weight,
    )

    prediction = model.predict(train[["feat_a"]].iloc[:10])
    assert prediction.shape == (10,)


def test_assert_pa_not_in_features() -> None:
    training.assert_pa_not_in_features(["k_rate_P5", "whiff_rate_P20"])
    with pytest.raises(RuntimeError, match="PA leaked"):
        training.assert_pa_not_in_features(["k_rate_P5", "PA"])


def test_fit_kwargs_for_weights() -> None:
    weights = np.array([1.0, 2.0])
    assert training.fit_kwargs_for_weights("ridge", None) == {}
    assert training.fit_kwargs_for_weights("ridge", weights) == {
        "ridge__sample_weight": weights
    }
    assert training.fit_kwargs_for_weights("elasticnet", weights) == {
        "elasticnetcv__sample_weight": weights
    }
    assert training.fit_kwargs_for_weights("poisson", weights) == {
        "poissonregressor__sample_weight": weights
    }
    assert training.fit_kwargs_for_weights("lightgbm", weights) == {
        "sample_weight": weights
    }


def test_build_model_elasticnet_and_poisson_fit() -> None:
    rng = np.random.default_rng(0)
    n = 80
    x = pd.DataFrame({"feat_a": rng.normal(size=n), "feat_b": rng.normal(size=n)})
    y = np.clip(20 + x["feat_a"] + 0.5 * x["feat_b"] + rng.normal(size=n), 8, 35)
    for name in ("elasticnet", "poisson"):
        model = training.build_model(name)
        training.fit_regressor(model, name, x, y)
        pred = model.predict(x.iloc[:5])
        assert pred.shape == (5,)
        assert np.all(np.isfinite(pred))
