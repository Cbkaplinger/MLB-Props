"""Unit tests for the daily grading summary math."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "send_daily_grading",
        ROOT / "production" / "ops" / "send_daily_grading.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["send_daily_grading"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_mod()


def _frame() -> pl.DataFrame:
    return pl.DataFrame([
        {"stake": 50.0, "pnl": 45.0, "edge": 0.15, "result": "win", "clv_pp": 0.02},
        {"stake": 50.0, "pnl": -50.0, "edge": 0.13, "result": "loss", "clv_pp": -0.01},
        {"stake": 50.0, "pnl": 60.0, "edge": 0.20, "result": "win", "clv_pp": None},
    ])


def test_summarize_numbers() -> None:
    s = _mod.summarize(_frame())
    assert s["n"] == 3
    assert s["roi"] == round(55.0 / 150.0, 4)
    assert s["wr"] == round(2 / 3, 4)
    assert "xroi" not in s and "gap" not in s  # purged from notifications
    assert s["ev_dollars"] == round(0.15 * 50 + 0.13 * 50 + 0.20 * 50, 2)
    assert s["n_clv"] == 2
    assert s["mean_clv_pp"] == 0.5  # fraction x100 -> pp
    assert s["beat_rate"] == 0.5
    assert s["n_cons"] == 0 and s["cons_clv_pp"] is None


def test_summarize_empty() -> None:
    assert _mod.summarize(_frame().head(0)) == {"n": 0}


def test_formatters() -> None:
    assert _mod.pct(0.1564) == "+15.6%"
    assert _mod.pct(None) == "n/a"
    assert _mod.pp(0.01296) == "+0.01pp"
    assert _mod.pp(None) == "n/a"


def test_consensus_books_universe() -> None:
    assert set(_mod.CONSENSUS_BOOKS) == {
        "draftkings", "fanduel", "betmgm", "bovada", "betonlineag",
        "fanatics", "betrivers", "williamhill_us", "mybookieag"}


def test_consensus_depth() -> None:
    frame = pl.DataFrame([
        {"game_date": "2026-09-15", "player_name": "Sean Manaea", "line": 6.5},
        {"game_date": "2026-09-15", "player_name": "No Cover", "line": 4.5},
    ])
    cache = pl.DataFrame([
        {"gd": "2026-09-15", "key": "manaea sean", "line": 6.5, "n_books": 5},
    ])
    assert _mod.consensus_depth(frame, cache) == 5.0
    assert _mod.consensus_depth(frame.head(0), cache) is None
