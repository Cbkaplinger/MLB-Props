"""Synthetic tests for the pregame lineup capture adapter (no live calls)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1] / "research" / "offseason_2026"
sys.path.insert(0, str(HERE))

import pregame_lineup_capture as pc  # noqa: E402

CUTOFF = datetime(2026, 8, 21, 17, 0, tzinfo=timezone.utc)


def snaps(rows):
    return pl.DataFrame(
        rows,
        schema={"game_pk": pl.Int64, "team": pl.String,
                "batting_order": pl.Int64, "batter": pl.Int64,
                "fetched_at": pl.Datetime("us", "UTC"),
                "lineup_status": pl.String},
        orient="row")


def full_lineup(game_pk, team, fetched_at, status="confirmed", shift=0):
    return [(game_pk, team, i + 1, 1000 + i + shift, fetched_at, status)
            for i in range(9)]


def test_cutoff_enforcement_rejects_late_snapshot():
    early = full_lineup(1, "NYY", datetime(2026, 8, 21, 15, 0,
                                           tzinfo=timezone.utc))
    s = snaps(early)
    ok = pc.select_pregame_lineup(s, 1, "NYY", CUTOFF)
    assert ok["ok"] and ok["reason"] == pc.REASON_OK
    late = full_lineup(1, "NYY", datetime(2026, 8, 21, 18, 0,
                                          tzinfo=timezone.utc))
    r = pc.select_pregame_lineup(snaps(late), 1, "NYY", CUTOFF)
    assert not r["ok"] and r["reason"] == pc.REASON_LATE_ONLY


def test_latest_valid_revision_wins_and_revisions_preserved():
    rows = full_lineup(1, "NYY", datetime(2026, 8, 21, 14, 0,
                                          tzinfo=timezone.utc))
    rows += full_lineup(1, "NYY", datetime(2026, 8, 21, 16, 0,
                                           tzinfo=timezone.utc), shift=100)
    r = pc.select_pregame_lineup(snaps(rows), 1, "NYY", CUTOFF)
    assert r["ok"]
    assert r["batters"][0] == 1100  # latest revision's slot 1
    assert r["status"] == "confirmed"


def test_missing_and_partial_reasons():
    r = pc.select_pregame_lineup(snaps([]), 1, "NYY", CUTOFF)
    assert r["reason"] == pc.REASON_MISSING
    partial = [(1, "NYY", i + 1, 1000 + i, CUTOFF, "projected")
               for i in range(7)]
    r2 = pc.select_pregame_lineup(snaps(partial), 1, "NYY", CUTOFF)
    assert r2["reason"] == pc.REASON_NOT_9_SLOTS and not r2["ok"]


def test_duplicate_slots_rejected():
    rows = full_lineup(1, "NYY", CUTOFF)
    rows[8] = (1, "NYY", 9, 1001, CUTOFF, "confirmed")  # duplicate batter
    r = pc.select_pregame_lineup(snaps(rows), 1, "NYY", CUTOFF)
    assert r["reason"] == pc.REASON_NOT_9_SLOTS


def test_opportunity_sequence_cycles_with_repeats():
    lineup = {"ok": True, "batters": list(range(1000, 1009))}
    seq = pc.opportunity_sequence(lineup, 23)
    assert len(seq) == 23
    assert seq[9] == seq[0] and seq[22] == seq[4]
    assert pc.opportunity_sequence({"ok": False, "batters": None}, 9) is None


def test_string_fetched_at_parsed():
    rows = [(1, "NYY", i + 1, 1000 + i, "2026-08-21T15:00:00Z",
             "confirmed") for i in range(9)]
    s = pl.DataFrame(
        rows,
        schema={"game_pk": pl.Int64, "team": pl.String,
                "batting_order": pl.Int64, "batter": pl.Int64,
                "fetched_at": pl.String, "lineup_status": pl.String},
        orient="row")
    r = pc.select_pregame_lineup(s, 1, "NYY", CUTOFF)
    assert r["ok"] and r["fetched_at"] is not None
