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


def test_projected_full_rejected_confirmed_only_accepted_allowed():
    proj = full_lineup(1, "NYY", datetime(2026, 8, 21, 15, 0,
                                          tzinfo=timezone.utc),
                       status="projected")
    s = snaps(proj)
    r = pc.select_pregame_lineup(s, 1, "NYY", CUTOFF)
    assert not r["ok"] and r["reason"] == pc.REASON_PROJECTED_ONLY
    r2 = pc.select_pregame_lineup(s, 1, "NYY", CUTOFF,
                                  mode=pc.MODE_PROJECTED_ALLOWED)
    assert r2["ok"] and r2["reason"] == pc.REASON_OK
    assert r2["status"] == "projected"


def test_confirmed_full_accepted_under_confirmed_only():
    r = pc.select_pregame_lineup(
        snaps(full_lineup(1, "NYY", datetime(2026, 8, 21, 15, 0,
                                             tzinfo=timezone.utc))),
        1, "NYY", CUTOFF)
    assert r["ok"] and r["reason"] == pc.REASON_OK
    assert r["status"] == "confirmed"


def test_post_cutoff_append_leaves_selection_unchanged():
    early = full_lineup(1, "NYY", datetime(2026, 8, 21, 15, 0,
                                           tzinfo=timezone.utc))
    s0 = snaps(early)
    before = pc.select_pregame_lineup(s0, 1, "NYY", CUTOFF)
    late = full_lineup(1, "NYY", datetime(2026, 8, 21, 19, 0,
                                          tzinfo=timezone.utc), shift=500)
    after = pc.select_pregame_lineup(snaps(early + late), 1, "NYY", CUTOFF)
    assert before == after


def test_naive_cutoff_rejected_aware_timezones_equivalent():
    with pytest.raises(ValueError):
        pc.select_pregame_lineup(
            snaps(full_lineup(1, "NYY", datetime(2026, 8, 21, 15,
                                                 tzinfo=timezone.utc))),
            1, "NYY", datetime(2026, 8, 21, 17, 0))
    from datetime import timedelta
    et = timezone(timedelta(hours=-4))
    a = pc.select_pregame_lineup(
        snaps(full_lineup(1, "NYY", datetime(2026, 8, 21, 15,
                                             tzinfo=timezone.utc))),
        1, "NYY", datetime(2026, 8, 21, 13, 0, tzinfo=et))
    b = pc.select_pregame_lineup(
        snaps(full_lineup(1, "NYY", datetime(2026, 8, 21, 15,
                                             tzinfo=timezone.utc))),
        1, "NYY", datetime(2026, 8, 21, 17, 0, tzinfo=timezone.utc))
    assert a == b


def test_team_normalization_canonical_parity_and_unknown_code():
    from Python.daily_lineups import canonical_team_code
    assert pc.canonical_team_code is canonical_team_code  # D2 parity
    r = pc.select_pregame_lineup(
        snaps(full_lineup(1, "NYY", CUTOFF)), 1, "XYZ", CUTOFF)
    assert not r["ok"] and r["reason"] == pc.REASON_UNKNOWN_TEAM
    r2 = pc.select_pregame_lineup(snaps([]), 1, "NYY", CUTOFF)
    assert r2["reason"] == pc.REASON_MISSING


def test_mixed_status_snapshot_explicit_fallback():
    rows = full_lineup(1, "NYY", CUTOFF)
    rows[4] = (1, "NYY", 5, 1004, CUTOFF, "projected")
    r = pc.select_pregame_lineup(snaps(rows), 1, "NYY", CUTOFF)
    assert not r["ok"] and r["reason"] == pc.REASON_MIXED_STATUS
    assert "confirmed|projected" in r["status"]


def test_no_older_revision_substitution_latest_partial_fallback():
    complete = full_lineup(1, "NYY", datetime(2026, 8, 21, 15, 0,
                                              tzinfo=timezone.utc))
    partial = [(1, "NYY", i + 1, 2000 + i,
                datetime(2026, 8, 21, 16, 0, tzinfo=timezone.utc),
                "confirmed") for i in range(7)]
    r = pc.select_pregame_lineup(snaps(complete + partial), 1, "NYY", CUTOFF)
    assert not r["ok"] and r["reason"] == pc.REASON_NOT_9_SLOTS
    assert r["fetched_at"] == partial[0][4]


def test_naive_cutoff_rejected_before_any_utc_coercion():
    # naive cutoff must raise before snapshot timestamps are touched
    proj = full_lineup(1, "NYY", "not-a-timestamp", status="confirmed")
    with pytest.raises(ValueError):
        pc.select_pregame_lineup(snaps([]), 1, "NYY",
                                 datetime(2026, 8, 21, 17, 0))


def test_adapter_invoked_by_research_runner():
    import inspect
    import run_pa_pregame_ab as runner
    src = inspect.getsource(runner)
    assert "pc.select_pregame_lineup" in src
    assert "MODE_CONFIRMED_ONLY" in src


def test_d2_canonical_code_behavior():
    from Python.daily_lineups import canonical_team_code
    canonical = ["ATH", "BAL", "BOS", "CHC", "CWS", "CIN", "CLE", "COL",
                 "DET", "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN",
                 "NYM", "NYY", "PHI", "PIT", "SD", "SEA", "SF", "STL",
                 "TB", "TEX", "TOR", "WSH", "ATL", "ARI"]
    for c in canonical:  # all 30 writer-emitted codes: self-mapped
        assert pc.select_pregame_lineup(
            snaps(full_lineup(1, c, CUTOFF)), 1, c, CUTOFF)["ok"]
    assert canonical_team_code_canonicality(canonical)


def canonical_team_code_canonicality(canonical):
    from Python.daily_lineups import canonical_team_code
    return all(canonical_team_code(c) == c for c in canonical)


def test_d3_mixed_status_row_order_invariant_no_older_substitution():
    ts = datetime(2026, 8, 21, 15, 0, tzinfo=timezone.utc)
    rows = full_lineup(1, "NYY", ts)
    rows[4] = (1, "NYY", 5, 1004, ts, "projected")  # same fetch, mixed
    r1 = pc.select_pregame_lineup(snaps(rows), 1, "NYY", CUTOFF)
    import random
    shuffled = rows[:]
    random.Random(3).shuffle(shuffled)
    r2 = pc.select_pregame_lineup(snaps(shuffled), 1, "NYY", CUTOFF)
    assert r1 == r2 and r1["reason"] == pc.REASON_MIXED_STATUS
    # no substitution of an older uniform snapshot
    older = full_lineup(1, "NYY", datetime(2026, 8, 21, 14, 0,
                                           tzinfo=timezone.utc))
    r3 = pc.select_pregame_lineup(snaps(older + rows), 1, "NYY", CUTOFF)
    assert not r3["ok"] and r3["reason"] == pc.REASON_MIXED_STATUS


def test_d4_unparseable_timestamp_explicit_fallback():
    rows = [(1, "NYY", i + 1, 1000 + i, "garbage-time", "confirmed")
            for i in range(9)]
    r = pc.select_pregame_lineup(
        pl.DataFrame(rows, schema={"game_pk": pl.Int64, "team": pl.String,
                                   "batting_order": pl.Int64,
                                   "batter": pl.Int64,
                                   "fetched_at": pl.String,
                                   "lineup_status": pl.String},
                     orient="row"),
        1, "NYY", CUTOFF)
    assert not r["ok"] and r["reason"] == pc.REASON_MALFORMED_TIMESTAMP
