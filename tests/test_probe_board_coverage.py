"""Synthetic tests for the board-clock coverage probe
(probe_board_coverage_2025H1.py). SYNTHETIC ONLY: tmp parquets; no
private lake reads, no network, no canonical writes, no outcomes.

Requirement -> implementation -> test-evidence closure table:
  Footer-metadata-only row-group separation verdicts
  (metadata read never touches data pages):
    separable groups -> SEPARABLE                     -> test 1
    mixed-date groups -> NOT_SEPARABLE                -> test 2
    missing/unusable date statistics -> UNVERIFIABLE  -> test 3
  Blocked run: stage 1 (data-page read) NOT executed when
  not SEPARABLE; blocked evidence written write-once -> test 4
  SEPARABLE run: window-restricted counts by clock,
  two-sided contracts, median books-per-event, timestamp
  fields; criterion labeled an operational heuristic  -> test 5
"""
from __future__ import annotations

import json

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from production.ops.market_research import (
    probe_board_coverage_2025H1 as probe,
)

SPEC_ORDERED = [("2025-04-10", "e2025a"), ("2026-05-01", "e2026a")]


def _rows(spec: list[tuple[str, str]], *, interleave: bool = False) -> list[dict]:
    """Two-sided -110/+110 K quotes per (event, clock). The snapshot
    column carries the CLOCK; the year distinction comes from
    game_date (and the event map), not the snapshot. ``interleave``
    orders rows so consecutive rows alternate 2025/2026 events."""
    rows = []
    for gd, eid in spec:
        for clock in probe.CLOCKS:
            for side, price in (("over", -110), ("under", 110)):
                rows.append({
                    "event_id": eid, "snapshot": clock,
                    "snapshot_ts": f"{gd}T15:00:00Z", "game_date": gd,
                    "season_type": "regular", "book": "draftkings",
                    "market": "pitcher_strikeouts", "player": "P A",
                    "player_norm": "a p", "line": 4.5, "side": side,
                    "price": price,
                })
    if interleave:
        n = len(rows) // 2
        a, b = rows[:n], rows[n:]
        rows = [r for pair in zip(a, b) for r in pair]
    return rows


def _setup(tmp: Path, spec: list[tuple[str, str]], *, name: str,
           row_group_size: int = 6, write_statistics: bool = True,
           interleave: bool = False,
           out_name: str = "board_coverage_2025H1.json") -> None:
    """Write synthetic book_lines + envelope parquets and point the
    probe's module constants at them."""
    path = tmp / name
    pq.write_table(pa.Table.from_pylist(
        _rows(spec, interleave=interleave)), path,
        row_group_size=row_group_size,
        write_statistics=write_statistics)
    probe.__dict__["BOOK_LINES"] = path
    env_path = tmp / "snapshot_envelope.parquet"
    env_rows = []
    for gd, eid in spec:
        for clock in probe.CLOCKS:
            env_rows.append({
                "event_id": eid, "snapshot": clock,
                "vendor_timestamp": f"{gd}T14:55:00Z",
                "reconstructed_ts": f"{gd}T15:00:00Z",
                "commence_time": f"{gd}T19:00:00Z",
                "lag_vendor_vs_commence_sec": -300,
            })
    pl.DataFrame(env_rows, schema={
        "event_id": pl.Utf8, "snapshot": pl.Utf8,
        "vendor_timestamp": pl.Utf8, "reconstructed_ts": pl.Utf8,
        "commence_time": pl.Utf8,
        "lag_vendor_vs_commence_sec": pl.Int64},
        orient="row").write_parquet(env_path)
    probe.__dict__["ENVELOPE"] = env_path
    probe.__dict__["OUT"] = tmp / "_probe" / out_name


# ---- 1. separable groups -> SEPARABLE
def test_separable_verdict(tmp_path):
    layout = probe.row_group_separation(
        _setup(tmp_path, SPEC_ORDERED, name="separable.parquet",
               row_group_size=6) or probe.BOOK_LINES,
        protected_boundary="2025-06-30")
    assert layout["verdict"] == "SEPARABLE"
    statuses = {g["status"] for g in layout["row_groups"]}
    assert statuses <= {"WINDOW_OR_EARLIER", "PROTECTED_ONLY"}


# ---- 2. mixed-date groups -> NOT_SEPARABLE
def test_mixed_group_verdict(tmp_path):
    interleaved = []
    for i in range(3):
        interleaved.append(("2025-04-10", f"eA{i}"))
        interleaved.append(("2026-05-01", f"eB{i}"))
    layout = probe.row_group_separation(
        _setup(tmp_path, interleaved, name="mixed.parquet",
               row_group_size=3, interleave=True) or probe.BOOK_LINES,
        protected_boundary="2025-06-30")
    assert layout["verdict"] == "NOT_SEPARABLE"
    assert any(g["status"] == "OVERLAPS_PROTECTED"
               for g in layout["row_groups"])


# ---- 3. missing/unusable statistics -> UNVERIFIABLE
def test_missing_statistics_verdict(tmp_path):
    layout = probe.row_group_separation(
        _setup(tmp_path, SPEC_ORDERED, name="nostats.parquet",
               row_group_size=6, write_statistics=False)
        or probe.BOOK_LINES, protected_boundary="2025-06-30")
    assert layout["verdict"] == "UNVERIFIABLE"
    assert all(g["game_date_min"] is None
               for g in layout["row_groups"])


# ---- 4. blocked run: no data-page read, no stage 1
def test_blocked_run_stops_before_decode(tmp_path, monkeypatch):
    interleaved = []
    for i in range(3):
        interleaved.append(("2025-04-10", f"eA{i}"))
        interleaved.append(("2026-05-01", f"eB{i}"))
    _setup(tmp_path, interleaved, name="mixed.parquet",
           row_group_size=3, interleave=True)

    scanned = []
    monkeypatch.setattr(
        pl, "scan_parquet",
        lambda source, *a, **kw: scanned.append(str(source))
        or _fail_scan(source, *a, **kw))
    rc = probe.main()
    assert rc == 1
    assert scanned == []  # the stage-1 data-page read never ran
    report = json.loads(
        (tmp_path / "_probe" / "board_coverage_2025H1.json")
        .read_text(encoding="utf-8"))
    assert report["stage1_executed"] is False
    assert report["blocked"]["reason"]
    assert report["row_group_separation"]["verdict"] in (
        "UNVERIFIABLE", "NOT_SEPARABLE")


def _fail_scan(source, *a, **kw):
    raise AssertionError("data-page read attempted while blocked")


# ---- 5. SEPARABLE run: counts + criterion
def test_separable_run_counts(tmp_path, monkeypatch):
    _setup(tmp_path, SPEC_ORDERED, name="separable.parquet",
           row_group_size=6)
    rc = probe.main()
    assert rc == 0
    report = json.loads(probe.OUT.read_text(encoding="utf-8"))
    assert report["stage1_executed"] is True
    assert report["row_group_separation"]["verdict"] == "SEPARABLE"
    crit = report["declared_criterion"]
    assert crit["label"].startswith("OPERATIONAL COVERAGE HEURISTIC")
    # the 2026 event (e2026a) is correctly excluded pre-decode by the
    # game_date window; only the 2025H1 event survives
    assert crit["board_two_sided"] == 1 and crit["close_two_sided"] == 1
    # one book per event -> median books-per-event 1 < 2 -> sparse
    assert crit["median_books_per_event_board"] == 1
    assert crit["verdict"] == "sparse_or_absent"
    for clock in probe.CLOCKS:
        assert report["per_clock_counts"][clock]["n_events"] == 1
        assert report["per_clock_counts"][clock][
            "n_two_sided_contracts"] == 1
        assert report["per_clock_counts"][clock][
            "median_books_per_event"] == 1.0
    assert report["envelope_timestamps"]["close"][
        "vendor_timestamp_present"] == 1
    assert report["envelope_timestamps"]["close"][
        "lag_p50_sec"] == -300
