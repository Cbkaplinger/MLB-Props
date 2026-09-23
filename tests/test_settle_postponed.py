"""Settle: postponed (long-unstarted) games void instead of lingering open."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import polars as pl  # noqa: E402


def _load_grading():
    spec = importlib.util.spec_from_file_location(
        "grade_odds_ledger",
        ROOT / "production" / "odds" / "grade_odds_ledger.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["grade_odds_ledger"] = mod
    spec.loader.exec_module(mod)
    return mod


def _ledger(rows: list[dict]):
    import polars as pl

    base = {"status": "open", "note": None, "pnl": None, "result": None}
    return pl.DataFrame([{**base, **r} for r in rows])


def test_postponed_unstarted_voids_after_24h(monkeypatch) -> None:
    g = _load_grading()
    now = datetime.now(timezone.utc)
    df = _ledger([
        {"ticket_id": "ppd", "player_name": "PPD Arm",
         "game_pk": 1, "pitcher": 2,
         "event_start_time_utc": (now - timedelta(hours=30)).isoformat()},
        {"ticket_id": "fresh", "player_name": "Fresh Arm",
         "game_pk": 3, "pitcher": 4,
         "event_start_time_utc": (now - timedelta(hours=2)).isoformat()},
    ])
    monkeypatch.setattr(
        g, "_fetch_pitcher_result",
        lambda _pk, _pid: {"so": None, "game_final": False,
                           "game_started": False, "appeared": False})
    out, stats = g.auto_settle_api(df)
    got = dict(zip(out["ticket_id"].to_list(), out["status"].to_list()))
    assert got["ppd"] == "void"
    assert "postponed_unstarted_24h" in out.filter(
        pl.col("ticket_id") == "ppd")["note"][0]
    assert got["fresh"] == "open"
    assert stats == {"settled": 0, "voided": 1, "skipped": 1}
