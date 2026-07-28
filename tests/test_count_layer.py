"""Tests for the strikeout count layer (rate × projected TBF)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from Python.count_layer import (
    attach_count_predictions,
    count_point_metrics,
    evaluate_count_layer,
    expected_strikeouts,
    fit_count_layer_kappa,
    over_threshold,
    p_strikeouts_ge,
    trials_from_projected_tbf,
)


def test_expected_strikeouts_product() -> None:
    got = expected_strikeouts([0.25, 0.20], [20.0, 25.0])
    np.testing.assert_allclose(got, [5.0, 5.0])


def test_over_threshold_half_lines() -> None:
    assert over_threshold(4.5) == 5
    assert over_threshold(5.0) == 6
    assert over_threshold(0.5) == 1


def test_trials_round_projected_tbf() -> None:
    np.testing.assert_array_equal(
        trials_from_projected_tbf([22.4, 22.6, 0.2]),
        [22, 23, 1],
    )


def test_binomial_p_over_known() -> None:
    # n=10, p=0.5, P(K >= 6) = P(K > 5) = sum binom 6..10
    from scipy.stats import binom

    expected = float(binom.sf(5, 10, 0.5))
    got = p_strikeouts_ge(
        5.5,
        k_rate=[0.5],
        projected_tbf=[10.0],
        family="binomial",
    )
    assert got[0] == pytest.approx(expected)


def test_beta_binomial_matches_binomial_at_large_kappa() -> None:
    rate = np.array([0.22, 0.28])
    tbf = np.array([22.0, 24.0])
    binom_p = p_strikeouts_ge(4.5, k_rate=rate, projected_tbf=tbf, family="binomial")
    bb_p = p_strikeouts_ge(
        4.5,
        k_rate=rate,
        projected_tbf=tbf,
        family="beta_binomial",
        kappa=1.0e6,
    )
    np.testing.assert_allclose(bb_p, binom_p, rtol=1e-5)


def test_poisson_family_uses_mean() -> None:
    from scipy.stats import poisson

    rate = np.array([0.25])
    tbf = np.array([20.0])
    expected = float(poisson.sf(4, 5.0))  # P(K >= 5), line 4.5
    got = p_strikeouts_ge(4.5, k_rate=rate, projected_tbf=tbf, family="poisson")
    assert got[0] == pytest.approx(expected)


def test_evaluate_count_layer_smoke() -> None:
    frame = pd.DataFrame({"K": [4, 6, 5, 7]})
    k_rate = np.array([0.22, 0.25, 0.20, 0.28])
    tbf = np.array([20.0, 22.0, 24.0, 21.0])
    report = evaluate_count_layer(
        frame,
        k_rate=k_rate,
        projected_tbf=tbf,
        lines=(4.5, 5.5),
        kappa=50.0,
    )
    assert "expected_k" in report
    assert report["expected_k"]["mae"] >= 0
    assert "4.5" in report["lines"]["binomial"]
    assert "4.5" in report["lines"]["beta_binomial"]
    assert report["lines"]["binomial"]["4.5"]["n"] == 4


def test_fit_kappa_and_attach_predictions() -> None:
    rng = np.random.default_rng(0)
    n = 80
    pa = rng.integers(18, 28, n).astype(float)
    rate = np.clip(0.22 + 0.02 * rng.normal(size=n), 0.05, 0.45)
    k = rng.binomial(pa.astype(int), rate).astype(float)
    kappa = fit_count_layer_kappa(k=k, pa=pa, k_rate=rate)
    assert kappa > 0
    frame = pd.DataFrame({"K": k, "PA": pa, "player": np.arange(n)})
    out = attach_count_predictions(
        frame,
        k_rate=rate,
        projected_tbf=pa * 0.98,
        lines=(4.5,),
        kappa=kappa,
    )
    assert "expected_K" in out.columns
    assert "projected_tbf" in out.columns
    assert "p_over_4_5" in out.columns
    assert "p_over_4_5_bb" in out.columns


def test_count_point_metrics_perfect() -> None:
    m = count_point_metrics([5, 6, 7], [5, 6, 7])
    assert m["mae"] == pytest.approx(0.0)
    assert m["rmse"] == pytest.approx(0.0)
    assert m["r2"] == pytest.approx(1.0)
