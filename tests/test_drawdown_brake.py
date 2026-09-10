"""Tests for the drawdown brake state machine (pure logic, no parquet)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

OPS = Path(__file__).resolve().parents[1] / "production" / "ops"
_spec = importlib.util.spec_from_file_location(
    "check_drawdown_brake", OPS / "check_drawdown_brake.py")
assert _spec is not None and _spec.loader is not None
brake = importlib.util.module_from_spec(_spec)
sys.modules["check_drawdown_brake"] = brake
_spec.loader.exec_module(brake)


def test_green_below_caution() -> None:
    assert brake.brake_state(0.0, "GREEN") == ("GREEN", 1.0)
    assert brake.brake_state(7.99, "GREEN") == ("GREEN", 1.0)


def test_caution_band_and_hysteresis() -> None:
    assert brake.brake_state(8.0, "GREEN") == ("CAUTION", 0.5)
    # Stays CAUTION until back at/below 5 (no flicker at the boundary).
    assert brake.brake_state(7.0, "CAUTION") == ("CAUTION", 0.5)
    assert brake.brake_state(5.1, "CAUTION") == ("CAUTION", 0.5)
    assert brake.brake_state(4.9, "CAUTION") == ("GREEN", 1.0)


def test_halt_and_release() -> None:
    assert brake.brake_state(15.0, "GREEN") == ("HALT", 0.0)
    assert brake.brake_state(24.4, "CAUTION") == ("HALT", 0.0)
    # HALT holds until 10, then steps down (never straight to GREEN).
    assert brake.brake_state(12.0, "HALT") == ("HALT", 0.0)
    assert brake.brake_state(10.0, "HALT") == ("CAUTION", 0.5)
    assert brake.brake_state(4.0, "HALT") == ("GREEN", 1.0)
