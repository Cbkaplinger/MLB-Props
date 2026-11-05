"""Unit tests for A/B policy audit bootstrap math."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "ab_policy_audit",
        ROOT / "production" / "ops" / "market_research" / "ab_policy_audit.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ab_policy_audit"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_mod()


def test_boot_roi_ci_empty() -> None:
    q = _mod.boot_roi_ci([], [], n_boot=50)
    assert q["n"] == 0 and q["roi"] is None and q["ci_lo"] is None


def test_boot_roi_ci_contains_point() -> None:
    gd = ["2026-04-01", "2026-04-01", "2026-04-02", "2026-04-02"]
    pnl = [45.0, -50.0, 45.0, -50.0]  # ROI -10/200 = -5%
    q = _mod.boot_roi_ci(gd, pnl, n_boot=200, seed=7)
    assert q["roi"] == round(-10.0 / 200.0, 4)
    assert q["ci_lo"] <= q["roi"] <= q["ci_hi"]
    assert q["slates"] == 2


def test_boot_roi_ci_deterministic() -> None:
    gd = [f"2026-04-{d:02d}" for d in range(1, 11) for _ in (0, 1)]
    pnl = [50.0 if i % 3 else -50.0 for i in range(20)]
    a = _mod.boot_roi_ci(gd, pnl, n_boot=100, seed=3)
    b = _mod.boot_roi_ci(gd, pnl, n_boot=100, seed=3)
    assert a == b


def test_legs_registered() -> None:
    names = [leg[0] for leg in _mod.LEGS]
    assert names == ["status_quo", "cap_only", "lean_only", "dkfd_only", "champion"]
    assert _mod.NO_CAP == 9.0  # encodes "no cap" through the same refuse path
