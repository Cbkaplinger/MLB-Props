"""Count-PMF calibration: one-parameter linear CDF recalibration.

RESEARCH-ONLY. Implements the pre-registered calibration method from
card_count_pmf_calibration_2026-10-24.md (revised per owner review).
This module is the SINGLE implementation consumed by both the
synthetic tests and the eventual real-data runner.

The mapping operates on the count CDF:

    F_cal(k) = clip(1 - a * (1 - F(k)), 0, 1)   for k = 0..23

Clipping is an ESSENTIAL part of the contract: without it, F_cal(0)
can go negative when a > 1 and F(0) < 1 - 1/a.

For a < 1 (no clipping active):
    p_cal(0) = 1 - a + a * p(0)   (increased zero-K mass)
    p_cal(k) = a * p(k)            for k >= 1
This is a mixture of the original distribution with additional mass
at zero. It is a directional correction, not a symmetric dispersion
adjustment.

For a > 1 (clipping active at the lower boundary):
    p_cal(0) = 0 (all sub-threshold zero-K mass is removed)
    The remaining survival probabilities are rescaled.

The fitted parameter a is FROZEN before any evaluation-set outcome is
accessed. The evaluation outcomes are loaded by a guarded loader that
refuses to return data before the calibration parameter has been
persisted.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

K_MAX = 24
CONTROL_A_BOUNDS = (0.5, 2.0)
FIT_TOLERANCE = 1e-6


def linear_cdf_calibrate(pmf: np.ndarray, a: float) -> np.ndarray:
    """Apply the clipped linear CDF recalibration.

    This is the SINGLE implementation consumed by tests and runners.
    The clip is essential: without it, F_cal(0) can be negative when
    a > 1 and F(0) < 1 - 1/a.
    """
    pmf = np.asarray(pmf, dtype=np.float64)
    if pmf.shape != (K_MAX,):
        raise ValueError(f"expected {K_MAX}-bucket PMF, got {pmf.shape}")
    if not np.all(np.isfinite(pmf)):
        raise ValueError("input PMF contains nonfinite values")
    if np.any(pmf < 0) or abs(pmf.sum() - 1.0) > 1e-9:
        raise ValueError("input PMF must be nonnegative and normalized")
    if not np.isfinite(a) or a < 0:
        raise ValueError(f"calibration parameter a must be finite and "
                         f"nonnegative, got {a}")
    F = np.cumsum(pmf)
    F = np.clip(F, 0.0, 1.0)  # input CDF must also be in [0, 1]
    F_cal = np.clip(1.0 - a * (1.0 - F), 0.0, 1.0)
    p_cal = np.zeros(K_MAX)
    p_cal[0] = F_cal[0]  # F_cal(-1) = 0
    p_cal[1:] = np.diff(F_cal)
    # enforce exact normalization (clip may introduce negligible drift)
    total = p_cal.sum()
    if total <= 0:
        raise ValueError("calibrated PMF has zero total mass")
    p_cal = p_cal / total
    return p_cal


def _count_rps(pmf: np.ndarray, k_real: int) -> float:
    """Registered count-RPS (inline to avoid import cycle at module
    level; the real runner imports from kcount_combiner directly)."""
    import kcount_combiner as kc
    return float(kc.count_rps(pmf, k_real))


def fit_calibration_a(pmf_list: list[np.ndarray],
                      realized_list: list[int],
                      ) -> float:
    """Fit the calibration parameter a by minimizing mean count-RPS on
    the calibration window. Deterministic; uses bounded scalar search.

    The caller must pass ONLY calibration-window PMFs and outcomes.
    This function does not access evaluation outcomes.
    """
    from scipy.optimize import minimize_scalar

    if len(pmf_list) < 100:
        raise ValueError(
            f"calibration sample too small: {len(pmf_list)} < 100")

    def objective(a: float) -> float:
        total = 0.0
        for pmf, k in zip(pmf_list, realized_list):
            cal = linear_cdf_calibrate(np.asarray(pmf), a)
            total += _count_rps(cal, k)
        return total / len(pmf_list)

    result = minimize_scalar(
        objective,
        bounds=CONTROL_A_BOUNDS,
        method="bounded",
        options={"xatol": FIT_TOLERANCE},
    )
    a = float(result.x)
    if a < CONTROL_A_BOUNDS[0] or a > CONTROL_A_BOUNDS[1]:
        raise ValueError(
            f"fitted a={a} outside {CONTROL_A_BOUNDS}: stop")
    return a


class GuardedEvaluationLoader:
    """Refuses to return evaluation outcomes until the fitted parameter
    has been persisted. This enforces the evaluation-outcome isolation
    contract at the code level."""

    def __init__(self):
        self._fitted_a = None
        self._frozen = False

    def freeze(self, a: float):
        if self._frozen:
            raise ValueError("already frozen")
        self._fitted_a = a
        self._frozen = True

    def load(self, evaluation_pmfs, evaluation_outcomes):
        if not self._frozen:
            raise RuntimeError(
                "EVALUATION_OUTCOME_ISOLATION: the calibration "
                "parameter must be frozen (via freeze()) before "
                "evaluation outcomes can be loaded")
        return evaluation_pmfs, evaluation_outcomes

    @property
    def fitted_a(self):
        return self._fitted_a

    @property
    def is_frozen(self):
        return self._frozen
