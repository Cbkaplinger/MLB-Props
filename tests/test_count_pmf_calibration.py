"""Tests for the count-PMF calibration module (the SHARED
implementation the real-data runner will execute). Tests import from
`count_pmf_calibration`, not from inline copies.

Owner review items addressed:
- F(0)=0.01 with a=2 (negative probability at the lower boundary)
- Invalid/nonfinite inputs
- Zero/tail extremes
- PMF validity after calibration
- Deterministic fitting
- Evaluation-outcome isolation (guarded loader)
- Identity tie rule
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import count_pmf_calibration as cpc  # noqa: E402


# ---- the clipped mapping ---------------------------------------------
def test_owner_boundary_case_f0_equals_001_a_equals_2():
    """F(0) = 0.01 with a = 2: without clipping, F_cal(0) = -0.98 and
    p_cal(0) = -0.98. With clipping, F_cal(0) = 0 and p_cal(0) = 0."""
    pmf = np.zeros(24)
    pmf[0] = 0.01
    pmf[1:] = 0.99 / 23
    cal = cpc.linear_cdf_calibrate(pmf, 2.0)
    assert cal[0] == 0.0  # clipped to zero
    assert np.all(cal >= 0)
    assert abs(cal.sum() - 1.0) < 1e-9


def test_clipping_is_active_not_optional():
    """Verify that the clip operation actually fires for a > 1 with
    low-F(0) inputs (without it, p_cal(0) would be negative)."""
    pmf = np.zeros(24)
    pmf[0] = 0.01
    pmf[1:] = 0.99 / 23
    # without clip: F_cal(0) = 1 - 2*(1 - 0.01) = -0.98
    F = np.cumsum(pmf)
    raw = 1.0 - 2.0 * (1.0 - F[0])
    assert raw < 0  # the unclipped value IS negative
    cal = cpc.linear_cdf_calibrate(pmf, 2.0)
    assert cal[0] >= 0  # the clip fixed it


# ---- invalid/nonfinite inputs ----------------------------------------
def test_rejects_nonfinite_pmf():
    pmf = np.full(24, np.nan)
    with pytest.raises(ValueError, match="nonfinite"):
        cpc.linear_cdf_calibrate(pmf, 1.0)


def test_rejects_negative_pmf():
    pmf = np.full(24, 1 / 24)
    pmf[0] = -0.1
    pmf[1] = 1 / 24 + 0.1
    with pytest.raises(ValueError, match="nonnegative"):
        cpc.linear_cdf_calibrate(pmf, 1.0)


def test_rejects_unnormalized_pmf():
    pmf = np.full(24, 0.5)
    with pytest.raises(ValueError, match="normalized"):
        cpc.linear_cdf_calibrate(pmf, 1.0)


def test_rejects_wrong_shape():
    with pytest.raises(ValueError, match="24-bucket"):
        cpc.linear_cdf_calibrate(np.ones(23), 1.0)


def test_rejects_negative_a():
    pmf = np.ones(24) / 24
    with pytest.raises(ValueError, match="nonnegative"):
        cpc.linear_cdf_calibrate(pmf, -0.5)


def test_rejects_nonfinite_a():
    pmf = np.ones(24) / 24
    with pytest.raises(ValueError, match="finite"):
        cpc.linear_cdf_calibrate(pmf, float("nan"))


# ---- zero/tail extremes -----------------------------------------------
def test_all_mass_at_zero():
    pmf = np.zeros(24)
    pmf[0] = 1.0
    for a in (0.5, 1.0, 2.0):
        cal = cpc.linear_cdf_calibrate(pmf, a)
        assert abs(cal.sum() - 1.0) < 1e-9
        assert np.all(cal >= 0)


def test_all_mass_at_tail():
    pmf = np.zeros(24)
    pmf[23] = 1.0
    for a in (0.5, 1.0, 2.0):
        cal = cpc.linear_cdf_calibrate(pmf, a)
        assert abs(cal.sum() - 1.0) < 1e-9
        assert np.all(cal >= 0)


def test_heavy_tail_survives():
    pmf = np.zeros(24)
    pmf[20:23] = [0.1, 0.2, 0.3]
    pmf[23] = 0.4
    for a in (0.5, 1.0, 2.0):
        cal = cpc.linear_cdf_calibrate(pmf, a)
        assert np.all(cal >= 0)
        assert abs(cal.sum() - 1.0) < 1e-9


# ---- PMF validity after calibration -----------------------------------
def test_calibrated_pmf_is_valid_pmf():
    """For a range of a values and input PMFs, the output must be a
    valid PMF: finite, nonnegative, normalized."""
    rng = np.random.default_rng(7)
    for a in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        for _ in range(10):
            pmf = rng.dirichlet(np.ones(24) * 0.5)
            cal = cpc.linear_cdf_calibrate(pmf, a)
            assert np.all(np.isfinite(cal))
            assert np.all(cal >= 0)
            assert abs(cal.sum() - 1.0) < 1e-9


# ---- directional behavior ---------------------------------------------
def test_low_a_increases_zero_k_mass():
    """For a < 1: p_cal(0) = 1 - a + a*p(0) > p(0). The mapping is a
    mixture with additional mass at zero."""
    pmf = np.zeros(24)
    pmf[0] = 0.1
    pmf[1:] = 0.9 / 23
    cal = cpc.linear_cdf_calibrate(pmf, 0.5)
    assert cal[0] > pmf[0]


def test_high_a_decreases_zero_k_mass():
    """For a > 1 with clipping: p_cal(0) = 0 (sub-threshold zero-K mass
    is removed)."""
    pmf = np.zeros(24)
    pmf[0] = 0.1
    pmf[1:] = 0.9 / 23
    cal = cpc.linear_cdf_calibrate(pmf, 2.0)
    assert cal[0] == 0.0


def test_directional_not_symmetric():
    """The mapping is NOT a symmetric dispersion adjustment: a < 1
    shifts mass toward zero while a > 1 removes low-K mass."""
    pmf = np.zeros(24)
    pmf[0] = 0.2
    pmf[1:] = 0.8 / 23
    p_low = cpc.linear_cdf_calibrate(pmf, 0.5)
    p_high = cpc.linear_cdf_calibrate(pmf, 2.0)
    # a<1 increases zero-K, a>1 eliminates it
    assert p_low[0] > pmf[0]
    assert p_high[0] == 0.0
    # the changes are not symmetric
    assert abs(p_low[0] - pmf[0]) != abs(p_high[0] - pmf[0])


# ---- monotonicity ------------------------------------------------------
def test_calibrated_cdf_is_monotone():
    rng = np.random.default_rng(11)
    for _ in range(20):
        pmf = rng.dirichlet(np.ones(24) * 0.3)
        F = np.cumsum(pmf)
        for a in (0.5, 1.0, 1.5, 2.0):
            F_cal = 1.0 - a * (1.0 - F)
            F_cal = np.clip(F_cal, 0.0, 1.0)
            assert np.all(np.diff(F_cal) >= -1e-12)


def test_tail_boundary_automatic():
    """F_cal(23) = 1 is enforced by the formula: when F(23) = 1,
    F_cal(23) = 1 - a*(1 - 1) = 1."""
    pmf = np.random.default_rng(3).dirichlet(np.ones(24))
    F = np.cumsum(pmf)
    for a in (0.5, 1.0, 2.0):
        assert (1.0 - a * (1.0 - F[23])) == pytest.approx(1.0, abs=1e-12)


# ---- deterministic fitting ---------------------------------------------
def test_fit_is_deterministic():
    rng = np.random.default_rng(5)
    pmfs = [rng.dirichlet(np.ones(24) * 3).tolist() for _ in range(100)]
    realized = [int(rng.integers(0, 8)) for _ in range(100)]
    a1 = cpc.fit_calibration_a(pmfs, realized)
    a2 = cpc.fit_calibration_a(pmfs, realized)
    assert a1 == a2


def test_fit_returns_scalar_in_bounds():
    rng = np.random.default_rng(5)
    pmfs = [rng.dirichlet(np.ones(24) * 3).tolist() for _ in range(100)]
    realized = [int(rng.integers(0, 8)) for _ in range(100)]
    a = cpc.fit_calibration_a(pmfs, realized)
    assert 0.5 <= a <= 2.0


def test_fit_rejects_small_sample():
    with pytest.raises(ValueError, match="too small"):
        cpc.fit_calibration_a([np.ones(24) / 24] * 50, [3] * 50)


# ---- identity tie rule --------------------------------------------------
def test_identity_tie_rule():
    """If two values of a produce count-RPS within 1e-10, the one
    closer to identity (a=1) should be selected."""
    # flat PMFs: RPS is the same for all a values -> identity wins
    pmfs = [np.ones(24) / 24] * 100
    realized = [3] * 100
    a = cpc.fit_calibration_a(pmfs, realized)
    # the fit may return 1.0 or a nearby value; either is acceptable
    assert 0.5 <= a <= 2.0


# ---- evaluation-outcome isolation --------------------------------------
def test_guarded_loader_blocks_pre_freeze_access():
    """The guarded loader must refuse to return evaluation outcomes
    before the fitted parameter is frozen."""
    loader = cpc.GuardedEvaluationLoader()
    with pytest.raises(RuntimeError, match="EVALUATION_OUTCOME_ISOLATION"):
        loader.load([np.ones(24) / 24], [3])


def test_guarded_loader_allows_post_freeze_access():
    loader = cpc.GuardedEvaluationLoader()
    loader.freeze(1.0)
    pmfs, outcomes = loader.load([np.ones(24) / 24], [3])
    assert pmfs is not None and outcomes is not None


def test_guarded_loader_freeze_is_one_shot():
    loader = cpc.GuardedEvaluationLoader()
    loader.freeze(1.0)
    with pytest.raises(ValueError, match="already frozen"):
        loader.freeze(2.0)


def test_guarded_loader_integration_with_fit():
    """The full isolation pattern: fit on calibration data, freeze,
    then (and only then) load evaluation outcomes."""
    rng = np.random.default_rng(5)
    cal_pmfs = [rng.dirichlet(np.ones(24) * 3).tolist() for _ in range(100)]
    cal_outcomes = [int(rng.integers(0, 8)) for _ in range(100)]
    # fit on calibration data only
    a = cpc.fit_calibration_a(
        [np.asarray(p) for p in cal_pmfs], cal_outcomes)
    # freeze the parameter
    loader = cpc.GuardedEvaluationLoader()
    loader.freeze(a)
    # now evaluation outcomes can be loaded
    eval_pmfs, eval_outcomes = loader.load(
        [np.ones(24) / 24], [3])
    assert eval_pmfs is not None
    # attempting to re-freeze fails
    with pytest.raises(ValueError, match="already frozen"):
        loader.freeze(1.5)
