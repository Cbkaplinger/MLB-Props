"""Tests for post-hoc probability calibration (chrono-safe maps)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from Python.prob_calibration import (
    ProbCalibrationBundle,
    apply_prob_calibration,
    clip_prob,
    expected_calibration_error,
    fit_bundle_from_arrays,
    fit_isotonic,
    fit_platt,
    load_bundle,
    outcome_over,
    save_bundle,
    scoring_metrics,
    transform_line,
)


def test_outcome_over_half_line() -> None:
    y = outcome_over(np.array([4, 5, 6]), 4.5)
    np.testing.assert_array_equal(y, [0.0, 1.0, 1.0])


def test_platt_transform_bounds_and_shape() -> None:
    rng = np.random.default_rng(0)
    # Overconfident raw probs
    p = np.clip(rng.beta(5, 2, size=800), 0.02, 0.98)
    y = (rng.random(800) < (0.5 + 0.3 * (p - 0.5))).astype(float)
    cal = fit_platt(p, y)
    out = cal.transform(p)
    assert out.min() >= 0.0 and out.max() <= 1.0
    assert cal.platt_a is not None


def test_isotonic_is_monotone() -> None:
    rng = np.random.default_rng(1)
    p = np.sort(rng.uniform(0.05, 0.95, size=500))
    # Empirical rate increases with p but shrunk
    y = (rng.random(500) < (0.2 + 0.5 * p)).astype(float)
    cal = fit_isotonic(p, y)
    grid = np.linspace(0.05, 0.95, 40)
    out = cal.transform(grid)
    assert np.all(np.diff(out) >= -1e-9)


def test_identity_fallback_when_empty_map(tmp_path) -> None:
    bundle = ProbCalibrationBundle(
        version="test",
        method="isotonic",
        fit_cutoff="2024-01-01",
        fit_source="unit",
        lines=[],
        min_line_n=200,
        min_global_n=400,
        created_utc="2024-01-01T00:00:00Z",
        line_maps={},
    )
    p = np.array([0.2, 0.5, 0.8])
    out, scope = transform_line(bundle, 4.5, p)
    np.testing.assert_allclose(out, clip_prob(p))
    assert scope == "identity"


def test_bundle_line_and_nearest_fallback() -> None:
    rng = np.random.default_rng(2)
    p = rng.uniform(0.1, 0.9, size=400)
    y = (rng.random(400) < p * 0.8 + 0.1).astype(float)
    cal = fit_isotonic(p, y)
    cal.scope = "line_3.5"
    cal.line = 3.5
    bundle = ProbCalibrationBundle(
        version="t",
        method="isotonic",
        fit_cutoff="2024-06-01",
        fit_source="unit",
        lines=[3.5],
        min_line_n=200,
        min_global_n=400,
        created_utc="x",
        line_maps={"3_5": cal, "global": cal},
    )
    _, scope = transform_line(bundle, 3.5, p[:10])
    assert scope == "line_3.5"
    _, scope2 = transform_line(bundle, 2.5, p[:10])
    assert scope2 == "nearest_3.5"


def test_apply_keeps_raw_writes_cal() -> None:
    rng = np.random.default_rng(3)
    p = rng.uniform(0.2, 0.8, size=300)
    y = (rng.random(300) < 0.45).astype(float)
    bundle = fit_bundle_from_arrays(
        method="platt",
        line_data={4.5: (p, y), 5.5: (p, y)},
        fit_cutoff="2024-07-01",
        fit_source="unit",
        version="unit_platt",
        min_line_n=100,
        min_global_n=100,
    )
    frame = pd.DataFrame(
        {
            "p_over_4_5": p,
            "p_over_5_5": p,
            "expected_K": np.full(300, 5.0),
        }
    )
    out = apply_prob_calibration(frame, bundle, lines=(4.5, 5.5))
    assert "p_over_4_5" in out.columns
    assert "p_over_4_5_cal" in out.columns
    np.testing.assert_allclose(out["p_over_4_5"].to_numpy(), p)
    assert out["calibration_version"].iloc[0] == "unit_platt"
    # Calibrated should differ from raw for overconfident / biased data
    assert not np.allclose(out["p_over_4_5_cal"].to_numpy(), p)


def test_save_load_roundtrip(tmp_path) -> None:
    rng = np.random.default_rng(4)
    p = rng.uniform(0.15, 0.85, size=250)
    y = (rng.random(250) < p).astype(float)
    bundle = fit_bundle_from_arrays(
        method="isotonic",
        line_data={3.5: (p, y)},
        fit_cutoff="2024-08-01",
        fit_source="unit",
        min_line_n=100,
        min_global_n=100,
    )
    path = tmp_path / "cal.joblib"
    save_bundle(bundle, path)
    loaded = load_bundle(path)
    a = bundle.line_maps["3_5"].transform(p[:20])
    b = loaded.line_maps["3_5"].transform(p[:20])
    np.testing.assert_allclose(a, b)


def test_ece_and_scoring_smoke() -> None:
    y = np.array([0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0])
    p = np.array([0.1, 0.9, 0.8, 0.2, 0.7, 0.3, 0.6, 0.55, 0.4, 0.35])
    ece, bins = expected_calibration_error(y, p, n_bins=5)
    assert ece >= 0.0
    assert len(bins) == 5
    m = scoring_metrics(y, p)
    assert m["brier"] is not None
    assert m["n"] == 10.0
