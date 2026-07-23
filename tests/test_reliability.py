"""Tests for Python.reliability.

These exercise the split-half / stabilization / reliability-table helpers on a
small synthetic dataset where each pitcher has a stable underlying "skill", so
reliability should be high, and the fast (grouped) paths should agree with the
per-call reference implementation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from Python import reliability as rel


@pytest.fixture
def synthetic_starts() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n_pitchers, n_games = 80, 24
    rows = []
    dates = pd.date_range("2023-04-01", periods=n_games * 3, freq="5D")
    for pid in range(n_pitchers):
        skill = rng.uniform(0.15, 0.35)  # stable per-pitcher K rate
        for g in range(n_games):
            pa = int(rng.integers(20, 28))
            k = rng.binomial(pa, skill)
            rows.append(
                {
                    "player_name": f"P{pid:03d}",
                    "game_date": dates[g % len(dates)] + pd.Timedelta(days=pid),
                    "PA": pa,
                    "K": k,
                    "ff_velo": 93.0 + skill * 10 + rng.normal(0, 0.2),
                }
            )
    return pd.DataFrame(rows)


def test_split_half_reliability_detects_stable_skill(synthetic_starts):
    r = rel.split_half_reliability(synthetic_starts, "K", n_games_per_half=10, use_rate=True)
    assert not np.isnan(r)
    assert r > 0.4  # a stable underlying rate should be at least moderately reliable


def test_split_half_reliability_too_few_pitchers_returns_nan(synthetic_starts):
    r = rel.split_half_reliability(synthetic_starts, "K", n_games_per_half=10, min_pitchers=10_000)
    assert np.isnan(r)


def test_stabilization_curve_matches_per_call(synthetic_starts):
    windows = [5, 8, 10]
    curve = rel.stabilization_curve(
        synthetic_starts, rate_stats=("K",), mean_stats=("ff_velo",), windows=windows
    )
    assert list(curve.index) == windows
    assert {"K", "ff_velo"}.issubset(curve.columns)
    for n in windows:
        ref = rel.split_half_reliability(synthetic_starts, "K", n, use_rate=True)
        assert curve.loc[n, "K"] == pytest.approx(ref, rel=1e-9, nan_ok=True)


def test_reliability_table_shapes_and_tiers(synthetic_starts):
    table = rel.reliability_table(
        synthetic_starts, n_games_per_half=10, rate_stats=("K",), mean_stats=("ff_velo",)
    )
    assert set(table["stat"]) == {"K", "ff_velo"}
    for col in ("pearson_r", "spearman_rho", "yoy_r", "sem", "beta1", "feature_tier"):
        assert col in table.columns
    assert table["feature_tier"].isin(
        ["Tier 1 - stable", "Tier 2 - moderate", "Tier 3 - noisy", "Unknown"]
    ).all()


def test_feature_tier_thresholds():
    assert rel.feature_tier(0.9) == "Tier 1 - stable"
    assert rel.feature_tier(0.6) == "Tier 2 - moderate"
    assert rel.feature_tier(0.1) == "Tier 3 - noisy"
    assert rel.feature_tier(float("nan")) == "Unknown"
