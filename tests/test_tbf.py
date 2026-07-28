"""Tests for projected-TBF feature safety."""

from __future__ import annotations

import pandas as pd
import pytest

from Python.tbf import (
    TBF_TARGET,
    assert_tbf_label_not_in_features,
    tbf_feature_names,
)


def _frame() -> pd.DataFrame:
    from Python.bullpen import bullpen_lookback_column_names

    cols = {
        "PA": [24],
        "days_rest_capped": [5],
        "is_season_debut": [0],
        "rest_is_long_gap": [0],
        "rest_gap_severity": [0],
        "is_career_mlb_debut": [0],
        "is_home": [1],
        "park_k_factor": [1.0],
        "opp_lineup_k": [0.22],
        "opp_lineup_k_vs_hand": [0.23],
    }
    for name in bullpen_lookback_column_names():
        cols[name] = [1]
    for stat in ("PA", "Outs", "Pitches"):
        for window in (5, 10, 20):
            cols[f"{stat}_P{window}"] = [20.0]
    return pd.DataFrame(cols)


def test_tbf_workload_excludes_label() -> None:
    features = tbf_feature_names(_frame(), "workload")
    assert TBF_TARGET not in features
    assert "PA_P5" in features
    assert "days_rest_capped" in features
    assert "rest_gap_severity" in features
    assert "is_career_mlb_debut" in features
    assert "is_home" not in features
    assert "bullpen_pitches_L1d" not in features


def test_tbf_workload_context_includes_context() -> None:
    features = tbf_feature_names(_frame(), "workload_context")
    assert "is_home" in features
    assert "park_k_factor" in features
    assert "opp_lineup_k" in features
    assert "bullpen_pitches_L1d" not in features
    assert TBF_TARGET not in features


def test_tbf_workload_context_bullpen_includes_pen() -> None:
    features = tbf_feature_names(_frame(), "workload_context_bullpen")
    assert "bullpen_pitches_L1d" in features
    assert "bullpen_pitchers_used_L3d" in features
    assert "bullpen_L_pitches_L1d" not in features  # thin freeze set
    assert "rest_gap_severity" in features
    assert TBF_TARGET not in features


def test_tbf_bullpen_rich_includes_enrichment() -> None:
    features = tbf_feature_names(_frame(), "workload_context_bullpen_rich")
    assert "bullpen_L_pitches_L1d" in features
    assert "bullpen_b2b_arms_L3d" in features
    assert "bullpen_unique_arms_L2d" in features


def test_assert_rejects_label_leak() -> None:
    with pytest.raises(RuntimeError, match="leaked"):
        assert_tbf_label_not_in_features(["PA_P5", "PA"])
