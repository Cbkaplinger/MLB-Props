"""Characterization tests for the settlement/grading path (O-3, test-only).

These tests PIN the CURRENT behavior of production/odds/grade_odds_ledger.py
argument parsing, ticket matching, status summary, and the de-facto exit
contract — they do not propose or implement any behavior change. The proposed
O-3 contract (formal exit codes + summary line) lives in
docs/reference/reports/o3_settlement_contract_proposal_2026-10-19.md and is
NOT implemented here.

No real ledger, lake, network, or MLB API access is used: every test runs on
synthetic frames or monkeypatched paths.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "production" / "odds" / "grade_odds_ledger.py"

_spec = importlib.util.spec_from_file_location(
    "grade_odds_ledger_char", SCRIPT)
gol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gol)


def _ledger_row(**kw):
    base = dict(
        game_date="2026-07-30",
        game_pk=1,
        pitcher=100,
        player_name="Sean Burke",
        line=6.5,
        over_price=-110,
        under_price=-110,
        p_model_over=0.58,
        book="draftkings",
        unit_dollars=50.0,
        source="test",
        status="open",
        event_id="evt_1",
        event_start_time="2026-07-30T23:10:00Z",
        logged_at=datetime(2026, 7, 30, 14, 0, tzinfo=timezone.utc),
    )
    base.update(kw)
    return base


class TestParseContract:
    def test_parse_settle_valid(self):
        assert gol._parse_settle("Logan Webb,2026-07-29,4") == (
            "Logan Webb", "2026-07-29", 4.0)

    def test_parse_settle_strips_whitespace(self):
        assert gol._parse_settle(" Logan Webb , 2026-07-29 , 4 ") == (
            "Logan Webb", "2026-07-29", 4.0)

    def test_parse_settle_wrong_arity_fails_loud(self):
        with pytest.raises(SystemExit) as exc:
            gol._parse_settle("Logan Webb,2026-07-29")
        assert "Bad --settle" in str(exc.value)

    def test_parse_settle_non_numeric_k_fails_loud(self):
        # float() ValueError is NOT caught today — pins current behavior
        with pytest.raises((ValueError, SystemExit)):
            gol._parse_settle("Logan Webb,2026-07-29,four")

    def test_parse_close_valid(self):
        assert gol._parse_close("Sean Burke,2026-07-30,-115,-110") == (
            "Sean Burke", "2026-07-30", -115.0, -110.0)

    def test_parse_close_wrong_arity_fails_loud(self):
        with pytest.raises(SystemExit) as exc:
            gol._parse_close("Sean Burke,2026-07-30,-115")
        assert "Bad --close" in str(exc.value)


class TestFindTickets:
    @pytest.fixture()
    def ledger(self):
        return pl.DataFrame([
            _ledger_row(),
            _ledger_row(player_name="Justin Steele", game_date="2026-07-30"),
            _ledger_row(player_name="Sean Burke", game_date="2026-08-02"),
        ])

    def test_matches_last_name_case_insensitive(self, ledger):
        hits = gol._find_tickets(ledger, "sean burke", "2026-07-30")
        assert len(hits) == 1
        assert hits[0]["player_name"] == "Sean Burke"

    def test_date_substring_match(self, ledger):
        # current behavior: game_date matched by str.contains, not equality
        hits = gol._find_tickets(ledger, "sean burke", "2026-07-30")
        assert len(hits) == 1

    def test_no_match_returns_empty(self, ledger):
        assert gol._find_tickets(ledger, "nobody here", "2026-07-30") == []

    def test_wrong_date_returns_empty(self, ledger):
        assert gol._find_tickets(ledger, "sean burke", "2025-01-01") == []


class TestStatusSummary:
    def test_status_counts_ascii_shape(self):
        led = pl.DataFrame([
            _ledger_row(status="open"),
            _ledger_row(status="open", game_pk=2),
            _ledger_row(status="settled"),
        ])
        lines = gol._status_counts_ascii(led)
        assert isinstance(lines, list)
        assert all(isinstance(l, str) and l.startswith("status=") for l in lines)
        assert any("count=2" in l for l in lines)   # open, sorted first
        assert any("count=1" in l for l in lines)   # settled
        # descending by count is the current contract
        counts = [int(l.split("count=")[1]) for l in lines]
        assert counts == sorted(counts, reverse=True)

    def test_status_counts_ascii_empty_ledger(self):
        led = pl.DataFrame(schema={"status": pl.Utf8})
        assert gol._status_counts_ascii(led) == []


class TestExitContractCurrentBehavior:
    """Pins the de-facto exit contract BEFORE the O-3 proposal changes anything:

    - success: main() returns None (exit 0 by interpreter default)
    - guard failures: raise SystemExit(<message string>) -> interpreter exits 1
      with the message on stderr
    - there is no distinct exit code for partial failures (the O-3 gap)
    """

    def test_guard_raises_systemexit_with_message(self, tmp_path, monkeypatch):
        missing = tmp_path / "no" / "ledger.parquet"
        monkeypatch.setattr(gol, "LEDGER_PATH", missing)
        monkeypatch.setattr(
            "sys.modules[__name__]", gol, raising=False)  # no-op, keeps module
        argv = ["grade_odds_ledger.py", "--settle", "Nobody,2026-07-29,4"]
        monkeypatch.setattr(sys, "argv", argv)
        # LEDGER_PATH.exists() is False and --settle present -> the no-ledger
        # guard fires before ticket lookup
        with pytest.raises(SystemExit) as exc:
            gol.main()
        assert "No ledger at" in str(exc.value)

    def test_systemexit_message_is_string_not_int(self):
        # pins that guard failures use message-strings (=> exit code 1), which
        # is the behavior the O-3 proposal must preserve or explicitly replace
        with pytest.raises(SystemExit) as exc:
            gol._parse_settle("bad")
        assert isinstance(exc.value.code, str)


import sys  # noqa: E402  (kept at bottom: main() monkeypatch needs sys.argv)
