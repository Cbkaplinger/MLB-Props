"""Regression test for D1 correction (b1-d1-ci95-rmse-scale-v1).

Guards the corrected difference-of-replicates percentile interval for the
DESCRIPTIVE-ONLY ci95_rmse_scale field, demonstrates the executed runner's
bug deterministically, and (when the persisted B1 run artifacts are present
on this machine) re-derives the corrected lower bound -0.9848014609216529
from the stored bootstrap matrix while asserting the registered primary
endpoint values are untouched.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import pytest

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "b1_d1_ci95_correction_v1",
    _HERE / "b1_d1_ci95_correction_v1.py",
)
d1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d1)


def test_corrected_formula_on_synthetic_replicates() -> None:
    """Correct interval = [p2.5(b1)-p97.5(b0), p97.5(b1)-p2.5(b0)] (after sqrt)."""
    rng = np.random.default_rng(20261001)
    b1 = rng.uniform(10.0, 30.0, size=500)
    b0 = rng.uniform(10.0, 30.0, size=500)
    got = d1.ci95_rmse_scale_corrected(b1, b0)
    s1, s0 = np.sqrt(b1), np.sqrt(b0)
    want = [
        float(np.percentile(s1, 2.5)) - float(np.percentile(s0, 97.5)),
        float(np.percentile(s1, 97.5)) - float(np.percentile(s0, 2.5)),
    ]
    assert got == pytest.approx(want, abs=0.0)


def test_buggy_formula_differs_on_synthetic_replicates() -> None:
    """The executed v1 formula (p2.5 - p2.5) is NOT the correct lower endpoint."""
    rng = np.random.default_rng(7)
    b1 = rng.uniform(10.0, 30.0, size=400)
    b0 = rng.uniform(10.0, 30.0, size=400)
    assert d1.ci95_rmse_scale_buggy_v1(b1, b0)[0] != pytest.approx(
        d1.ci95_rmse_scale_corrected(b1, b0)[0], abs=1e-12
    )


def _run_dir() -> Path:
    return Path(os.environ.get("B1_RUN_DIR", str(d1.DEFAULT_RUN_DIR)))


@pytest.mark.integration
def test_real_run_corrected_lower_bound_and_primary_endpoint_untouched() -> None:
    """Deterministic check against the persisted B1 run (skipped if absent)."""
    rd = _run_dir()
    if not (rd / "b1_bootstrap_replicates.npy").is_file():
        pytest.skip("B1 run artifacts not present on this machine")
    report = d1.check_against_run(rd)
    assert report["verdict"] == "PASS"
    assert report["buggy_formula_reproduces_stored"] is True
    assert report["stored_ci95_rmse_scale"][0] == pytest.approx(
        -0.7098076573910497, abs=0.0
    )
    assert report["corrected_ci95_rmse_scale"][0] == pytest.approx(
        -0.9848014609216529, abs=0.0
    )
    assert report["corrected_ci95_rmse_scale"][1] == pytest.approx(
        -0.4527807057818549, abs=0.0
    )
    assert report["primary_endpoint_unaffected"] is True


@pytest.mark.integration
def test_real_run_metrics_json_unchanged() -> None:
    """metrics.json must stay byte-identical to the reconciled identity."""
    rd = _run_dir()
    metrics = rd / "metrics.json"
    if not metrics.is_file():
        pytest.skip("B1 run artifacts not present on this machine")
    with open(metrics, "rb") as fh:
        mj = json.loads(fh.read().decode("utf-8"))
    assert mj["config"]["registration_sha256"] == (
        "e10ee2c4a9a56ece249ba3f2203762a34a6a524c9dff3b432d4afca43756425d"
    )
    assert mj["contrast"]["contrasts"]["C_b1_ridge_vs_b0_empirical"]["delta"] == (
        -0.028178565433309988
    )
    assert mj["contrast"]["contrasts"]["C_b1_ridge_vs_b0_empirical"][
        "p_holm"
    ] == 0.0004997501249375312
    # D1 correction is additive: metrics.json itself is never rewritten.
    assert mj["bootstrap"]["paired_deltas_b1_minus_b0"]["sq_err"][
        "ci95_rmse_scale"
    ] == [-0.7098076573910497, -0.4527807057818549]
