"""Tests for tip-window close selection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Python.odds_close import select_due_tickets


def _row(name: str, tip: datetime | None, **extra):
    r = {
        "ticket_id": name,
        "player_name": name,
        "game_date": "2026-07-30",
        "book": "draftkings",
        "line": 5.5,
        "event_start_time_utc": tip.isoformat() if tip else None,
    }
    r.update(extra)
    return r


def test_select_due_within_window() -> None:
    now = datetime(2026, 7, 30, 18, 0, tzinfo=timezone.utc)
    due, waiting, any_due = select_due_tickets(
        [
            _row("soon", now + timedelta(minutes=10)),
            _row("later", now + timedelta(minutes=90)),
            _row("past", now - timedelta(minutes=20)),
        ],
        as_of=now,
        minutes_before=15,
        minutes_after=5,
    )
    names = {r["player_name"] for r in due}
    assert names == {"soon"}
    assert any_due is True
    assert len(waiting) == 2


def test_missing_tip_included_when_peer_due() -> None:
    now = datetime(2026, 7, 30, 18, 0, tzinfo=timezone.utc)
    due, waiting, _ = select_due_tickets(
        [
            _row("soon", now + timedelta(minutes=5)),
            _row("orphan", None),
        ],
        as_of=now,
        minutes_before=15,
        minutes_after=5,
        include_missing_tip=True,
    )
    names = {r["player_name"] for r in due}
    assert names == {"soon", "orphan"}
    assert waiting == []


def test_just_after_tip_still_due() -> None:
    now = datetime(2026, 7, 30, 18, 0, tzinfo=timezone.utc)
    due, _, _ = select_due_tickets(
        [_row("live", now - timedelta(minutes=3))],
        as_of=now,
        minutes_before=15,
        minutes_after=5,
    )
    assert len(due) == 1


def test_next_future_tip_ignores_past() -> None:
    from Python.odds_close import next_future_tip_minutes

    waiting = [
        {"_minutes_to_tip": -40.0, "player_name": "Past"},
        {"_minutes_to_tip": 90.0, "player_name": "Later"},
        {"_minutes_to_tip": 25.0, "player_name": "Soon"},
    ]
    nxt = next_future_tip_minutes(waiting)
    assert nxt == (25.0, "Soon")
