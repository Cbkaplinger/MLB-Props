"""Tests for the single-slip pick (display-only, never changes BETs)."""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "production" / "ops"))

from send_morning_alert import _slip_pick


def _bets(*edges: float) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"player_name": f"Arm{i}", "best_side": "under", "line": 4.5,
             "best_price": -110.0, "book": "draftkings", "edge": e}
            for i, e in enumerate(edges)
        ]
    )


def test_slip_pick_prefers_in_band_over_monster() -> None:
    # Monster edge (0.30) loses on the replay set; in-band (0.15) wins.
    pick = _slip_pick(_bets(0.30, 0.15, 0.13))
    assert pick is not None
    assert pick["edge"] == 0.15


def test_slip_pick_falls_back_under_cap() -> None:
    # No in-band ticket: fall back to max edge under the 0.24 cap.
    pick = _slip_pick(_bets(0.30, 0.21))
    assert pick is not None
    assert pick["edge"] == 0.21


def test_slip_pick_empty_is_none() -> None:
    assert _slip_pick(pl.DataFrame({"edge": []})) is None
