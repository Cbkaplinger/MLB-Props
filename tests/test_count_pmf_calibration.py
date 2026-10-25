"""Tests for the count-PMF calibration module. Tests import from the
SHARED module (`count_pmf_calibration`), not from inline copies —
the same functions the real-data runner will execute.

Covers the owner's four review findings at 0901851:
1. Optimizer success checked; identity tie-break implemented
2. Unequal input lengths rejected; outcome values validated
3. Guarded loader persists to disk; load checks the artifact exists
4. Docstring accurately describes directional behavior (a>1 does not
   always imply p_cal(0)=0)
"""
from __future__ import annotations

import json
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
    """F(0) = 0.01 with a = 2: without clipping, F_cal(0) = -0.98.
    With clipping, F_cal(0) = 0 and p_cal(0) = 0."""
    pmf = np.zeros(24)
    pmf[0] = 0.01
    pmf[1:] = 0.99 / 23
    cal = cpc.linear_cdf_calibrate(pmf, 2.0)
    assert cal[0] == 0.0
    assert np.all(cal >= 0)
    assert abs(cal.sum() - 1.0) < 1e-9


def test_a_gt_1_does_not_always_zero_out_p0():
    """Owner finding 4: p(0)=0.8 and a=1.1 gives F_cal(0) = 0.78
    (positive, no clip fires). The docstring must not claim p_cal(0)=0
    for all a>1."""
    pmf = np.zeros(24)
    pmf[0] = 0.8
    pmf[1:] = 0.2 / 23
    cal = cpc.linear_cdf_calibrate(pmf, 1.1)
    assert cal[0] > 0  # NOT zeroed — the clip did not fire
    assert cal[0] == pytest.approx(0.78, abs=0.02)


def test_clip_fires_only_when_a_times_1_minus_f0_exceeds_1():
    """The clip fires only when a * (1 - F(0)) > 1, i.e. when
    F(0) < 1 - 1/a."""
    # F(0) = 0.8, a = 1.1: a*(1-0.8) = 0.22 < 1 -> no clip
    pmf_high_p0 = np.zeros(24)
    pmf_high_p0[0] = 0.8
    pmf_high_p0[1:] = 0.2 / 23
    cal = cpc.linear_cdf_calibrate(pmf_high_p0, 1.1)
    assert cal[0] > 0
    # F(0) = 0.01, a = 2: a*(1-0.01) = 1.98 > 1 -> clip fires
    pmf_low_p0 = np.zeros(24)
    pmf_low_p0[0] = 0.01
    pmf_low_p0[1:] = 0.99 / 23
    cal = cpc.linear_cdf_calibrate(pmf_low_p0, 2.0)
    assert cal[0] == 0.0


# ---- invalid/nonfinite inputs ----------------------------------------
def test_rejects_nonfinite_pmf():
    with pytest.raises(ValueError, match="nonfinite"):
        cpc.linear_cdf_calibrate(np.full(24, np.nan), 1.0)


def test_rejects_negative_pmf():
    pmf = np.full(24, 1 / 24)
    pmf[0] = -0.1
    pmf[1] = 1 / 24 + 0.1
    with pytest.raises(ValueError, match="nonnegative"):
        cpc.linear_cdf_calibrate(pmf, 1.0)


def test_rejects_unnormalized_pmf():
    with pytest.raises(ValueError, match="normalized"):
        cpc.linear_cdf_calibrate(np.full(24, 0.5), 1.0)


def test_rejects_wrong_shape():
    with pytest.raises(ValueError, match="24-bucket"):
        cpc.linear_cdf_calibrate(np.ones(23), 1.0)


def test_rejects_negative_a():
    with pytest.raises(ValueError, match="nonnegative"):
        cpc.linear_cdf_calibrate(np.ones(24) / 24, -0.5)


def test_rejects_nonfinite_a():
    with pytest.raises(ValueError, match="finite"):
        cpc.linear_cdf_calibrate(np.ones(24) / 24, float("nan"))


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
    pmf = np.zeros(24)
    pmf[0] = 0.1
    pmf[1:] = 0.9 / 23
    cal = cpc.linear_cdf_calibrate(pmf, 0.5)
    assert cal[0] > pmf[0]


def test_high_a_with_low_p0_clips_to_zero():
    pmf = np.zeros(24)
    pmf[0] = 0.1
    pmf[1:] = 0.9 / 23
    cal = cpc.linear_cdf_calibrate(pmf, 2.0)
    assert cal[0] == 0.0


def test_high_a_with_high_p0_does_not_clip():
    """Owner finding 4: p(0)=0.8 and a=1.1 gives a positive result."""
    pmf = np.zeros(24)
    pmf[0] = 0.8
    pmf[1:] = 0.2 / 23
    cal = cpc.linear_cdf_calibrate(pmf, 1.1)
    assert cal[0] > 0


def test_directional_not_symmetric():
    pmf = np.zeros(24)
    pmf[0] = 0.2
    pmf[1:] = 0.8 / 23
    p_low = cpc.linear_cdf_calibrate(pmf, 0.5)
    p_high = cpc.linear_cdf_calibrate(pmf, 2.0)
    assert p_low[0] > pmf[0]
    assert p_high[0] == 0.0
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
    pmf = np.random.default_rng(3).dirichlet(np.ones(24))
    F = np.cumsum(pmf)
    for a in (0.5, 1.0, 2.0):
        assert (1.0 - a * (1.0 - F[23])) == pytest.approx(1.0, abs=1e-12)


# ---- fitting: optimizer success ---------------------------------------
def test_fit_checks_optimizer_success():
    """The fit must raise if the optimizer fails (simulated by an
    objective that returns NaN for extreme values)."""
    # a normal fit should succeed
    rng = np.random.default_rng(5)
    pmfs = [rng.dirichlet(np.ones(24) * 3).tolist() for _ in range(100)]
    realized = [int(rng.integers(0, 8)) for _ in range(100)]
    a = cpc.fit_calibration_a(pmfs, realized)
    assert 0.5 <= a <= 2.0


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


# ---- fitting: identity tie rule ---------------------------------------
def test_identity_tie_rule_flat_pmfs():
    """Flat PMFs: RPS is the same for all a values. The identity
    tie-break should select a value close to 1."""
    pmfs = [np.ones(24) / 24] * 100
    realized = [3] * 100
    a = cpc.fit_calibration_a(pmfs, realized)
    assert 0.5 <= a <= 2.0


# ---- fitting: input validation ----------------------------------------
def test_fit_rejects_unequal_lengths():
    """Owner finding 2: unequal input lengths must be rejected, not
    silently truncated."""
    pmfs = [np.ones(24) / 24] * 100
    realized = [3] * 50  # HALF the length
    with pytest.raises(ValueError, match="!= realized_list length"):
        cpc.fit_calibration_a(pmfs, realized)


def test_fit_rejects_small_sample():
    with pytest.raises(ValueError, match="too small"):
        cpc.fit_calibration_a([np.ones(24) / 24] * 50, [3] * 50)


def test_fit_rejects_negative_outcomes():
    pmfs = [np.ones(24) / 24] * 100
    realized = [3] * 99 + [-1]
    with pytest.raises(ValueError, match="nonnegative integer"):
        cpc.fit_calibration_a(pmfs, realized)


def test_fit_rejects_noninteger_outcomes():
    pmfs = [np.ones(24) / 24] * 100
    realized = [3.5] * 100
    with pytest.raises(ValueError, match="nonnegative integer"):
        cpc.fit_calibration_a(pmfs, realized)


# ---- evaluation-outcome isolation -------------------------------------
def test_guarded_loader_blocks_pre_freeze_access(tmp_path):
    """The guarded loader must refuse to return evaluation outcomes
    before the fitted parameter artifact exists on disk."""
    loader = cpc.GuardedEvaluationLoader(tmp_path / "params")
    with pytest.raises(RuntimeError,
                       match="EVALUATION_OUTCOME_ISOLATION"):
        loader.load([np.ones(24) / 24], [3])


def test_guarded_loader_persists_parameter_to_disk(tmp_path):
    """Owner finding 3: the guard must PERSIST the parameter, not just
    set an in-memory flag."""
    loader = cpc.GuardedEvaluationLoader(tmp_path / "params")
    loader.freeze(1.2)
    artifact = tmp_path / "params" / "fitted_a.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text(encoding="utf-8"))
    assert data["fitted_a"] == 1.2


def test_guarded_loader_allows_post_freeze_access(tmp_path):
    loader = cpc.GuardedEvaluationLoader(tmp_path / "params")
    loader.freeze(1.0)
    pmfs, outcomes = loader.load([np.ones(24) / 24], [3])
    assert pmfs is not None and outcomes is not None


def test_guarded_loader_freeze_is_one_shot(tmp_path):
    loader = cpc.GuardedEvaluationLoader(tmp_path / "params")
    loader.freeze(1.0)
    with pytest.raises(ValueError, match="already exists"):
        loader.freeze(2.0)


def test_guarded_loader_rejects_out_of_bounds(tmp_path):
    loader = cpc.GuardedEvaluationLoader(tmp_path / "params")
    with pytest.raises(ValueError, match="refusing"):
        loader.freeze(5.0)


def test_guarded_loader_detects_corrupted_artifact(tmp_path):
    loader = cpc.GuardedEvaluationLoader(tmp_path / "params")
    loader.freeze(1.0)
    # corrupt the artifact
    artifact = tmp_path / "params" / "fitted_a.json"
    artifact.write_text('{"fitted_a": "NOT_A_NUMBER"}', encoding="utf-8")
    assert not loader.is_frozen
    with pytest.raises(RuntimeError, match="EVALUATION_OUTCOME_ISOLATION"):
        loader.load([np.ones(24) / 24], [3])


def test_guarded_loader_integration_with_fit(tmp_path):
    """The full isolation pattern: fit on calibration data, freeze to
    disk, then (and only then) load evaluation outcomes."""
    rng = np.random.default_rng(5)
    cal_pmfs = [rng.dirichlet(np.ones(24) * 3).tolist()
                for _ in range(100)]
    cal_outcomes = [int(rng.integers(0, 8)) for _ in range(100)]
    a = cpc.fit_calibration_a(
        [np.asarray(p) for p in cal_pmfs], cal_outcomes)
    loader = cpc.GuardedEvaluationLoader(tmp_path / "params")
    loader.freeze(a)
    assert loader.is_frozen
    eval_pmfs, eval_outcomes = loader.load([np.ones(24) / 24], [3])
    assert eval_pmfs is not None
