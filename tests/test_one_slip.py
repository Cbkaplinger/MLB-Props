"""One slip per signal at the best price; CLV on both books (owner 2026-09-23)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

import Python.odds_ledger as led  # noqa: E402


def _row(ticket_id: str, book: str, edge: float, **extra):
    base = {"ticket_id": ticket_id, "game_date": "2026-09-23",
            "player_name": "Test Arm", "line": 5.5, "side": "under",
            "book": book, "edge": edge, "status": "open", "note": None,
            "stake": 50.0, "bet_price": -110.0, "over_price": -110.0,
            "under_price": -110.0, "clv_pp": None, "close_status": None,
            "close_over": None, "close_under": None, "closed_at_utc": None,
            "minutes_to_tip_at_close": None,
            "event_start_time_utc": None}
    base.update(extra)
    return base


def test_collapse_keeps_best_edge_and_tags() -> None:
    kept, n = led.collapse_signal_dupes([
        _row("a", "draftkings", 0.10),
        _row("b", "fanduel", 0.18),
        _row("c", "draftkings", 0.12, line=6.5),  # different line = signal
    ])
    assert n == 1
    assert [r["ticket_id"] for r in kept] == ["b", "c"]
    assert "signal_dupe_dropped=draftkings" in str(kept[0]["note"])


def test_append_second_book_same_signal_skips(tmp_path) -> None:
    path = tmp_path / "ledger.parquet"
    frame, n_app, _ = led.append_open_rows(
        [_row("fd", "fanduel", 0.18)], path=path)
    assert n_app == 1
    frame, n_app, n_skip = led.append_open_rows(
        [_row("dk", "draftkings", 0.10)], path=path)
    assert (n_app, n_skip) == (0, 1)
    assert frame.height == 1
    assert frame["ticket_id"][0] == "fd"


def test_xbook_close_fills_both_clvs(monkeypatch) -> None:
    import Python.odds_close as oc
    from Python.sharp_odds import StrikeoutQuote

    df = pl.DataFrame([_row("t1", "fanduel", 0.18,
                            event_start_time_utc="2026-09-23T23:00:00+00:00")])
    store = {"df": df}
    monkeypatch.setattr(oc, "load_ledger", lambda: store["df"])
    monkeypatch.setattr(oc, "save_ledger", lambda d: store.update(df=d))
    quotes = [
        StrikeoutQuote(player_name="Test Arm", line=5.5, over_american=-110,
                       under_american=-110, sportsbook="fanduel",
                       home_team="A", away_team="B", event_id="e1",
                       event_start_time=None, is_main_line=True),
        StrikeoutQuote(player_name="Test Arm", line=5.5, over_american=-115,
                       under_american=-105, sportsbook="draftkings",
                       home_team="A", away_team="B", event_id="e1",
                       event_start_time=None, is_main_line=True),
    ]
    out = oc.fill_closes(slate="2026-09-23", quotes=quotes)
    assert out["n_upd"] == 1 and out["n_xbook"] == 1
    got = store["df"].to_dicts()[0]
    assert got["close_status"] == "ok"
    assert got["clv_pp"] is not None and got["clv_pp_xbook"] is not None


def _load_grading():
    spec = importlib.util.spec_from_file_location(
        "send_daily_grading",
        ROOT / "production" / "ops" / "send_daily_grading.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["send_daily_grading"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_summarize_reports_xbook() -> None:
    g = _load_grading()
    frame = pl.DataFrame([
        {"stake": 50.0, "pnl": 45.0, "edge": 0.15, "result": "win",
         "clv_pp": 0.02, "clv_pp_xbook": 0.01, "clv_paid_close_pp": None},
        {"stake": 50.0, "pnl": -50.0, "edge": 0.13, "result": "loss",
         "clv_pp": -0.01, "clv_pp_xbook": -0.03, "clv_paid_close_pp": None},
    ])
    s = g.summarize(frame)
    assert s["n_xbook"] == 2
    assert s["xbook_beat"] == 0.5
    assert s["n"] == 2 and s["beat_rate"] == 0.5
