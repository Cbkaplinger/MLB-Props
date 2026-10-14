"""Log5 identity fixtures for the P1 harness v2 (owner ruling 5).

The implementation under test (scripts/fit_models.log5) is the full
league-rate identity:

    q = (p*b/l) / (p*b/l + (1-p)*(1-b)/(1-l))

Identities asserted (tolerance 1e-12):
    p = b = l  ->  q = l
    p = l      ->  q = b
    b = l      ->  q = p
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HARNESS = Path(__file__).resolve().parent
REPO_ROOT = HARNESS.parents[2]
sys.path.insert(0, str(HARNESS / "scripts"))

from fit_models import log5  # noqa: E402

TOL = 1e-12


def test_import_resolves_inside_checkout() -> None:
    """The log5 implementation under test is THIS checkout's file."""
    import fit_models

    mod_path = Path(fit_models.__file__).resolve()
    assert mod_path.is_relative_to(REPO_ROOT), (
        f"imported fit_models from outside the checkout: {mod_path}"
    )
    assert mod_path == HARNESS / "scripts" / "fit_models.py"

P_FIXED = np.array([0.15, 0.2245, 0.31, 0.42, 0.57, 0.68, 0.83])
B_FIXED = np.array([0.18, 0.26, 0.19, 0.35, 0.49, 0.61, 0.72])
L_FIXED = np.array([0.20, 0.2245, 0.24, 0.23, 0.25, 0.21, 0.22])


def test_p_equals_b_equals_l_gives_q_equal_l() -> None:
    for v in [0.05, 0.2245, 0.5, 0.9]:
        q = log5(np.array([v]), np.array([v]), np.array([v]))
        assert q[0] == pytest.approx(v, abs=TOL)


def test_p_equals_l_gives_q_equal_b() -> None:
    q = log5(P_FIXED, B_FIXED, P_FIXED)
    assert np.allclose(q, B_FIXED, atol=TOL, rtol=0)


def test_b_equals_l_gives_q_equal_p() -> None:
    q = log5(P_FIXED, B_FIXED, B_FIXED)
    assert np.allclose(q, P_FIXED, atol=TOL, rtol=0)


def test_asymmetric_case_matches_direct_formula() -> None:
    """Spot-check the asymmetric (p, b, l all distinct) case against the
    literal formula, not the algebraic simplification."""
    p, b, l = 0.35, 0.28, 0.2245
    expected = (p * b / l) / (p * b / l + (1 - p) * (1 - b) / (1 - l))
    q = log5(np.array([p]), np.array([b]), np.array([l]))
    assert q[0] == pytest.approx(expected, abs=TOL)


def test_output_in_open_interval() -> None:
    q = log5(P_FIXED, B_FIXED, L_FIXED)
    assert np.all(q > 0) and np.all(q < 1)


def test_extreme_inputs_do_not_produce_nan() -> None:
    """Clipping guards the 0/0 corner (p=b=l=0 or 1)."""
    q = log5(np.array([0.0]), np.array([0.0]), np.array([0.0]))
    assert np.isfinite(q).all()
    q = log5(np.array([1.0]), np.array([1.0]), np.array([1.0]))
    assert np.isfinite(q).all()
