"""Tests for the ordered starter-only opportunity layer (I3)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import kcount_combiner as kc  # noqa: E402
import lineup_opportunity as lo  # noqa: E402
import run_kcount_integration_2023 as rkc  # noqa: E402


def bf_ext(h=0.075, cap=60):
    pmf = np.empty(cap)
    surv = 1.0
    for n in range(cap):
        pmf[n] = surv * h
        surv *= 1 - h
    return pmf / pmf.sum()


def test_pb_prefix_matches_binomial_when_probs_equal():
    # equal p_j -> each prefix distribution equals the frozen binomial
    # path (point_exposure_pmf) exactly
    ext = bf_ext()
    seq = lo.opportunity_sequence(np.full(9, 0.25), len(ext))
    pre = lo.pb_prefix_dists(seq)
    for n in (1, 5, 9, 10, 23, 24, 41, 60):
        ref = rkc.point_exposure_pmf(n, 0.25)
        assert np.allclose(pre[n - 1], ref, atol=1e-12), n


def test_pb_mass_conservation_and_absorbing_bucket():
    rng = np.random.default_rng(7)
    seq = rng.uniform(0.05, 0.45, size=60)
    pre = lo.pb_prefix_dists(seq)
    assert np.allclose(pre.sum(axis=1), 1.0, atol=1e-12)
    # absorbing bucket is non-decreasing in n
    assert (np.diff(pre[:, 23]) >= -1e-15).all()


def test_mixture_ordered_identity_vs_combine_count_uniform():
    # uniform slots must reproduce the frozen homogeneous mixture EXACTLY
    ext = bf_ext()
    pk_ord = lo.mixture_ordered(ext, np.full(9, 0.22))
    pk_hom = kc.combine_count(ext, 0.22)
    assert np.allclose(pk_ord, pk_hom, atol=1e-12)
    assert abs(pk_ord.sum() - 1.0) < 1e-12


def test_mixture_ordered_absorbing_tail_matches_marginal():
    ext = bf_ext(h=0.06)
    slots = np.array([0.3, 0.2, 0.25, 0.35, 0.15, 0.28, 0.22, 0.30, 0.18])
    pk = lo.mixture_ordered(ext, slots)
    assert abs(pk.sum() - 1.0) < 1e-9
    # P(K>=23) from the mixture = mean over n of P(K>=23 | N=n)
    pre = lo.pb_prefix_dists(lo.opportunity_sequence(slots, len(ext)))
    ref = float((ext * pre[:, 23]).sum())
    assert pk[23] == pytest.approx(ref, abs=1e-12)


def test_p_star_parity_with_expected_k():
    ext = bf_ext()
    slots = np.array([0.3, 0.2, 0.25, 0.35, 0.15, 0.28, 0.22, 0.30, 0.18])
    ek_ord = lo.expected_k_ordered(ext, slots)
    ps = lo.p_star(ext, slots)
    en = kc.expected_bf(ext)
    # I3b expected K = p* * E[N] must equal I3a expected K exactly
    assert ps * en == pytest.approx(ek_ord, abs=1e-12)


def test_p_star_is_not_the_unweighted_average():
    # early slots repeat more often: with a front-loaded high-p card,
    # p* must exceed the unweighted nine-player mean
    ext = bf_ext(h=0.05)  # long outings -> late trips matter
    slots = np.array([0.40, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10,
                      0.10])
    ps = lo.p_star(ext, slots)
    assert ps > float(slots.mean())


def test_survival_properties_and_encounter_formula():
    ext = bf_ext(h=0.075)
    s = lo.bf_survival(ext)
    assert s[0] == pytest.approx(1.0, abs=1e-12)  # S(1) = P(N>=1) = 1
    assert (np.diff(s) <= 1e-15).all()  # non-increasing
    # encounter formula: P(slot j faced >= r times) = S(j + 9(r-1))
    for j, r in ((1, 2), (1, 3), (9, 2), (5, 3)):
        assert s[j + 9 * (r - 1) - 1] >= 0.0
    # P(exactly r meetings) = S(j+9(r-1)) - S(j+9r); sums to S(j)
    j = 3
    diffs = [s[j + 9 * (r - 1) - 1] - s[j + 9 * r - 1] for r in (1, 2, 3)]
    assert all(d >= -1e-15 for d in diffs)


def test_card_first_nine_order_distinct_and_fail_loud():
    rows = [11, 12, 13, 14, 15, 16, 17, 18, 19, 11, 12, 20, 13]
    card = lo.card_first_nine(rows)
    assert card == [11, 12, 13, 14, 15, 16, 17, 18, 19]
    with pytest.raises(ValueError):
        lo.card_first_nine([1, 2, 3, 1, 2, 3, 1, 2, 3, 1])


def test_slot_probs_log5_and_cold_start():
    rates = {101: (0.30, 500)}
    p = lo.slot_probs([101, 102], 0.28, rates, lg=0.22, w=150.0)
    # cold-start batter 102 falls back to the league rate -> log5
    # collapses to the shrunk pitcher rate
    assert p[1] == pytest.approx(0.28, abs=1e-6)
    # batter 101 above league -> matchup prob above the pitcher rate
    assert p[0] > 0.28
    assert ((p > 0) & (p < 1)).all()


def test_cap_120_applicability():
    ext120 = bf_ext(h=0.055, cap=120)
    slots = np.full(9, 0.24)
    pk = lo.mixture_ordered(ext120, slots)
    assert abs(pk.sum() - 1.0) < 1e-9
    ps = lo.p_star(ext120, slots)
    assert ps == pytest.approx(0.24, abs=1e-9)  # uniform slots: p* = p
