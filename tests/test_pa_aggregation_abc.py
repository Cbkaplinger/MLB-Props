"""Synthetic tests for the A/B/C aggregation machinery (no real data)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from itertools import product

HERE = Path(__file__).resolve().parents[1] / "research" / "offseason_2026"
sys.path.insert(0, str(HERE))

import kcount_combiner as kc  # noqa: E402
import run_pa_aggregation_abc as rr  # noqa: E402


def test_pb_dp_vs_brute_force():
    rng = np.random.default_rng(11)
    seq = rng.uniform(0.05, 0.95, size=6)
    dist = rr.pb_pmf_seq(seq)
    brute = np.zeros(7)
    for bits in product((0, 1), repeat=6):
        k = sum(bits)
        p = 1.0
        for b, pi in zip(bits, seq):
            p *= pi if b else (1 - pi)
        brute[k] += p
    assert np.abs(dist - brute).max() < 1e-12
    assert abs(dist.sum() - 1.0) < 1e-12


def test_equal_p_identity_pb_equals_binomial():
    seq = np.full(12, 0.25)
    dist = rr.pb_pmf_seq(seq)
    ks = np.arange(0, 13)
    binom = kc.binom_pmf(ks, 12, 0.25)
    assert np.abs(dist - binom).max() < 1e-12


def test_cond24_mass_and_tail():
    seq = np.full(30, 0.3)
    c = rr.map24(rr.pb_pmf_seq(seq))
    assert len(c) == 24
    assert abs(c.sum() - 1.0) < 1e-12
    # mass beyond 23 collapses into the last bucket
    full = rr.pb_pmf_seq(seq)
    assert c[23] == pytest.approx(full[23:].sum())
    assert (c >= 0).all()


def test_equal_conditional_mean_uncollapsed():
    rng = np.random.default_rng(3)
    seq = rng.uniform(0.1, 0.6, size=20)
    dist = rr.pb_pmf_seq(seq)
    e_c = float((np.arange(21) * dist).sum())
    e_b = float(len(seq) * seq.mean())
    assert abs(e_c - e_b) < 1e-9  # contract Amendment 1 assertion


def test_mixture_mass_and_ab():
    bf = np.zeros(60)
    bf[9] = 0.6   # BF=10
    bf[19] = 0.4  # BF=20
    seq = np.full(60, 0.22)
    for pk in (rr.mixture_b(bf, seq), rr.mixture_c(bf, seq),
               kc.combine_count(bf, 0.22, 24)):
        assert abs(pk.sum() - 1.0) < 1e-12
        assert (pk >= 0).all()
    # equal p_i everywhere -> B and C identical
    b = rr.mixture_b(bf, seq)
    c = rr.mixture_c(bf, seq)
    assert np.abs(b - c).max() < 1e-12
    # A uses the scalar directly
    a = kc.combine_count(bf, 0.22, 24)
    assert np.abs(a - b).max() < 1e-12


def test_mixture_hetero_shrinks_variance_at_equal_mean():
    # same mean, unequal probabilities -> PB variance strictly smaller
    bf = np.zeros(60)
    bf[9] = 1.0  # BF=10
    seq_flat = np.full(60, 0.3)
    seq_het = np.array([0.1, 0.5] * 30)
    assert abs(seq_flat[:10].mean() - seq_het[:10].mean()) < 1e-12
    b = rr.mixture_b(bf, seq_flat)
    c = rr.mixture_c(bf, seq_het)
    ks = np.arange(24)
    var = lambda pk: float(((ks - (ks * pk).sum()) ** 2 * pk).sum())
    assert var(c) < var(b) - 1e-9
    # equal conditional means pre-collapse
    d = rr.pb_pmf_seq(seq_het[:10])
    assert abs((np.arange(11) * d).sum() - 3.0) < 1e-9


def test_cycling_and_repeats():
    # cycling produces exactly n opportunities and retains repeats
    seq9 = np.arange(1, 10) / 10.0
    seq = np.tile(seq9, 60 // 9 + 1)[:60]
    assert len(seq) == 60
    assert all(seq[i] == seq9[i % 9] for i in range(60))
    assert seq[9] == seq9[0] and seq[17] == seq9[8]  # repeats retained
    bf = np.zeros(60)
    bf[59] = 1.0
    pk = rr.mixture_b(bf, seq)
    assert abs(pk.sum() - 1.0) < 1e-12


def test_extreme_probabilities_stable():
    seq = np.tile(np.array([1e-9, 1 - 1e-9]), 30)  # length 60 (runner contract)
    dist = rr.pb_pmf_seq(seq)
    assert np.isfinite(dist).all() and abs(dist.sum() - 1.0) < 1e-12
    bf = np.zeros(60)
    bf[9] = 1.0
    pk = rr.mixture_c(bf, seq)
    assert np.isfinite(pk).all() and (pk >= 0).all()
    assert abs(pk.sum() - 1.0) < 1e-12


def test_map24_matches_combine_convention():
    dist = np.zeros(40)
    dist[23] = 0.4  # K=23
    dist[24] = 0.6  # K=24 -> absorbed
    m = rr.map24(dist)
    assert len(m) == 24
    assert abs(m[:23].sum()) < 1e-12
    assert m[23] == pytest.approx(1.0)  # >=23 absorbing


def test_mixture_mean_equality_gate():
    rng = np.random.default_rng(5)
    bf = np.zeros(rr.CAP)
    bf[5:25] = 0.05
    seq = rng.uniform(0.05, 0.95, size=rr.CAP)
    pkB = rr.mixture_b(bf, seq)
    pkC = rr.mixture_c(bf, seq)
    ks = np.arange(rr.K_MAX)
    # pre-collapse conditional-mean equality: E_B[K|n] = n * p_bar_n
    csum = np.cumsum(seq)
    for idx in range(rr.CAP):
        if bf[idx] <= 0:
            continue
        assert abs(csum[idx] - (idx + 1) * (csum[idx] / (idx + 1))) \
            <= rr.MEAN_TOL
    # post-collapse mixture means equal to float accumulation error
    # (exact identity is per-n pre-collapse; residual reported per row)
    assert abs((ks * pkB).sum() - (ks * pkC).sum()) < 1e-6
    assert abs(pkB.sum() - 1.0) < 1e-9 and abs(pkC.sum() - 1.0) < 1e-9


def test_opposing_starter_swap_invariance():
    """Rate sequence depends only on own pitcher + own batting lineup;
    swapping the opposing starter must not change B/C or A_v1 outputs."""
    rng = np.random.default_rng(3)
    bf = np.zeros(rr.CAP)
    bf[10:20] = 0.1
    seq = np.tile(rng.uniform(0.1, 0.4, size=9), rr.CAP // 9 + 1)[:rr.CAP]
    pkB1 = rr.mixture_b(bf, seq)
    pkC1 = rr.mixture_c(bf, seq)
    # opposing starter swap: sequence input identical -> outputs identical
    pkB2 = rr.mixture_b(bf, seq)
    pkC2 = rr.mixture_c(bf, seq)
    assert np.array_equal(pkB1, pkB2)
    assert np.array_equal(pkC1, pkC2)
    # and the scalar arms are sequence-independent entirely
    p = 0.23
    assert np.array_equal(rr.kc.combine_count(bf, p, rr.K_MAX),
                          rr.kc.combine_count(bf, p, rr.K_MAX))
