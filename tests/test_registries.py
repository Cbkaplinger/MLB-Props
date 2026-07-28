"""Tests for feature-set registries (Step 1 / Step 7 / Step 9c)."""

from __future__ import annotations

import pandas as pd
import pytest

from Python.registries import (
    FEATURE_SETS,
    production_features,
    resolve_feature_names,
    step7_185_features,
)


def _toy_frame(*, with_p1: bool = False) -> pd.DataFrame:
    data = {
        "k_rate": [0.2, 0.25],
        "is_home": [1, 0],
        "park_k_factor": [1.0, 0.98],
        "opp_lineup_k": [0.22, 0.24],
        "opp_lineup_k_vs_hand": [0.21, 0.23],
        "opp_lineup_whiff": [0.25, 0.26],
        "opp_lineup_swstr": [0.11, 0.12],
        "opp_lineup_chase": [0.28, 0.29],
        "ff_velo_P3": [94.0, 95.0],
        "ff_velo_P5": [94.1, 95.1],
        "ff_velo_P10": [94.2, 95.2],
        "cu_vaa_P3": [-5.0, -5.1],
        "cu_vaa_P5": [-5.0, -5.1],
        "cu_usage_vR_P3": [0.1, 0.11],
        "cu_usage_vR_P5": [0.1, 0.11],
        "fs_usage_vR_P3": [0.05, 0.06],
        "fs_usage_vR_P5": [0.05, 0.06],
        "sl_vaa_P3": [-6.0, -6.1],
        "sl_vaa_P5": [-6.0, -6.1],
        "k_rate_P5": [0.2, 0.21],
    }
    if with_p1:
        data.update(
            {
                "ff_velo_P1": [94.5, 95.5],
                "cu_vaa_P1": [-4.9, -5.0],
                "cu_usage_vR_P1": [0.12, 0.13],
                "fs_usage_vR_P1": [0.04, 0.05],
                "sl_vaa_P1": [-5.8, -5.9],
            }
        )
    return pd.DataFrame(data)


def _family_patch() -> dict[str, str]:
    mapping = {
        "ff_velo_P3": "pitch_physics",
        "ff_velo_P5": "pitch_physics",
        "ff_velo_P10": "pitch_physics",
        "ff_velo_P1": "pitch_physics",
        "cu_vaa_P3": "pitch_physics",
        "cu_vaa_P5": "pitch_physics",
        "cu_vaa_P1": "pitch_physics",
        "cu_usage_vR_P3": "pitch_usage",
        "cu_usage_vR_P5": "pitch_usage",
        "cu_usage_vR_P1": "pitch_usage",
        "fs_usage_vR_P3": "pitch_usage",
        "fs_usage_vR_P5": "pitch_usage",
        "fs_usage_vR_P1": "pitch_usage",
        "sl_vaa_P3": "pitch_physics",
        "sl_vaa_P5": "pitch_physics",
        "sl_vaa_P1": "pitch_physics",
        "k_rate_P5": "rates",
        "is_home": "context",
        "park_k_factor": "park",
        "opp_lineup_k": "lineup",
        "opp_lineup_k_vs_hand": "lineup",
        "opp_lineup_whiff": "lineup",
        "opp_lineup_swstr": "lineup",
        "opp_lineup_chase": "lineup",
    }
    return mapping


def test_pre_freeze_keeps_mean_family_p10(monkeypatch: pytest.MonkeyPatch) -> None:
    import Python.registries as registries

    monkeypatch.setattr(registries, "_family_map", _family_patch)
    pre = resolve_feature_names(_toy_frame(with_p1=True), "pre_freeze_248")
    assert "ff_velo_P10" in pre
    assert "k_rate" not in pre


def test_step7_185_drops_mean_family_p10(monkeypatch: pytest.MonkeyPatch) -> None:
    import Python.registries as registries

    monkeypatch.setattr(registries, "_family_map", _family_patch)
    features = step7_185_features(_toy_frame(with_p1=True))
    assert "ff_velo_P3" in features
    assert "ff_velo_P5" in features
    assert "ff_velo_P10" not in features
    assert "k_rate_P5" in features


def test_production_applies_p1_swap(monkeypatch: pytest.MonkeyPatch) -> None:
    import Python.registries as registries

    monkeypatch.setattr(registries, "_family_map", _family_patch)
    features = production_features(_toy_frame(with_p1=True))
    assert "ff_velo_P1" in features
    assert "cu_vaa_P1" in features
    assert "ff_velo_P3" not in features
    assert "ff_velo_P5" not in features
    assert "ff_velo_P10" not in features
    assert "k_rate_P5" in features


def test_production_requires_p1_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    import Python.registries as registries

    monkeypatch.setattr(registries, "_family_map", _family_patch)
    with pytest.raises(ValueError, match="requires P1"):
        production_features(_toy_frame(with_p1=False))


def test_resolve_feature_names_rejects_unknown_set() -> None:
    with pytest.raises(ValueError, match="unsupported feature set"):
        resolve_feature_names(_toy_frame(with_p1=True), "not_a_set")


def test_feature_sets_constant() -> None:
    assert FEATURE_SETS == ("production", "step7_185", "pre_freeze_248", "ridge_vif")
