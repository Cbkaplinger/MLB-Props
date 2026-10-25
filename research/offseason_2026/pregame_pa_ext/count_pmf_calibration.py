"""Count-PMF calibration: one-parameter linear CDF recalibration.

RESEARCH-ONLY. The SINGLE implementation consumed by both the
synthetic tests and the eventual real-data runner. Implements the
pre-registered calibration method from
card_count_pmf_calibration_2026-10-24.md.

The mapping operates on the count CDF:

    F_cal(k) = clip(1 - a * (1 - F(k)), 0, 1)   for k = 0..23

The clip is an ESSENTIAL part of the contract: without it, F_cal(0)
can go negative when a > 1 and F(0) < 1 - 1/a.

Directional behavior:
- For a < 1 (clip typically inactive): p_cal(0) = 1 - a + a*p(0)
  (increased zero-K mass); p_cal(k) = a * p(k) for k >= 1. This is a
  mixture of the original distribution with additional mass at zero.
- For a > 1: the transformed zero-count CDF may be clipped to zero,
  which removes sub-threshold zero-K mass. However, this occurs only
  when a * (1 - F(0)) > 1, i.e. when F(0) < 1 - 1/a. If p(0) = 0.8
  and a = 1.1, F_cal(0) = 1 - 1.1*(1-0.8) = 0.78 (positive, no clip).
  The mapping is a directional correction, not a symmetric dispersion
  adjustment.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

K_MAX = 24
CONTROL_A_BOUNDS = (0.5, 2.0)
FIT_TOLERANCE = 1e-6
IDENTITY_A = 1.0
IDENTITY_TIE_TOLERANCE = 1e-10


def linear_cdf_calibrate(pmf: np.ndarray, a: float) -> np.ndarray:
    """Apply the clipped linear CDF recalibration.

    The clip is essential: without it, F_cal(0) can be negative when
    a > 1 and F(0) < 1 - 1/a. For example, p(0) = 0.01 and a = 2
    gives F_cal(0) = 1 - 2*(1 - 0.01) = -0.98 without the clip.

    Note: a > 1 does NOT always imply p_cal(0) = 0. If p(0) = 0.8
    and a = 1.1, F_cal(0) = 1 - 1.1*(0.2) = 0.78 (positive, no clip).
    The clip fires only when a * (1 - F(0)) > 1.
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
    F = np.clip(F, 0.0, 1.0)
    F_cal = np.clip(1.0 - a * (1.0 - F), 0.0, 1.0)
    p_cal = np.zeros(K_MAX)
    p_cal[0] = F_cal[0]  # F_cal(-1) = 0
    p_cal[1:] = np.diff(F_cal)
    total = p_cal.sum()
    if total <= 0:
        raise ValueError("calibrated PMF has zero total mass")
    p_cal = p_cal / total
    return p_cal


def _count_rps(pmf: np.ndarray, k_real: int) -> float:
    """Registered count-RPS."""
    import kcount_combiner as kc
    return float(kc.count_rps(pmf, k_real))


def fit_calibration_a(pmf_list: list[np.ndarray],
                      realized_list: list[int],
                      ) -> float:
    """Fit the calibration parameter a by minimizing mean count-RPS on
    the calibration window.

    Preconditions enforced:
    - pmf_list and realized_list must have the same length.
    - realized_list values must be nonnegative integers.
    - calibration sample must have at least 100 starts.
    - the optimizer must succeed.

    Returns the fitted a (scalar). Implements the identity tie-break:
    if two values of a produce mean count-RPS within
    IDENTITY_TIE_TOLERANCE, the one closer to identity (a=1) is
    selected.

    The caller must pass ONLY calibration-window PMFs and outcomes.
    This function does not access evaluation outcomes.
    """
    from scipy.optimize import minimize_scalar

    if len(pmf_list) != len(realized_list):
        raise ValueError(
            f"pmf_list length ({len(pmf_list)}) != realized_list length "
            f"({len(realized_list)})")
    if len(pmf_list) < 100:
        raise ValueError(
            f"calibration sample too small: {len(pmf_list)} < 100")
    for i, k in enumerate(realized_list):
        if not isinstance(k, (int, np.integer)) or k < 0:
            raise ValueError(
                f"realized_list[{i}] = {k}: must be a nonnegative "
                f"integer")

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
    if not result.success:
        raise ValueError(
            f"calibration optimizer failed: {result.message}")
    a = float(result.x)
    if a < CONTROL_A_BOUNDS[0] or a > CONTROL_A_BOUNDS[1]:
        raise ValueError(
            f"fitted a={a} outside {CONTROL_A_BOUNDS}: stop")

    # identity tie-break: check whether a value closer to identity
    # achieves RPS within IDENTITY_TIE_TOLERANCE
    rps_at_a = objective(a)
    rps_at_identity = objective(IDENTITY_A)
    if abs(rps_at_a - rps_at_identity) <= IDENTITY_TIE_TOLERANCE:
        a = IDENTITY_A
    return a


class GuardedEvaluationLoader:
    """Persists the fitted calibration parameter to disk and refuses
    to return evaluation outcomes until that artifact exists and
    contains a valid parameter.

    This enforces the evaluation-outcome isolation contract at the
    code level: a runner cannot accidentally skip the freeze step
    because the loader checks for the persisted artifact, not just
    an in-memory flag."""

    def __init__(self, artifact_dir: Path):
        self._artifact_dir = Path(artifact_dir)
        self._param_path = self._artifact_dir / "fitted_a.json"
        self._artifact_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_frozen(self) -> bool:
        """True iff the parameter artifact exists on disk with a valid
        value."""
        if not self._param_path.exists():
            return False
        try:
            data = json.loads(self._param_path.read_text(encoding="utf-8"))
            a = float(data["fitted_a"])
            return CONTROL_A_BOUNDS[0] <= a <= CONTROL_A_BOUNDS[1]
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return False

    def freeze(self, a: float) -> Path:
        """Persist the fitted parameter to disk (write-once)."""
        if self._param_path.exists():
            raise ValueError(
                f"parameter artifact already exists: {self._param_path}")
        a = float(a)
        if a < CONTROL_A_BOUNDS[0] or a > CONTROL_A_BOUNDS[1]:
            raise ValueError(
                f"fitted a={a} outside {CONTROL_A_BOUNDS}: refusing to "
                f"persist")
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        self._param_path.write_text(
            json.dumps({"fitted_a": a}, indent=1), encoding="utf-8")
        return self._param_path

    def load(self, evaluation_pmfs, evaluation_outcomes):
        """Gate for evaluation data access. Accepts prebuilt data
        structures and returns them only after the parameter artifact
        exists on disk with a valid value. The runner is responsible
        for not using the returned data for any purpose other than
        the registered evaluation."""
        if not self.is_frozen:
            raise RuntimeError(
                "EVALUATION_OUTCOME_ISOLATION: the fitted calibration "
                "parameter artifact must exist on disk (via freeze()) "
                "and be valid before evaluation outcomes can be loaded. "
                f"Expected artifact: {self._param_path}")
        return evaluation_pmfs, evaluation_outcomes
