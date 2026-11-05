"""Unit tests for the cloud close-backfill matcher (pure planning logic)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "backfill_closes_from_cloud",
        ROOT / "production" / "ops" / "backfill_closes_from_cloud.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["backfill_closes_from_cloud"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_mod()
pick_donors = _mod.pick_donors
plan_merges = _mod.plan_merges


def _frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows)


def test_prefers_same_book_donor() -> None:
    cloud = _frame([
        {"game_date": "2026-09-15", "player_name": "Sean Manaea", "line": 6.5,
         "side": "under", "book": "fanduel", "close_over": 112.0,
         "close_under": -142.0, "close_status": "ok_cross_book",
         "closed_at_utc": "2026-09-16T01:00:00+00:00"},
        {"game_date": "2026-09-15", "player_name": "Sean Manaea", "line": 6.5,
         "side": "under", "book": "fanduel", "close_over": 110.0,
         "close_under": -140.0, "close_status": "ok",
         "closed_at_utc": "2026-09-16T00:00:00+00:00"},
    ])
    donors = pick_donors(cloud.to_dicts())
    key = ("2026-09-15", "sean manaea", 6.5, "under", "fanduel")
    assert donors[key]["close_status"] == "ok"
    assert donors[key]["close_over"] == 110.0


def test_skips_filled_and_today_rows() -> None:
    laptop = _frame([
        {"ticket_id": "t1", "game_date": "2026-09-15",
         "player_name": "Sean Manaea", "line": 6.5, "side": "under",
         "book": "fanduel", "clv_pp": None, "close_status": None},
        {"ticket_id": "t2", "game_date": "2026-09-15",
         "player_name": "Filled Gal", "line": 5.5, "side": "under",
         "book": "draftkings", "clv_pp": 0.01, "close_status": "ok"},
        {"ticket_id": "t3", "game_date": "2026-09-16",
         "player_name": "Today Arm", "line": 4.5, "side": "under",
         "book": "draftkings", "clv_pp": None, "close_status": None},
    ])
    cloud = _frame([
        {"game_date": "2026-09-15", "player_name": "Sean Manaea", "line": 6.5,
         "side": "under", "book": "fanduel", "close_over": 112.0,
         "close_under": -142.0, "close_status": "ok",
         "closed_at_utc": "2026-09-16T01:00:00+00:00"},
        {"game_date": "2026-09-16", "player_name": "Today Arm", "line": 4.5,
         "side": "under", "book": "draftkings", "close_over": 100.0,
         "close_under": -120.0, "close_status": "ok",
         "closed_at_utc": "2026-09-16T05:00:00+00:00"},
    ])
    plans = plan_merges(laptop, cloud, "2026-09-16")
    assert [p["ticket_id"] for p in plans] == ["t1"]


def test_no_donor_no_plan() -> None:
    laptop = _frame([
        {"ticket_id": "t9", "game_date": "2026-09-14",
         "player_name": "No Close Guy", "line": 7.5, "side": "over",
         "book": "fanduel", "clv_pp": None, "close_status": None},
    ])
    cloud = _frame([
        {"game_date": "2026-09-14", "player_name": "Someone Else", "line": 7.5,
         "side": "over", "book": "fanduel", "close_over": -110.0,
         "close_under": -110.0, "close_status": "ok",
         "closed_at_utc": "2026-09-15T01:00:00+00:00"},
    ])
    assert plan_merges(laptop, cloud, "2026-09-16") == []
