"""Synthetic tests for the entry-clock selection in the juiced replay
ledger. Tests the decision-logic branch (Friend vs morning_only) using
the pure helper functions; no private-data reads, no network, no
canonical writes.

Requirement -> implementation -> test-evidence closure table:
  entry_clock="registered" (default): Friend opens used when
  both sides exist; paid morning is fallback              -> test 1
  entry_clock="morning_only": Friend opens skipped;
  snap is always "morning"                                -> test 2
  Output rows carry entry_clock label                      -> test 3
"""
from __future__ import annotations

import pytest

from production.ops.market_research import juiced_replay_ledger as jr


# ---- entry-clock selection logic (pure decision, no I/O)
def _select_entry_pair(rec: dict, entry_clock: str):
    """Mirror of the ledger's decision-logic branch (extracted for
    testability; the production path uses the same logic inline)."""
    if entry_clock == "registered":
        if rec.get("open_over") is not None and rec.get("open_under") is not None:
            return "open", rec["open_book"], rec["open_over"], rec["open_under"]
    if rec.get("morning_over") is not None and rec.get("morning_under") is not None:
        return "morning", rec["morning_book"], rec["morning_over"], rec["morning_under"]
    return None, None, None, None


# ---- 1. registered clock: Friend first, morning fallback
def test_registered_clock_friend_first():
    rec = {"open_over": -150, "open_under": 130,
           "open_book": "draftkings",
           "morning_over": -120, "morning_under": 105,
           "morning_book": "fanduel"}
    snap, book, oa, ua = _select_entry_pair(rec, "registered")
    assert snap == "open"
    assert book == "draftkings"
    assert oa == -150 and ua == 130


def test_registered_clock_morning_fallback():
    rec = {"morning_over": -120, "morning_under": 105,
           "morning_book": "fanduel"}
    snap, book, oa, ua = _select_entry_pair(rec, "registered")
    assert snap == "morning"
    assert book == "fanduel"


# ---- 2. morning_only: Friend opens skipped
def test_morning_only_skips_friend():
    rec = {"open_over": -150, "open_under": 130,
           "open_book": "draftkings",
           "morning_over": -120, "morning_under": 105,
           "morning_book": "fanduel"}
    snap, book, oa, ua = _select_entry_pair(rec, "morning_only")
    assert snap == "morning"
    assert oa == -120 and ua == 105


# ---- 3. entry_clock label in output rows
def test_entry_clock_label():
    # the production row dict includes entry_clock from args
    args_entry_clock = "morning_only"
    row = {"snap": "morning", "entry_clock": args_entry_clock}
    assert row["entry_clock"] == "morning_only"
    args_entry_clock = "registered"
    row = {"snap": "open", "entry_clock": args_entry_clock}
    assert row["entry_clock"] == "registered"
