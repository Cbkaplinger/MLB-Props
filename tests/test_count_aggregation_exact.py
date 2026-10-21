"""Synthetic tests for the RESEARCH-ONLY exact Poisson-Binomial count
aggregator (count_aggregation_exact.py, Question A scoping). Separates
UNEQUAL BATTER PROBABILITIES from the current average-probability
binomial. Synthetic only: no real data, no production change, no
outcome evaluation."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import pregame_pa_ext.adapter as ad  # noqa: E402
from pregame_pa_ext import count_aggregation_exact as ex  # noqa: E402


def uniform_bf() -> np.ndarray:
    bf = np.full(ad.KCOUNT_CAP, 1.0 / ad.KCOUNT_CAP)
    return bf / bf.sum()


def point_mass_bf(n: int) -> np.ndarray:
    bf = np.zeros(ad.KCOUNT_CAP)
    bf[n - 1] = 1.0
    return bf


def brute_force_pmf(ps: list[float]) -> np.ndarray:
    """Ground-truth oracle: enumerate all 2^n outcome vectors (small n
    only). Returns probabilities for K=0..n."""
    pmf = np.zeros(len(ps) + 1)
    for mask in range(2 ** len(ps)):
        prob = 1.0
        k = 0
        for i in range(len(ps)):
            if mask >> i & 1:
                prob *= ps[i]
                k += 1
            else:
                prob *= 1.0 - ps[i]
        pmf[k] += prob
    return pmf


def test_normalization_and_nonnegative_mass():
    """The exact PMF sums to 1 and is non-negative for heterogeneous and
    homogeneous lineups across point-mass, uniform, and mixed BF inputs."""
    p9s = [[0.18, 0.30, 0.22, 0.41, 0.12, 0.35, 0.27, 0.20, 0.38],
           [0.3] * 9]
    bfs = [point_mass_bf(1), point_mass_bf(9), point_mass_bf(37),
           uniform_bf(),
           0.4 * point_mass_bf(2) + 0.6 * uniform_bf()]
    for p9 in p9s:
        for bf in bfs:
            pmf = ex.exact_count_pmf(p9, bf)
            assert pmf.min() >= 0.0
            assert pmf.sum() == pytest.approx(1.0, abs=1e-12)


def test_equivalence_under_homogeneous_probabilities():
    """Equal slot probabilities: the exact Poisson-Binomial equals the
    current averaged binomial (the approximation is exact under
    homogeneity) for point-mass and spread BF workloads."""
    p9 = [0.3] * 9
    pbar = ad.cycled_cond_mean(np.asarray(p9))
    for bf in (point_mass_bf(1), point_mass_bf(5), point_mass_bf(37),
               uniform_bf()):
        exact = ex.exact_count_pmf(p9, bf)
        current = ad.count_pmf_from_mixture(bf, pbar)
        assert exact == pytest.approx(current, abs=1e-12)


def test_agreement_with_bruteforce_enumeration_small_cases():
    """The DP aggregator agrees with brute-force 2^n enumeration for
    small heterogeneous cases (n=2 and n=3), including the tail bucket."""
    for ps in ([0.1, 0.9], [0.2, 0.7, 0.55], [0.05, 0.95, 0.5]):
        # pad to a 9-slot lineup: the first n cycled probabilities are ps
        p9_pad = ps + [0.0] * (9 - len(ps))
        n = len(ps)
        dp = ex.poisson_binomial_pmf_cycled(p9_pad, n)
        bf_exact = brute_force_pmf(ps)
        # compare k=0..n (no tail mass below the last bucket)
        assert dp[: n + 1] == pytest.approx(bf_exact, abs=1e-12)
        # and through the registered 24-bucket wrapper (point-mass BF at n)
        pmf = ex.exact_count_pmf(p9_pad, point_mass_bf(n))
        assert pmf[: n + 1] == pytest.approx(bf_exact, abs=1e-12)
        assert pmf[n + 1:].sum() == pytest.approx(0.0, abs=1e-12)


def test_expected_ks_preserved():
    """E[K] under the exact aggregation equals the sum of the first n
    slot probabilities (Poisson-Binomial mean), and the BF mixture
    preserves the weighted mean."""
    p9 = [0.18, 0.30, 0.22, 0.41, 0.12, 0.35, 0.27, 0.20, 0.38]
    ks = np.arange(ad.K_MAX)
    for n in (1, 2, 5, 9):
        pmf = ex.poisson_binomial_pmf_cycled(p9, n)
        assert float((pmf * ks).sum()) == pytest.approx(sum(p9[:n]),
                                                        abs=1e-12)
    # BF mixture: E[K] of the bucketed PMF equals the bf-weighted mean of
    # the per-n bucketed PB means (the k=23 tail bucket absorbs K >= 23,
    # so for large n the bucketed mean is the correct comparison - the
    # analytic untruncated mean would be biased down by the truncation)
    bf = uniform_bf()
    pmf = ex.exact_count_pmf(p9, bf)
    per_n_mean = [float((ex.poisson_binomial_pmf_cycled(p9, n) * ks).sum())
                  for n in range(1, ad.KCOUNT_CAP + 1)]
    expected = sum(bf[n - 1] * per_n_mean[n - 1]
                   for n in range(1, ad.KCOUNT_CAP + 1))
    assert float((pmf * ks).sum()) == pytest.approx(expected, abs=1e-9)


def test_mixing_across_bf_values():
    """The exact aggregator is linear in the BF workload: a mixture of two
    workload distributions yields the same mixture of exact PMFs."""
    p9 = [0.22, 0.35, 0.28, 0.15, 0.44, 0.26, 0.31, 0.2, 0.33]
    bf1, bf2 = point_mass_bf(3), uniform_bf()
    for alpha in (0.25, 0.6):
        mix = alpha * bf1 + (1 - alpha) * bf2
        lhs = ex.exact_count_pmf(p9, mix)
        rhs = alpha * ex.exact_count_pmf(p9, bf1) + \
            (1 - alpha) * ex.exact_count_pmf(p9, bf2)
        assert lhs == pytest.approx(rhs, abs=1e-12)


def test_heterogeneous_gap_direction_matches_separation_findings():
    """Cross-check with the separation tests: for a heterogeneous
    two-slot prefix the CURRENT averaged binomial overstates both tail
    masses relative to the exact aggregator (analytic at n=2:
    ((p1-p2)/2)^2), confirming the two aggregators genuinely differ."""
    p9 = [0.1, 0.9] + [0.5] * 7
    exact = ex.exact_count_pmf(p9, point_mass_bf(2))
    pbar = ad.cycled_cond_mean(np.asarray(p9))
    current = ad.count_pmf_from_mixture(point_mass_bf(2), pbar)
    gap = ((p9[0] - p9[1]) / 2.0) ** 2
    assert (current[0] - exact[0]) == pytest.approx(gap, abs=1e-12)
    assert (current[2] - exact[2]) == pytest.approx(gap, abs=1e-12)
