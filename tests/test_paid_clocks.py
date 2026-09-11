"""Tests for --attach-paid-clocks (backend pack #113 step 0)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import polars as pl
import pytest

ODDS = Path(__file__).resolve().parents[1] / "production" / "odds"
_spec = importlib.util.spec_from_file_location(
    "grade_odds_ledger", ODDS / "grade_odds_ledger.py")
assert _spec is not None and _spec.loader is not None
gol = importlib.util.module_from_spec(_spec)
sys.modules["grade_odds_ledger"] = gol
_spec.loader.exec_module(gol)


def _led() -> pl.DataFrame:
    return pl.DataFrame([
        {"ticket_id": "t-over", "game_date": "2026-09-01", "player_name": "Logan Gilbert",
         "line": 6.5, "side": "over", "bet_price": -110.0,
         "over_price": -110.0, "under_price": -110.0, "market": "pitcher_strikeouts",
         "status": "settled", "settle_value": 7.0},
        {"ticket_id": "t-under", "game_date": "2026-09-01", "player_name": "Max Fried",
         "line": 5.5, "side": "under", "bet_price": -110.0,
         "over_price": -110.0, "under_price": -110.0, "market": "pitcher_strikeouts",
         "status": "settled", "settle_value": 4.0},
        {"ticket_id": "t-nomatch", "game_date": "2026-09-01", "player_name": "No Body",
         "line": 9.5, "side": "over", "bet_price": -110.0,
         "over_price": -110.0, "under_price": -110.0, "market": "pitcher_strikeouts",
         "status": "settled", "settle_value": 3.0},
    ])


def _panel(rows) -> pl.DataFrame:
    return pl.DataFrame(rows, schema={"gd": pl.Utf8, "key": pl.Utf8, "line": pl.Float64,
                                      "market": pl.Utf8, "fair": pl.Float64,
                                      "n_books": pl.UInt32})


def _panels():
    m = _panel([
        {"gd": "2026-09-01", "key": "gilbert logan", "line": 6.5,
         "market": "pitcher_strikeouts", "fair": 0.48, "n_books": 3},
        {"gd": "2026-09-01", "key": "fried max", "line": 5.5,
         "market": "pitcher_strikeouts", "fair": 0.55, "n_books": 3},
    ])
    c = _panel([
        {"gd": "2026-09-01", "key": "gilbert logan", "line": 6.5,
         "market": "pitcher_strikeouts", "fair": 0.52, "n_books": 4},
        {"gd": "2026-09-01", "key": "fried max", "line": 5.5,
         "market": "pitcher_strikeouts", "fair": 0.50, "n_books": 4},
    ])
    f = _panel([
        {"gd": "2026-09-01", "key": "gilbert logan", "line": 6.5,
         "market": "pitcher_strikeouts", "fair": 0.46, "n_books": 2},
    ])
    return m, c, f


def test_attach_fills_clv_exact() -> None:
    m, c, f = _panels()
    out, audit = gol.attach_paid_clocks(_led(), m, c, f)
    got = {r["ticket_id"]: r for r in out.to_dicts()}
    # Canonical sign: paid-fair minus devigged-bet-side. Bet pair -110/-110
    # devigs to 0.50 taken either side.
    assert got["t-over"]["paid_morning_over"] == pytest.approx(0.48)
    assert got["t-over"]["clv_paid_morning_pp"] == pytest.approx(-2.0, abs=0.01)
    assert got["t-over"]["clv_paid_close_pp"] == pytest.approx(2.0, abs=0.01)
    assert got["t-over"]["clv_paid_open_pp"] == pytest.approx(-4.0, abs=0.01)
    # under: taken fair 1-0.55=0.45 vs bet 0.50 -> -5.0pp; no friend row
    assert got["t-under"]["clv_paid_morning_pp"] == pytest.approx(-5.0, abs=0.01)
    assert got["t-under"]["paid_open_over"] is None
    assert got["t-under"]["clv_paid_open_pp"] is None
    # no panel match -> all null
    assert got["t-nomatch"]["paid_close_over"] is None
    assert audit["matched"]["morning"] == 2
    assert audit["matched"]["close"] == 2
    assert audit["matched"]["friend"] == 1


def test_attach_never_touches_live_cols_and_idempotent() -> None:
    m, c, f = _panels()
    out1, _ = gol.attach_paid_clocks(_led(), m, c, f)
    assert "close_over" not in out1.columns
    assert "clv_pp" not in out1.columns
    stamp1 = out1.filter(pl.col("ticket_id") == "t-over")["paid_clocks_attached_utc"][0]
    out2, _ = gol.attach_paid_clocks(out1, m, c, f)
    stamp2 = out2.filter(pl.col("ticket_id") == "t-over")["paid_clocks_attached_utc"][0]
    assert stamp1 == stamp2
    # CLV recomputes deterministically: same values across runs
    v1 = out1.filter(pl.col("ticket_id") == "t-over")["clv_paid_morning_pp"][0]
    v2 = out2.filter(pl.col("ticket_id") == "t-over")["clv_paid_morning_pp"][0]
    assert v1 == v2 == pytest.approx(-2.0)
