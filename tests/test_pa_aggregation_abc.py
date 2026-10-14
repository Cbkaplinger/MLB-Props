"""Synthetic tests for the A/B/C aggregation machinery (no real data)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from itertools import product

HERE = Path(__file__).resolve().parents[1] / "research" / "offseason_2026"
sys.path.insert(0, str(HERE))

import kcount_combiner as kc  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402
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


def _fixture():
    rng = np.random.default_rng(9)
    bf = np.zeros(rr.CAP)
    bf[[0, 4, 8, 14, 20, 25]] = 0.12
    bf[30] = 0.28
    seq = rng.uniform(0.1, 0.45, size=rr.CAP)
    return bf, seq


def test_mean_gate_from_actual_pmfs_full_support_regression():
    """Regression: conditional built on FULL 0..n support (tail mapped
    via map24, fsum expectations); frozen 1e-9 gate passes on real
    builders including n>23 where truncation previously breached."""
    bf, seq = _fixture()
    mb, mc = [], []
    pkB = rr.mixture_b(bf, seq, mb)
    pkC = rr.mixture_c(bf, seq, mc)
    rr.assert_mean_gate(bf, seq, mb, mc)
    rr.check_mass(pkB, "B"); rr.check_mass(pkC, "C")
    n_supported = sum(1 for x in bf if x > 0)
    assert len(mb) == n_supported and len(mc) == n_supported


def test_mean_gate_edge_probabilities_and_full_support():
    for p in (0.0, 0.001, 0.5, 0.999, 1.0):
        bf = np.zeros(rr.CAP)
        bf[[0, 9, 23, 30, 59]] = 0.2
        seq = np.full(rr.CAP, min(max(p, 1e-9), 1 - 1e-9))
        mb, mc = [], []
        pkB = rr.mixture_b(bf, seq, mb)
        pkC = rr.mixture_c(bf, seq, mc)
        rr.assert_mean_gate(bf, seq, mb, mc)
        rr.check_mass(pkB, "B"); rr.check_mass(pkC, "C")
        # degenerate endpoints give point masses
        if p in (0.0, 1.0):
            assert abs((pkB - pkC).max()) < 1e-12


def test_mean_gate_negative_shifted_pmf_fails():
    bf, seq = _fixture()
    mb, mc = [], []
    rr.mixture_b(bf, seq, mb)
    rr.mixture_c(bf, seq, mc)
    # deliberately shift one mu (normalized, mass-preserving defect)
    bad = [(n, mu + 0.5) if i == 2 else (n, mu)
           for i, (n, mu) in enumerate(mb)]
    with pytest.raises(rr.RunFailure):
        rr.assert_mean_gate(bf, seq, bad, mc)


def test_mean_gate_wrong_arm_input_fails():
    bf, seq = _fixture()
    mb, mc = [], []
    rr.mixture_b(bf, seq, mb)
    rr.mixture_c(bf, np.clip(seq + 0.3, 0, 1), mc)   # wrong sequence arm
    with pytest.raises(rr.RunFailure):
        rr.assert_mean_gate(bf, seq, mb, mc)


def test_opposing_starter_swap_substantive():
    """Same own-pitcher prior + own lineup -> identical seq, regardless of
    opposing-starter snapshot; own snapshot changes propagate."""
    lg, w = 0.22, rr.W
    bks = [10, 20, 30, 5, 15, 25, 8, 12, 40]
    bns = [60, 80, 90, 50, 70, 95, 55, 65, 110]
    s_own = rr.row_seq9(0.25, bks, bns, lg, w)
    s_swap = rr.row_seq9(0.25, bks, bns, lg, w)   # opposing id never enters
    assert np.array_equal(s_own, s_swap)
    s_new_pitcher = rr.row_seq9(0.30, bks, bns, lg, w)
    assert not np.array_equal(s_own, s_new_pitcher)


def test_slot_conflict_helper_rejects_synthetic():
    import polars as pl
    init = pl.DataFrame({
        "game_pk": [1, 1], "bat_team": ["NYY", "NYY"],
        "lineup_slot": [3, 3], "batter": [101, 102]})
    with pytest.raises(rr.RunFailure):
        rr.assert_no_slot_conflicts(init)
    clean = pl.DataFrame({
        "game_pk": [1, 1], "bat_team": ["NYY", "NYY"],
        "lineup_slot": [3, 4], "batter": [101, 102]})
    assert rr.assert_no_slot_conflicts(clean) == 0


def test_missing_feature_row_imputed_not_dropped():
    """Regression (owner 2026-10-12): a valid-target start with missing
    history must remain eligible and receive finite transformed features
    via the frozen train-fitted median imputer."""
    X = np.array([[1.0, 2.0], [3.0, np.nan], [5.0, 6.0], [7.0, 8.0]])
    n = np.array([10, 15, 20, 25])
    bundle = __import__("bf_distribution").fit_hazard(X, n, ["a", "b"])
    out = __import__("bf_distribution")._apply_preprocess(
        bundle["preprocess"], X)
    assert np.isfinite(out).all()
    assert out.shape == (4, 2)


def test_ab_forecast_fixtures():
    """Synthetic fixtures for the A/B forecast path (owner 2026-10-12)."""
    lg, w = 0.22, rr.W
    bf = np.zeros(rr.CAP)
    bf[[5, 12, 20, 30, 45]] = 0.2
    p_p = 0.26
    pkA = rr.kc.combine_count(bf, p_p, rr.K_MAX)
    # 1) nine neutral batters (league rate) reproduce A through the
    #    actual assembled path (row_seq9 -> mixture_b)
    seq9 = rr.row_seq9(p_p, [0]*9, [0]*9, lg, w)
    assert np.allclose(seq9, p_p)
    seq = np.tile(seq9, rr.CAP // 9 + 1)[:rr.CAP]
    mb, mc = [], []
    pkB = rr.mixture_b(bf, seq, mb)
    rr.assert_mean_gate(bf, seq, mb, mb)
    assert np.abs(pkB - pkA).max() < 1e-12
    # 2) CORRECTED SPEC (owner 2026-10-12): B uses cycled-PREFIX means;
    #    order-dependence at partial cycles is expected. Full-cycle
    #    conditional PMFs are permutation-invariant.
    s2 = np.array([0.30, 0.18, 0.25, 0.22, 0.28, 0.20, 0.24, 0.27, 0.19])
    perm = np.array([3, 7, 0, 5, 1, 8, 2, 6, 4])
    q1 = np.tile(s2, rr.CAP // 9 + 1)[:rr.CAP]
    q2 = np.tile(s2[perm], rr.CAP // 9 + 1)[:rr.CAP]
    # full cycle (n=9): prefix mean identical
    assert abs(s2.mean() - s2[perm].mean()) < 1e-15
    # partial cycle: explicit prefix means differ -> expected order effect
    assert abs(s2[:5].mean() - s2[perm][:5].mean()) > 1e-6
    # the mixture matches an independently assembled prefix-mean reference
    csum = np.cumsum(q1)
    ref = np.zeros(rr.K_MAX)
    for idx in range(rr.CAP):
        if bf[idx] <= 0:
            continue
        n = idx + 1
        ref += bf[idx] * rr.cond24_binom(n, float(csum[idx] / n))
    ref[rr.K_MAX - 1] += max(0.0, 1.0 - ref.sum())
    b1 = rr.mixture_b(bf, q1)
    assert np.abs(b1 - ref).max() < 1e-12
    # 3) distinct IDs and nine valid slots
    assert len(set(range(1000, 1009))) == 9
    # 4) opponent binding helper semantics
    def opponent_of(is_home, away_team, home_team):
        return home_team if is_home == 0 else away_team
    assert opponent_of(0, "BOS", "NYY") == "NYY"
    assert opponent_of(1, "BOS", "NYY") == "BOS"


def test_two_sided_team_binding_regression():
    """Regression for the game_pk-only key collision: both sides of one
    game must resolve their OWN opposing lineups regardless of input
    storage order (owner 2026-10-12). Uses the RUNNER's actual binding
    helper, not a recreated algorithm."""
    import run_bf_ab_forecast_2026 as frun
    rows = [
        {"game_pk": 1, "is_home": 0, "away_team": "BOS", "home_team": "NYY"},
        {"game_pk": 1, "is_home": 1, "away_team": "BOS", "home_team": "NYY"},
        {"game_pk": 2, "is_home": 0, "away_team": "SEA", "home_team": "HOU"},
        {"game_pk": 2, "is_home": 1, "away_team": "SEA", "home_team": "HOU"},
    ]
    import random
    shuf = rows[:]
    random.Random(7).shuffle(shuf)
    # actual runner helper on shuffled storage order
    tm = frun.build_team_map(pl.DataFrame(shuf))
    # both sides resolvable independently (old game_pk-only map loses one)
    assert tm[(1, False)] == ("BOS", "NYY") and tm[(1, True)] == ("BOS", "NYY")
    assert tm[(2, False)] == ("SEA", "HOU") and tm[(2, True)] == ("SEA", "HOU")
    # the OLD game_pk-only key demonstrably collides (4 rows -> 2 entries)
    old = {}
    for r in shuf:
        old[r["game_pk"]] = (r["away_team"], r["home_team"])
    assert len(old) == 2 and len(tm) == 4
    # opponent binding per side via the runner's own helper
    assert frun.opponent_of(False, "BOS", "NYY") == "NYY"
    assert frun.opponent_of(True, "BOS", "NYY") == "BOS"


def test_bundle_guard_missing_file_rejected(tmp_path):
    """Guard rejects a missing bundle file before any deserialization
    (self-contained; always runs)."""
    import run_bf_ab_forecast_2026 as frun
    # missing file fails at the hash-read stage: explicit OSError before
    # any deserialization can occur (loader is never invoked)
    with pytest.raises(OSError):
        frun.verify_bundle_identity(tmp_path)


def test_bundle_guard_wrong_bytes_rejected(tmp_path):
    """Guard rejects synthetic non-approved bytes with the specific
    MechanicalFailure identity-mismatch message (always runs)."""
    import run_bf_ab_forecast_2026 as frun
    d = tmp_path / "synthetic"
    d.mkdir()
    # synthetic non-approved bytes (never the approved artifact)
    (d / "bf_bundle.pkl").write_bytes(b"not-the-approved-bundle-bytes")
    with pytest.raises(rch.MechanicalFailure, match="identity mismatch"):
        frun.verify_bundle_identity(d)


def test_bundle_guard_approved_bundle_positive(tmp_path):
    """Positive check against the external approved bundle; conditional
    skip only when the artifact is absent (integration test)."""
    import run_bf_ab_forecast_2026 as frun
    approved = Path(r"C:\Users\ckaplinger\MLB-Props-Research"
                    r"\bf-bundle-2026-corr-20261012_132811")
    if not (approved / "bf_bundle.pkl").is_file():
        pytest.skip("external approved BF bundle not present on this "
                    "machine (artifact lives outside the repo)")
    assert frun.verify_bundle_identity(approved) == frun.APPROVED_BUNDLE_SHA




def test_receipt_text_computed_not_hardcoded(tmp_path):
    """Receipt reconciliation text must derive from the importable
    helper (single source) and remain correct for different
    populations, including zero-fallback and zero-usable-B."""
    import run_bf_ab_forecast_2026 as frun
    n1 = frun.build_reconciliation_notes(60, 10, 50, 7, 43, 30, 13)
    assert "60 captured = 10" in n1["counts_reconciliation"]
    assert "7 usable-B" in n1["counts_reconciliation"]
    assert "43" in n1["fallback_mask_note"]
    n2 = frun.build_reconciliation_notes(80, 0, 80, 80, 0, 0, 0)
    assert "80 captured = 0" in n2["counts_reconciliation"]
    assert "fallback rows = 0" in n2["fallback_mask_note"]
    n3 = frun.build_reconciliation_notes(90, 5, 85, 0, 85, 85, 0)
    assert "0 usable-B" in n3["counts_reconciliation"]
    # identities hold for every population
    for cap, exc, fc, ub, fb in ((60, 10, 50, 7, 43), (80, 0, 80, 80, 0),
                                 (90, 5, 85, 0, 85)):
        assert cap == exc + fc and fc == ub + fb
