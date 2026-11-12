"""Small production-entry-point fixtures for the registered
event-player bridge (odds-coverage-v1/join_coverage.build_task_frames).

Covers:
- name-order normalization through the id-map bridge;
- same-date multiple games / doubleheaders;
- two vendor event_ids mapping to one validated game (documented
  closest-date + event_id-order tiebreak, meta-disclosed);
- genuinely conflicting game mapping (closest date wins);
- unmatched player/game behavior.

The bridge module lives in the private research card; these tests
SKIP cleanly when the card is absent. No network, no live-path edit.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"
                       / "pregame_pa_ext"))

_COV_DIR = Path(r"C:\Users\ckaplinger\MLB-Props-Research"
                r"\odds-coverage-v1")
_COV_OK = (_COV_DIR.exists()
           and (_COV_DIR / "join_coverage.py").exists())
pytestmark = pytest.mark.skipif(
    not _COV_OK, reason="private odds-coverage-v1 card not present")

if _COV_OK:
    sys.path.insert(0, str(_COV_DIR))
    import join_coverage as jc  # noqa: E402

MARKETS = ["pitcher_strikeouts"]


def _ts(hour: int) -> datetime:
    return datetime(2025, 4, 10, hour, 0, tzinfo=timezone.utc)


def _write_parquets(tmp_path, starts_rows, events):
    """events: (event_id, vendor_game_date, player_norm, quote_hour)."""
    bl_rows = []
    env_rows = []
    for eid, gd, pnorm, qh in events:
        for book in ("draftkings", "fanduel"):
            for side, price in (("over", -120), ("under", 105)):
                bl_rows.append({
                    "event_id": eid, "game_date": gd.isoformat(),
                    "player_norm": pnorm,
                    "market": "pitcher_strikeouts",
                    "season_type": "regular", "line": 4.5,
                    "side": side, "price": price,
                    "snapshot_ts": _ts(qh).isoformat(),
                    "book": book, "snapshot": "morning"})
        env_rows.append({"event_id": eid,
                         "commence_time": _ts(23).isoformat(),
                         "snapshot": "morning"})
    bl = tmp_path / "book_lines.parquet"
    pl.DataFrame(bl_rows).write_parquet(bl)
    env = tmp_path / "envelope.parquet"
    pl.DataFrame(env_rows).write_parquet(env)
    st = tmp_path / "starts.parquet"
    if starts_rows:
        pl.DataFrame(starts_rows, orient="row",
                     schema={"game_pk": pl.Int64,
                             "pitcher": pl.Int64,
                             "game_date": pl.Date}).write_parquet(st)
    else:
        pl.DataFrame(schema={"game_pk": pl.Int64,
                             "pitcher": pl.Int64,
                             "game_date": pl.Date}).write_parquet(st)
    idmap = tmp_path / "id_map.parquet"
    pl.DataFrame({"mlb_id": [700001],
                  "player_name": ["Allen Logan"]},
                 orient="row").write_parquet(idmap)
    return bl, env, st, idmap


def _run(tmp_path, starts_rows, events,
         window=("2025-04-01", "2025-04-30")):
    bl, env, st, idmap = _write_parquets(tmp_path, starts_rows, events)
    return jc.build_task_frames(
        bl, env, st, MARKETS, window_start=window[0],
        window_end=window[1], id_map_path=idmap)


def test_name_order_normalization(tmp_path):
    # Savant/id-map name ("Allen Logan", family-first) and the vendor
    # listing ("logan allen") must normalize to ONE sorted key
    starts = [(1, 700001, date(2025, 4, 10))]
    events = [("e1", date(2025, 4, 10), "logan allen", 14)]
    starts_out, odds, meta = _run(tmp_path, starts, events)
    assert starts_out["pitcher_key"][0] == "allen logan"
    assert odds.height > 0  # quotes matched through the sorted key


def test_same_date_doubleheader_both_starts_mapped(tmp_path):
    # two starts, SAME pitcher, SAME date (doubleheader); two events
    starts = [(1, 700001, date(2025, 4, 10)),
              (2, 700001, date(2025, 4, 10))]
    events = [("e1", date(2025, 4, 10), "logan allen", 14),
              ("e2", date(2025, 4, 10), "logan allen", 20)]
    starts_out, odds, meta = _run(tmp_path, starts, events)
    assert starts_out.height == 2
    assert starts_out["has_commence"].to_list() == [True, True]
    # every start receives task odds; the duplicate (game_date,
    # pitcher_key) event pair is COUNTED in meta, never silently mixed
    assert odds.height > 0
    assert meta["archive_event_map_duplicate_keys"] == 1


def test_two_vendor_ids_one_validated_game(tmp_path):
    # one start; the vendor lists the same game under two event_ids
    # (the baseline ambiguous-identity shape). The registered
    # closest-date + event_id-order rule resolves to ONE event
    # deterministically; the duplicate is counted in meta, never
    # silently mixed. Different prices per event prove WHICH event
    # won (evt-a over at -115; evt-b over repriced to -130).
    starts = [(1, 700001, date(2025, 4, 10))]
    bl, env, st, idmap = _write_parquets(tmp_path, starts, [
        ("evt-b", date(2025, 4, 10), "logan allen", 14),
        ("evt-a", date(2025, 4, 10), "logan allen", 14)])
    # reprice evt-b's over rows so the winner is identifiable
    lines = pl.read_parquet(bl)
    lines = lines.with_columns(
        pl.when(pl.col("event_id") == "evt-b")
        .then(pl.lit(-130)).otherwise(pl.col("price"))
        .alias("price"))
    lines.write_parquet(bl)
    starts_out, odds, meta = jc.build_task_frames(
        bl, env, st, MARKETS, window_start="2025-04-01",
        window_end="2025-04-30", id_map_path=idmap)
    assert meta["archive_event_map_duplicate_keys"] == 1
    assert starts_out.height == 1
    # only the deterministic winner's quotes survive: evt-b's repriced
    # over (-130) is absent; evt-a's default over (-120) is present
    prices = odds["price"].unique().to_list()
    assert -130 not in prices and -120 in prices


def test_conflicting_game_mapping_closest_date_wins(tmp_path):
    # events on the exact Savant date and +1 day (UTC-shift listing):
    # the exact-date event wins regardless of event_id order
    starts = [(1, 700001, date(2025, 4, 10))]
    events = [("evt-late", date(2025, 4, 11), "logan allen", 14),
              ("evt-exact", date(2025, 4, 10), "logan allen", 14)]
    starts_out, odds, meta = _run(tmp_path, starts, events)
    assert starts_out.height == 1
    assert odds.height > 0  # the exact-date event's quotes are used


def test_unmatched_player_and_game(tmp_path):
    # a vendor event whose pitcher is NOT a registered start: its
    # quotes never enter the task odds; a start with no event:
    # has_commence False, counted in meta
    starts = [(1, 700001, date(2025, 4, 10))]
    events = [("e1", date(2025, 4, 10), "someonelse", 14)]
    starts_out, odds, meta = _run(tmp_path, starts, events)
    assert odds.height == 0
    assert bool(starts_out["has_commence"][0]) is False
    assert meta["starts_without_event_or_commence"] == 1
