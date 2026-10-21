"""Synthetic separation tests for the REGISTERED count-aggregation
machinery (adapter.cycled_cond_mean + count_pmf_from_mixture, unchanged).

Purpose: separate the two queued research questions from
note_count_aggregation_future_2026-10-20.md by pinning exactly which
assumptions the current code makes:

  A. UNEQUAL BATTER PROBABILITIES: given N=n, the current code models the
     n PAs as i.i.d. Binomial(k; n, pbar_n) with pbar_n = mean of the
     first n slot probabilities (cycled prefix mean). The exact
     heterogeneous alternative is the Poisson-Binomial over the individual
     slot probabilities. Tests quantify where they agree (n=1, homogeneous
     lineups) and where they diverge (heterogeneous prefixes: tail mass
     overstated, middle understated), plus order sensitivity through the
     cycling.

  B. WORKLOAD/PERFORMANCE DEPENDENCE: the count PMF is a LINEAR mixture
     over the BF workload distribution with i.i.d.-given-n outcomes. Tests
     show the mixture is linear in P(N) (a coupled joint model is not
     expressible) and that within-n outcome correlation is outside the
     model class.

READ-ONLY over the frozen aggregation code: nothing in
research/offseason_2026/pregame_pa_ext/adapter.py is modified. The exact
Poisson-Binomial reference is a TEST-LOCAL oracle, never production code.
No real data, no fitting, no outcome evaluation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import pregame_pa_ext.adapter as ad  # noqa: E402


def point_mass_bf(n: int) -> np.ndarray:
    """BF workload distribution with all mass at exactly n batters faced
    (isolates the n-th term of the registered mixture)."""
    assert 1 <= n <= ad.KCOUNT_CAP
    bf = np.zeros(ad.KCOUNT_CAP)
    bf[n - 1] = 1.0
    return bf


def current_pmf_n(p9: list[float], n: int) -> np.ndarray:
    """The current model's count PMF when the BF workload is a point mass
    at n: Binom(k; n, pbar_n) over the 24 registered buckets."""
    pbar = ad.cycled_cond_mean(np.asarray(p9, dtype=np.float64))
    return ad.count_pmf_from_mixture(point_mass_bf(n), pbar)


def poisson_binomial_pmf(ps: list[float], buckets: int = ad.K_MAX) -> np.ndarray:
    """TEST-LOCAL exact oracle: Poisson-Binomial over heterogeneous
    per-PA probabilities, truncated into the same 24 buckets (tail at
    k=23) as the registered machinery."""
    dp = np.zeros(len(ps) + 1)
    dp[0] = 1.0
    for i, p in enumerate(ps, 1):
        nxt = np.zeros(i + 1)
        nxt[:i] += dp[:i] * (1.0 - p)
        nxt[1:i + 1] += dp[:i] * p
        dp = nxt
    out = np.zeros(buckets)
    for k in range(min(len(dp), buckets)):
        out[k] = dp[k]
    out[buckets - 1] += dp[buckets:].sum()
    return out


def var_current(p9: list[float], n: int) -> float:
    pmf = current_pmf_n(p9, n)
    ks = np.arange(ad.K_MAX)
    m = float((pmf * ks).sum())
    return float((pmf * (ks - m) ** 2).sum())


def var_poisson_binomial(ps: list[float]) -> float:
    pmf = poisson_binomial_pmf(ps)
    ks = np.arange(ad.K_MAX)
    m = float((pmf * ks).sum())
    return float((pmf * (ks - m) ** 2).sum())


# ------------------------------------- A. unequal probabilities vs averaged
def test_n1_is_exact():
    """For N=1 the averaged-binomial IS the Poisson-Binomial (a single
    Bernoulli) - the current code is exact at n=1 for any lineup."""
    p9 = [0.1, 0.35, 0.5, 0.62, 0.2, 0.44, 0.3, 0.55, 0.28]
    assert current_pmf_n(p9, 1) == pytest.approx(
        poisson_binomial_pmf(p9[:1]), abs=1e-12)


def test_homogeneous_lineup_is_exact():
    """Equal slot probabilities: the averaged binomial equals the exact
    Poisson-Binomial for every n - the current machinery's homogeneity
    assumption is the ONLY thing being tested here."""
    p9 = [0.3] * 9
    for n in range(1, 10):
        assert current_pmf_n(p9, n) == pytest.approx(
            poisson_binomial_pmf(p9[:n]), abs=1e-9)


def test_heterogeneous_prefix_overstates_extremes():
    """Heterogeneous two-slot prefix: the averaged binomial overstates
    P(K=0) and P(K=n) and understates the middle, relative to the exact
    Poisson-Binomial. Analytic gap at n=2: ((p1-p2)/2)^2 on each tail."""
    p9 = [0.1, 0.9] + [0.5] * 7
    cur = current_pmf_n(p9, 2)
    ex = poisson_binomial_pmf(p9[:2])
    assert cur[0] > ex[0] and cur[2] > ex[2]
    assert cur[1] < ex[1]
    gap = ((p9[0] - p9[1]) / 2.0) ** 2
    assert (cur[0] - ex[0]) == pytest.approx(gap, abs=1e-12)
    assert (cur[2] - ex[2]) == pytest.approx(gap, abs=1e-12)


def test_heterogeneous_variance_gap():
    """Var(Poisson-Binomial) = sum p(1-p) <= n * pbar (1-pbar):
    the averaged binomial's variance upper-bounds the exact variance for
    heterogeneous prefixes (Jensen) - a measurable dispersion error."""
    p9 = [0.10, 0.22, 0.35, 0.41, 0.18, 0.29, 0.5, 0.12, 0.33]
    for n in range(2, 10):
        assert var_current(p9, n) > var_poisson_binomial(p9[:n])


def test_max_gap_realistic_heterogeneous_spread():
    """Quantify the approximation error on a realistic heterogeneous
    lineup over n=2..9: non-zero, bounded, reported for the record."""
    p9 = [0.18, 0.30, 0.22, 0.41, 0.12, 0.35, 0.27, 0.20, 0.38]
    gaps = {}
    for n in range(2, 10):
        gaps[n] = float(np.max(np.abs(
            current_pmf_n(p9, n) - poisson_binomial_pmf(p9[:n]))))
    assert all(g > 0 for g in gaps.values())
    assert max(gaps.values()) < 0.05  # small but real at PA-count scale


def test_order_sensitivity_through_cycling():
    """The cycled prefix mean makes the model ORDER-SENSITIVE: the same
    nine batters in different batting orders produce different count PMFs
    whenever BF mass sits below n=9, and IDENTICAL PMFs at exactly n=9
    (the full-lineup mean is order-invariant). This pins the implicit
    assumption that batters faced follow batting order from slot 1."""
    p9 = [0.1, 0.5, 0.9, 0.3, 0.2, 0.4, 0.6, 0.25, 0.45]
    p9_rev = list(reversed(p9))
    assert not np.allclose(current_pmf_n(p9, 2), current_pmf_n(p9_rev, 2))
    assert not np.allclose(current_pmf_n(p9, 5), current_pmf_n(p9_rev, 5))
    assert current_pmf_n(p9, 9) == pytest.approx(
        current_pmf_n(p9_rev, 9), abs=1e-12)


# ------------------------------------- B. workload/performance dependence
def test_mixture_is_linear_in_bf_distribution():
    """The count PMF is LINEAR in the BF workload measure: a mixture of
    two workload distributions yields the same mixture of PMFs. This pins
    the independence assumption - the workload enters as a pure mixing
    measure over n; nothing couples it to the per-PA probabilities."""
    p9 = [0.25, 0.31, 0.22, 0.4, 0.28, 0.19, 0.33, 0.27, 0.36]
    pbar = ad.cycled_cond_mean(np.asarray(p9))
    bf1 = point_mass_bf(3)
    bf2 = point_mass_bf(20)
    for alpha in (0.3, 0.7):
        mix_bf = alpha * bf1 + (1 - alpha) * bf2
        lhs = ad.count_pmf_from_mixture(mix_bf, pbar)
        rhs = alpha * ad.count_pmf_from_mixture(bf1, pbar) + \
            (1 - alpha) * ad.count_pmf_from_mixture(bf2, pbar)
        assert lhs == pytest.approx(rhs, abs=1e-12)


def test_within_n_correlation_is_outside_the_model_class():
    """The registered mixture assumes outcomes are i.i.d. GIVEN n. A
    within-n correlated joint outcome (e.g., pitcher-state dependence
    inside a game) has a true count distribution that NO parameterization
    of the current per-n averaged binomial reproduces. The current code
    returns the i.i.d. answer; the correlated truth differs - quantifying
    the workload/performance separation question."""
    # n=2 joint: positively correlated outcomes
    # P(00)=0.40 P(01)=0.10 P(10)=0.10 P(11)=0.40 -> K: 0.40/0.20/0.40
    truth_corr = np.zeros(ad.K_MAX)
    truth_corr[0], truth_corr[1], truth_corr[2] = 0.40, 0.20, 0.40
    # the i.i.d. answer at the matching mean per-PA rate (p=0.5):
    iid = ad.count_pmf_from_mixture(point_mass_bf(2),
                                    np.array([0.5] * ad.KCOUNT_CAP))
    assert np.max(np.abs(truth_corr - iid)) > 0.1
    # the current machinery, given the same lineup + BF, returns exactly
    # the i.i.d. answer - there is no parameter for within-n correlation
    p9 = [0.5] * 9
    assert ad.count_pmf_from_mixture(point_mass_bf(2),
                                     ad.cycled_cond_mean(np.asarray(p9))
                                     ) == pytest.approx(iid, abs=1e-12)


def test_endogenous_workload_coupling_inexpressible():
    """A performance-exposure coupling (the per-PA K rate dropping in
    long-outing states, independent of lineup composition) is not
    expressible: pbar_n is CONSTRAINED to prefix means of the nine slot
    probabilities, so a declining profile like (0.3, 0.3, 0.3, 0.1) with
    slot probs all 0.3 cannot be represented. The constraint - not merely
    the point estimate - is what the queued dependent-formulation question
    would have to change."""
    p9 = [0.3] * 9
    pbar = ad.cycled_cond_mean(np.asarray(p9))
    # any prefix mean of equal slot probabilities is that same constant
    assert np.allclose(pbar[:9], 0.3)
    assert np.allclose(pbar, 0.3)  # cycled: constant forever
    # therefore a workload-dependent decline is structurally absent
    # (allowing 1e-9 for float accumulation noise in the running mean)
    assert not np.any(pbar < 0.3 - 1e-9)
