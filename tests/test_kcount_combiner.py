"""Synthetic tests for the K-count combiner (no real data, no scoring)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import kcount_combiner as kc  # noqa: E402


def flat_hazard(h=0.055, n=36):
    return np.full(n, h)


def test_overflow_extension_mass_and_bounds():
    pmf = kc.extend_overflow_with_hazard(flat_hazard(0.055))
    assert pmf.shape == (kc.KCOUNT_CAP,)
    assert abs(pmf.sum() - 1.0) < 1e-9
    assert (pmf >= 0).all()
    # tail strictly decreasing WITHIN 37..cap; the 36->37 junction may
    # step up when the overflow mass is large (documented approximation)
    assert (np.diff(pmf[36:]) <= 1e-12).all()
    # overflow redistributed, not dumped: P(37..60) = original P(N>=37)
    from math import prod
    overflow = prod(1 - h for h in flat_hazard(0.055))
    assert abs(pmf[36:].sum() - overflow) < 1e-9


def test_overflow_extension_matches_37cat_body():
    from math import prod
    h = flat_hazard(0.06)
    pmf37 = np.empty(37)
    surv = 1.0
    for n in range(36):
        pmf37[n] = surv * h[n]
        surv *= 1 - h[n]
    pmf37[36] = surv
    full = kc.extend_overflow_with_hazard(h)
    assert np.abs(full[:36] - pmf37[:36]).max() < 1e-12


def test_bf_pmf_from_37_preserves_body_and_redistributes_overflow():
    h = flat_hazard(0.05)
    from math import prod
    pmf37 = np.empty(37)
    surv = 1.0
    for n in range(36):
        pmf37[n] = surv * h[n]
        surv *= 1 - h[n]
    pmf37[36] = surv
    full = kc.bf_pmf_from_37(pmf37)
    assert np.abs(full[:36] - pmf37[:36]).max() < 1e-12
    assert abs(full.sum() - 1.0) < 1e-9
    # all original overflow mass lands in 37..cap
    assert abs(pmf37[36] - full[36:].sum()) < 0.02


def test_binom_pmf_sanity():
    ks = np.arange(0, 25)
    p1 = kc.binom_pmf(ks, 0, 0.22)
    assert p1[0] == 1.0 and p1.sum() == pytest.approx(1.0)
    p2 = kc.binom_pmf(ks, 24, 0.22)
    assert p2.sum() == pytest.approx(1.0, abs=1e-9)
    assert p2.argmax() == 5  # mean 5.28 -> mode 5
    assert kc.binom_pmf(ks, 10, 0.0)[0] == 1.0
    assert kc.binom_pmf(ks, 10, 1.0)[10] == 1.0


def test_combine_count_matches_direct_binomial_at_fixed_n():
    bf = np.zeros(60)
    bf[23] = 1.0  # exactly N=24
    pk = kc.combine_count(bf, 0.22, k_max=25)
    direct = kc.binom_pmf(np.arange(25), 24, 0.22)
    assert np.abs(pk - direct).max() < 1e-9


def test_combine_count_mixture_is_weighted_average():
    bf = np.zeros(60)
    bf[11] = 0.5  # N=12
    bf[19] = 0.5  # N=20
    pk = kc.combine_count(bf, 0.25, k_max=25)
    mix = 0.5 * kc.binom_pmf(np.arange(25), 12, 0.25) \
        + 0.5 * kc.binom_pmf(np.arange(25), 20, 0.25)
    assert np.abs(pk - mix).max() < 1e-9


def test_exceedance_monotone_and_bounds():
    bf = np.zeros(60)
    bf[19] = 1.0
    pk = kc.combine_count(bf, 0.25, k_max=25)
    vals = [kc.exceedance(pk, m) for m in (4, 5, 6, 7, 8, 10, 12)]
    assert all(vals[i] >= vals[i + 1] - 1e-12 for i in range(len(vals) - 1))
    assert kc.exceedance(pk, 0) == 1.0
    assert 0.0 < vals[0] < 1.0
    assert kc.exceedance(pk, 40) == 0.0


def test_count_rps_and_logscore_sane():
    bf = np.zeros(60)
    bf[19] = 1.0
    pk = kc.combine_count(bf, 0.25, k_max=25)
    rps_hit = kc.count_rps(pk, 5)
    rps_miss = kc.count_rps(pk, 12)
    assert rps_hit < rps_miss
    assert kc.count_logscore(pk, 5) < kc.count_logscore(pk, 12)


def test_milestone_brier_structure():
    bf = np.zeros(60)
    bf[19] = 1.0
    pk = kc.combine_count(bf, 0.25, k_max=25)
    mb = kc.milestone_brier(pk, 6)
    assert set(mb) == {"ge6", "ge7", "ge8", "ge9", "ge10", "ge12"}
    assert all(0 <= v <= 1 for v in mb.values())
