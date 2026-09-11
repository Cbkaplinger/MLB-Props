"""Regression: pre-game probable pitchers must never settle (backlog #83).

2026-09-10 incident: settle ran intraday (12:46 backfill) on rows logged at
12:25 for 13:05 games. The MLB feed carries probable pitchers with a
zero-valued pitching skeleton, and _fetch_pitcher_result returned so=0.0,
phantom-settling 4 open tickets pre-game (fake under-wins in paper PnL).
Fix: only return strikeouts once the game has started (Live/Final).
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

ODDS = Path(__file__).resolve().parents[1] / "production" / "odds"
_spec = importlib.util.spec_from_file_location(
    "grade_odds_ledger", ODDS / "grade_odds_ledger.py")
assert _spec is not None and _spec.loader is not None
gol = importlib.util.module_from_spec(_spec)
sys.modules["grade_odds_ledger"] = gol
_spec.loader.exec_module(gol)


class _FakeResp:
    def __init__(self, payload: dict):
        self._buf = io.BytesIO(json.dumps(payload).encode())
    def read(self):
        return self._buf.read()
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _feed(abstract: str, detailed: str, so) -> dict:
    pitching = {} if so == "absent" else {"strikeOuts": so, "inningsPitched": "5.0",
                                          "hits": 4, "baseOnBalls": 1}
    return {"gameData": {"status": {"abstractGameState": abstract,
                                    "detailedState": detailed}},
            "liveData": {"boxscore": {"teams": {
                "away": {"players": {"ID1": {"person": {"id": 111},
                                             "stats": {"pitching": pitching}}}},
                "home": {"players": {}}}}}}


def _patch(monkeypatch, feed: dict):
    monkeypatch.setattr(gol, "urlopen", lambda *a, **k: _FakeResp(feed))


def test_pregame_probable_zero_stays_open(monkeypatch) -> None:
    _patch(monkeypatch, _feed("Preview", "Scheduled", 0))
    res = gol._fetch_pitcher_result(1, 111)
    assert res["so"] is None, f"pre-game skeleton settled: {res}"


def test_live_game_settles_real_line(monkeypatch) -> None:
    _patch(monkeypatch, _feed("Live", "In Progress", 5))
    res = gol._fetch_pitcher_result(1, 111)
    assert res["so"] == 5.0


def test_final_scratch_stays_void_path(monkeypatch) -> None:
    _patch(monkeypatch, _feed("Final", "Final", "absent"))
    res = gol._fetch_pitcher_result(1, 111)
    assert res["so"] is None and res["game_final"] and not res["appeared"]


def test_pregame_postponed_still_voids(monkeypatch) -> None:
    # #88 review: the pre-game gate must not swallow the postponed path —
    # unplayed games void, never linger open.
    _patch(monkeypatch, _feed("Preview", "Postponed", 0))
    res = gol._fetch_pitcher_result(1, 111)
    assert res["so"] is None and res["game_final"] and not res["appeared"]


def test_started_flag_by_state(monkeypatch) -> None:
    for abstract, detailed, so, expected in [
        ("Preview", "Scheduled", 0, False),
        ("Live", "In Progress", 5, True),
        ("Final", "Final", "absent", True),
        ("Preview", "Postponed", 0, False),
    ]:
        _patch(monkeypatch, _feed(abstract, detailed, so))
        res = gol._fetch_pitcher_result(1, 111)
        assert res["game_started"] is expected, (abstract, res)


def test_auto_settle_skips_unstarted_settles_live_voids_absent(monkeypatch, capsys) -> None:
    import polars as pl
    feeds = {
        1: _feed("Preview", "Scheduled", 0),
        2: _feed("Live", "In Progress", 5),
        3: _feed("Final", "Final", "absent"),
    }

    def fake_fetch(game_pk: int, pitcher_id: int):
        assert pitcher_id == 111
        monkeypatch.setattr(gol, "urlopen",
                            lambda *a, **k: _FakeResp(feeds[game_pk]))
        return orig_fetch(game_pk, pitcher_id)

    orig_fetch = gol._fetch_pitcher_result
    monkeypatch.setattr(gol, "_fetch_pitcher_result", fake_fetch)
    led = pl.DataFrame([
        {"ticket_id": "t-pre", "game_pk": 1, "pitcher": 111,
         "player_name": "Pre Gamer", "status": "open"},
        {"ticket_id": "t-live", "game_pk": 2, "pitcher": 111,
         "player_name": "Live Arm", "status": "open", "side": "over",
         "line": 6.5, "over_price": -110.0, "under_price": -110.0,
         "stake": 50.0, "bet_price": -110.0, "unit_dollars": 50.0},
        {"ticket_id": "t-gone", "game_pk": 3, "pitcher": 111,
         "player_name": "Scratched", "status": "open"},
    ]).with_columns(
        pl.lit(None, dtype=pl.Float64).alias("settle_value"),
        pl.lit(None, dtype=pl.Float64).alias("settle_ip"),
        pl.lit(None, dtype=pl.Float64).alias("settle_outs"),
        pl.lit(None, dtype=pl.Float64).alias("settle_hits_allowed"),
        pl.lit(None, dtype=pl.Float64).alias("settle_walks_allowed"),
        pl.lit(None, dtype=pl.Float64).alias("settle_strikeouts"),
        pl.lit(None, dtype=pl.Utf8).alias("result"),
        pl.lit(None, dtype=pl.Float64).alias("pnl"),
        pl.lit(None, dtype=pl.Utf8).alias("note"))
    out, stats = gol.auto_settle_api(led, void_scratches=True)
    assert stats == {"settled": 1, "voided": 1, "skipped": 1}
    got = {r["ticket_id"]: r for r in out.to_dicts()}
    assert got["t-pre"]["status"] == "open"
    assert got["t-live"]["status"] == "settled" and got["t-live"]["settle_value"] == 5.0
    assert got["t-gone"]["status"] == "void"
    assert "unstarted" in capsys.readouterr().out
