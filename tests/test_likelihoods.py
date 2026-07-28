from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from Python.likelihoods import (
    BetaBinomialModel,
    BinomialGLM,
    beta_binomial_nll,
    binomial_nll,
    fit_beta_binomial_kappa,
    rate_and_likelihood_metrics,
)


def test_binomial_nll_known_values() -> None:
    # One game: 2 K in 10 PA at p=0.2 -> NLL = -(2 log 0.2 + 8 log 0.8)
    expected = -(2 * np.log(0.2) + 8 * np.log(0.8))
    got = binomial_nll([2], [10], [0.2])
    assert got["binomial_nll_sum"] == pytest.approx(expected)
    assert got["binomial_nll_per_game"] == pytest.approx(expected)
    assert got["binomial_nll_per_pa"] == pytest.approx(expected / 10)


def test_binomial_nll_rejects_invalid_k() -> None:
    with pytest.raises(ValueError, match="K must lie"):
        binomial_nll([11], [10], [0.2])


def test_binomial_glm_predicts_in_unit_interval() -> None:
    rng = np.random.default_rng(1)
    n = 120
    frame = pd.DataFrame(
        {
            "feat": rng.normal(size=n),
            "PA": rng.integers(9, 28, n).astype(float),
        }
    )
    p = 1.0 / (1.0 + np.exp(-0.4 * frame["feat"]))
    frame["K"] = rng.binomial(frame["PA"].astype(int), p)
    frame["k_rate"] = frame["K"] / frame["PA"]

    model = BinomialGLM(alpha=1.0).fit(frame.iloc[:80], ["feat"])
    prediction = model.predict_proba(frame.iloc[80:], ["feat"])
    assert prediction.shape == (40,)
    assert np.all((prediction >= 0.0) & (prediction <= 1.0))


def test_rate_and_likelihood_metrics_include_nll() -> None:
    frame = pd.DataFrame(
        {
            "k_rate": [0.2, 0.3],
            "K": [4, 6],
            "PA": [20, 20],
        }
    )
    report = rate_and_likelihood_metrics(frame, np.array([0.25, 0.25]))
    assert "unweighted_mae" in report
    assert "binomial_nll_per_pa" in report
    assert report["binomial_nll_per_pa"] > 0


def test_beta_binomial_nll_exceeds_binomial_when_overdispersed() -> None:
    # Same mean; finite kappa adds variance vs pure binomial likelihood shape.
    k = np.array([0.0, 10.0])
    pa = np.array([10.0, 10.0])
    mu = np.array([0.5, 0.5])
    binomial = binomial_nll(k, pa, mu)
    # Very large kappa -> nearly binomial; small kappa -> extra dispersion.
    tight = beta_binomial_nll(k, pa, mu, kappa=1.0e6)
    loose = beta_binomial_nll(k, pa, mu, kappa=5.0)
    assert tight["beta_binomial_nll_per_pa"] == pytest.approx(
        binomial["binomial_nll_per_pa"], rel=1e-3
    )
    # Extreme outcomes are more probable under overdispersion (lower NLL).
    assert loose["beta_binomial_nll_sum"] < tight["beta_binomial_nll_sum"]


def test_fit_beta_binomial_kappa_positive() -> None:
    rng = np.random.default_rng(2)
    n = 200
    mu = np.full(n, 0.22)
    pa = rng.integers(15, 30, n).astype(float)
    # Overdispersed relative to pure binomial via noisy rates.
    noisy = np.clip(mu + rng.normal(0, 0.05, n), 0.05, 0.5)
    k = rng.binomial(pa.astype(int), noisy).astype(float)
    kappa = fit_beta_binomial_kappa(k, pa, mu)
    assert kappa > 1.0


def test_beta_binomial_model_fit_predict() -> None:
    rng = np.random.default_rng(3)
    n = 150
    frame = pd.DataFrame(
        {
            "feat": rng.normal(size=n),
            "PA": rng.integers(9, 28, n).astype(float),
        }
    )
    p = 1.0 / (1.0 + np.exp(-0.3 * frame["feat"]))
    frame["K"] = rng.binomial(frame["PA"].astype(int), p)
    frame["k_rate"] = frame["K"] / frame["PA"]

    model = BetaBinomialModel(alpha=1.0).fit(frame.iloc[:100], ["feat"])
    prediction = model.predict_proba(frame.iloc[100:], ["feat"])
    assert model.kappa is not None and model.kappa > 0
    assert prediction.shape == (50,)
    assert np.all((prediction >= 0.0) & (prediction <= 1.0))
