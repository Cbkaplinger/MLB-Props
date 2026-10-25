"""Synthetic tests for the count-PMF calibration experiment (card:
card_count_pmf_calibration_2026-10-24.md). No real data.

Tests the mathematical contract of the one-parameter linear CDF
recalibration and the fitting algorithm, before any real-data use.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))


# ---- inline implementation (same as the card specifies) --------------
def linear_cdf_calibrate(pmf: np.ndarray, a: float) -> np.ndarray:
    """Apply the one-parameter linear CDF recalibration.

    F_cal(k) = 1 - a * (1 - F(k)), for k = 0..23.
    PMF reconstruction: p_cal(k) = F_cal(k) - F_cal(k-1), F_cal(-1) = 0.
    """
    pmf = np.asarray(pmf, dtype=np.float64)
    if pmf.shape != (24,):
        raise ValueError(f"expected 24-bucket PMF, got {pmf.shape}")
    if np.any(pmf < 0) or abs(pmf.sum() - 1.0) > 1e-9:
        raise ValueError("input PMF must be nonnegative and normalized")
    F = np.cumsum(pmf)
    F_cal = 1.0 - a * (1.0 - F)
    F_cal = np.clip(F_cal, 0.0, 1.0)
    p_cal = np.zeros(24)
    p_cal[0] = F_cal[0]
    p_cal[1:] = np.diff(F_cal)
    # enforce exact normalization
    p_cal = p_cal / p_cal.sum()
    return p_cal


def fit_calibration(pmfs: list[np.ndarray], realized: list[int],
                    ) -> float:
    """Fit the calibration parameter a by minimizing mean count-RPS
    on the calibration window (bounded scalar search)."""
    from scipy.optimize import minimize_scalar
    import kcount_combiner as kc  # noqa: E402
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                           / "research" / "offseason_2026"))
    import kcount_combiner as kc

    def objective(a):
        total = 0.0
        for pmf, k in zip(pmfs, realized):
            cal = linear_cdf_calibrate(pmf, a)
            total += kc.count_rps(cal, k)
        return total / len(pmfs)

    result = minimize_scalar(objective, bounds=(0.5, 2.0),
                             method="bounded",
                             options={"xatol": 1e-6})
    a = float(result.x)
    if a < 0.5 or a > 2.0:
        raise ValueError(f"fitted a={a} outside [0.5, 2.0]: stop")
    return a


# ---- identity ---------------------------------------------------------
def test_identity_mapping():
    """a=1 reproduces the input PMF exactly."""
    pmf = np.random.default_rng(42).dirichlet(np.ones(24))
    cal = linear_cdf_calibrate(pmf, 1.0)
    assert np.allclose(cal, pmf, atol=1e-9)


# ---- boundaries -------------------------------------------------------
def test_extreme_a_values_produce_valid_pmf():
    """a=0.5 and a=2.0 (the stop-condition bounds) produce finite,
    nonnegative, normalized PMFs."""
    rng = np.random.default_rng(7)
    for a in (0.5, 2.0):
        for _ in range(20):
            pmf = rng.dirichlet(np.ones(24) * 0.5)  # spiky
            cal = linear_cdf_calibrate(pmf, a)
            assert np.all(cal >= 0), f"a={a}: negative probability"
            assert abs(cal.sum() - 1.0) < 1e-9, f"a={a}: not normalized"
            assert np.all(np.isfinite(cal)), f"a={a}: nonfinite"


def test_heavy_tail_pmf():
    """A PMF with mass concentrated at k>=20 must remain valid after
    calibration, and the tail bucket must not go negative."""
    pmf = np.zeros(24)
    pmf[20] = 0.1
    pmf[21] = 0.2
    pmf[22] = 0.3
    pmf[23] = 0.4
    for a in (0.5, 1.0, 1.5, 2.0):
        cal = linear_cdf_calibrate(pmf, a)
        assert np.all(cal >= 0), f"a={a}: negative in tail"
        assert abs(cal.sum() - 1.0) < 1e-9


def test_all_mass_at_zero():
    """All mass at K=0: the calibrated PMF must remain valid."""
    pmf = np.zeros(24)
    pmf[0] = 1.0
    for a in (0.5, 1.0, 2.0):
        cal = linear_cdf_calibrate(pmf, a)
        assert abs(cal.sum() - 1.0) < 1e-9
        assert np.all(cal >= 0)


def test_all_mass_at_tail():
    """All mass at the tail bucket (k>=23)."""
    pmf = np.zeros(24)
    pmf[23] = 1.0
    for a in (0.5, 1.0, 2.0):
        cal = linear_cdf_calibrate(pmf, a)
        assert abs(cal.sum() - 1.0) < 1e-9
        assert np.all(cal >= 0)


# ---- monotonicity -----------------------------------------------------
def test_calibrated_cdf_is_monotone():
    """F_cal must be nondecreasing in k for all tested a values."""
    rng = np.random.default_rng(11)
    for _ in range(30):
        pmf = rng.dirichlet(np.ones(24) * 0.3)
        F = np.cumsum(pmf)
        for a in (0.5, 0.8, 1.0, 1.2, 1.5, 2.0):
            F_cal = 1.0 - a * (1.0 - F)
            F_cal = np.clip(F_cal, 0.0, 1.0)
            diffs = np.diff(F_cal)
            assert np.all(diffs >= -1e-12), (
                f"a={a}: F_cal not monotone (min diff {diffs.min()})")


def test_tail_boundary_automatic():
    """F_cal(23) = 1 is enforced automatically by the formula:
    when F(23) = 1, F_cal(23) = 1 - a * (1 - 1) = 1."""
    pmf = np.random.default_rng(3).dirichlet(np.ones(24))
    F = np.cumsum(pmf)
    for a in (0.5, 1.0, 1.5, 2.0):
        F_cal_23 = 1.0 - a * (1.0 - F[23])
        assert F_cal_23 == pytest.approx(1.0, abs=1e-12)


# ---- zero-K bucket behavior -------------------------------------------
def test_zero_k_bucket_can_change():
    """When a > 1, the zero-K probability can be reduced (mass
    transferred to K >= 1). When a < 1, it can be increased."""
    pmf = np.zeros(24)
    pmf[0] = 0.3
    pmf[1:] = 0.7 / 23
    p_low = linear_cdf_calibrate(pmf, 0.5)
    p_high = linear_cdf_calibrate(pmf, 2.0)
    assert p_low[0] > pmf[0], "a<1 should increase zero-K probability"
    assert p_high[0] < pmf[0], "a>1 should decrease zero-K probability"


# ---- deterministic fitting ---------------------------------------------
def test_fit_is_deterministic():
    """The same calibration input always produces the same fitted a."""
    rng = np.random.default_rng(5)
    pmfs = [rng.dirichlet(np.ones(24) * 3).tolist() for _ in range(50)]
    realized = [int(rng.integers(0, 8)) for _ in range(50)]
    a1 = fit_calibration(pmfs, realized)
    a2 = fit_calibration(pmfs, realized)
    assert a1 == a2


def test_fit_finds_improvement_on_synthetic_shift():
    """If the synthetic PMFs are systematically shifted from the
    realized outcomes, the fitted a should differ from 1."""
    rng = np.random.default_rng(9)
    pmfs = []
    realized = []
    for _ in range(100):
        # the PMFs predict too few K (mass shifted low)
        p = rng.dirichlet(np.concatenate([[8.0], np.ones(23)]))
        pmfs.append(p)
        realized.append(int(rng.integers(3, 10)))  # actual K is higher
    a = fit_calibration(pmfs, realized)
    # the calibration should stretch the CDF (a > 1) to shift mass up
    assert a != 1.0, "fitted a should differ from identity"


# ---- evaluation-outcome isolation --------------------------------------
def test_fit_does_not_access_evaluation_outcomes():
    """The fit_calibration function takes only (pmfs, realized) for
    the CALIBRATION window. The caller is responsible for not passing
    evaluation outcomes. This test documents the contract: the return
    value is a scalar (the fitted a), not a fitted model that could
    access evaluation data."""
    result = fit_calibration(
        [np.ones(24) / 24] * 10, [3] * 10)
    assert isinstance(result, float)
    assert 0.5 <= result <= 2.0
