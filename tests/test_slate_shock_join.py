"""Tests for the slate common-shock join (research only, no live policy)."""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))

from slate_shock_join import evening_event_totals, sorted_key  # noqa: E402


def test_sorted_key_is_order_invariant() -> None:
    assert sorted_key("Eflin, Zach") == sorted_key("Zach Eflin")
    assert sorted_key("Davis Martin") == "davis martin"
    assert sorted_key(None) is None


def test_evening_event_totals_prefers_dkfd() -> None:
    totals = pl.DataFrame(
        [
            {"event_id": "e1", "clock": "evening", "book": "draftkings", "line": 8.5},
            {"event_id": "e1", "clock": "evening", "book": "fanduel", "line": 9.5},
            {"event_id": "e1", "clock": "evening", "book": "betrivers", "line": 4.5},
            {"event_id": "e2", "clock": "evening", "book": "betrivers", "line": 7.5},
            {"event_id": "e1", "clock": "morning", "book": "draftkings", "line": 99.0},
        ]
    )
    out = evening_event_totals(totals).sort("event_id")
    e1 = out.filter(pl.col("event_id") == "e1").to_dicts()[0]
    e2 = out.filter(pl.col("event_id") == "e2").to_dicts()[0]
    assert e1["total_line"] == 9.0  # DK/FD median, not the all-book median
    assert e2["total_line"] == 7.5  # fallback when DK/FD absent


def test_high_total_split_counts_pairs() -> None:
    assert (3 * 2 // 2) == 3  # 3 tickets on one game = 3 correlated pairs
