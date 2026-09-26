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


def test_flip_stake_upgrades_open_zero_only() -> None:
    base = {"game_date": "2026-09-23", "player_name": "Test Arm", "line": 5.5,
            "side": "under", "book": "fanduel", "edge": 0.18,
            "bet_price": -110.0, "over_price": -110.0, "under_price": -110.0,
            "event_start_time_utc": None, "clv_pp": None, "close_status": None,
            "close_over": None, "close_under": None, "closed_at_utc": None,
            "minutes_to_tip_at_close": None, "note": None, "units": 0.0,
            "unit_dollars": 50.0}
    rows = [
        {"ticket_id": "zero", "status": "open", "stake": 0.0, **base},
        {"ticket_id": "staked", "status": "open", "stake": 50.0, **base},
        {"ticket_id": "settled", "status": "settled", "stake": 0.0, **base},
        {"ticket_id": "other", "status": "open", "stake": 0.0,
         **{**base, "line": 6.5}},
    ]
    import polars as pl

    df = pl.DataFrame(rows)
    out, n = led.apply_flip_stake(
        df, game_date="2026-09-23", player_name="Test Arm", line=5.5,
        side="under", stake=50.0)
    assert n == 1
    got = dict(zip(out["ticket_id"].to_list(), out["stake"].to_list()))
    assert got == {"zero": 50.0, "staked": 50.0, "settled": 0.0, "other": 0.0}
    note = out.filter(pl.col("ticket_id") == "zero")["note"][0]
    assert "flip_upgrade" in str(note)
    assert out.filter(pl.col("ticket_id") == "zero")["units"][0] == 1.0
    # Zero/negative board stake never touches anything.
    out2, n2 = led.apply_flip_stake(
        df, game_date="2026-09-23", player_name="Test Arm", line=5.5,
        side="under", stake=0.0)
    assert n2 == 0


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


def test_append_second_line_same_family_links_zero(tmp_path) -> None:
    # Glasnow 2026-09-24: U7.5 FD 08:00 staked, U6.5 DK 11:00 must NOT become
    # a second $50 slip — it appends as $0 telemetry, tagged.
    import polars as pl

    path = tmp_path / "ledger.parquet"
    r1 = _row("u75", "fanduel", 0.15)
    r1["stake"] = 50.0
    led.append_open_rows([r1], path=path)
    r2 = _row("u65", "draftkings", 0.20)
    r2["stake"] = 50.0
    r2["line"] = 6.5
    frame, n_app, _ = led.append_open_rows([r2], path=path)
    assert n_app == 1 and frame.height == 2
    got = dict(zip(frame["ticket_id"].to_list(), frame["stake"].to_list()))
    assert got == {"u75": 50.0, "u65": 0.0}
    note = frame.filter(pl.col("ticket_id") == "u65")["note"][0]
    assert "signal_family_linked" in str(note)


def test_dedupe_keeps_earliest_line_per_family() -> None:
    # Grading: earliest line when it pops up, even if the later line has the
    # better edge (explicit logged_at clocks — no build-order luck).
    import polars as pl
    from datetime import datetime, timezone

    def _t(ticket_id, line, edge, logged):
        r = _row(ticket_id, "draftkings", edge)
        r["line"] = line
        r["stake"] = 50.0
        r["status"] = "settled"
        r["logged_at_utc"] = logged
        return r

    early = "2026-09-24T12:00:00+00:00"
    late = "2026-09-24T15:00:00+00:00"
    df = pl.DataFrame([
        _t("late-better", 6.5, 0.25, late),
        _t("early-worse", 7.5, 0.10, early),
    ])
    one = led.dedupe_ledger_props(df)
    assert one.height == 1
    assert one["ticket_id"][0] == "early-worse"
