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

CLOCK_LIST = ["board", "morning", "close"]


def _rows(spec: list[tuple[str, str]], *, interleave: bool = False) -> list[dict]:
    """Two-sided -110/+110 K quotes per (event, clock). Rows are in
    spec order unless ``interleave`` round-robins them across events
    (producing mixed-date row groups)."""
    event_rows = []
    for gd, eid in spec:
        er = []
        for clock in CLOCK_LIST:
            for side, price in (("over", -110), ("under", 110)):
                er.append({
                    "event_id": eid, "snapshot": clock,
                    "snapshot_ts": f"{gd}T15:00:00Z", "game_date": gd,
                    "season_type": "regular", "book": "draftkings",
                    "market": "pitcher_strikeouts", "player": "P A",
                    "player_norm": "a p", "line": 4.5, "side": side,
                    "price": price,
                })
        event_rows.append(er)
    if interleave and len(event_rows) > 1:
        rows = []
        max_len = max(len(er) for er in event_rows)
        for i in range(max_len):
            for er in event_rows:
                if i < len(er):
                    rows.append(er[i])
        return rows
    return [r for er in event_rows for r in er]


def _write_book_lines(tmp: Path, spec: list[tuple[str, str]], name: str,
                      *, interleave: bool = False, row_group_size: int = 6,
                      write_statistics: bool = True) -> Path:
    path = tmp / name
    pq.write_table(pa.Table.from_pylist(
        _rows(spec, interleave=interleave)), path,
        row_group_size=row_group_size,
        write_statistics=write_statistics)
    return path


def _write_envelope(tmp: Path, spec: list[tuple[str, str]],
                    name: str = "snapshot_envelope.parquet") -> Path:
    rows = []
    for gd, eid in spec:
        for clock in CLOCK_LIST:
            rows.append({
                "event_id": eid, "snapshot": clock,
                "vendor_timestamp": f"{gd}T14:55:00Z",
                "reconstructed_ts": f"{gd}T15:00:00Z",
                "commence_time": f"{gd}T19:00:00Z",
                "lag_vendor_vs_commence_sec": -300,
            })
    path = tmp / name
    pl.DataFrame(rows, schema={
        "event_id": pl.Utf8, "snapshot": pl.Utf8,
        "vendor_timestamp": pl.Utf8, "reconstructed_ts": pl.Utf8,
        "commence_time": pl.Utf8,
        "lag_vendor_vs_commence_sec": pl.Int64},
        orient="row").write_parquet(path)
    return path


# ---- 1. separable groups -> SEPARABLE
def test_separable_verdict(tmp_path):
    path = _write_book_lines(tmp_path, SPEC_ORDERED,
                             "separable.parquet", row_group_size=6)
    layout = probe.row_group_separation(path, protected_boundary="2025-06-30")
    assert layout["verdict"] == "SEPARABLE"
    statuses = {g["status"] for g in layout["row_groups"]}
    assert statuses <= {"WINDOW_OR_EARLIER", "PROTECTED_ONLY"}


# ---- 2. mixed-date groups -> NOT_SEPARABLE
def test_mixed_group_verdict(tmp_path):
    interleaved = []
    for i in range(3):
        interleaved.append(("2025-04-10", f"eA{i}"))
        interleaved.append(("2026-05-01", f"eB{i}"))
    path = _write_book_lines(tmp_path, interleaved, "mixed.parquet",
                             interleave=True, row_group_size=3)
    layout = probe.row_group_separation(path, protected_boundary="2025-06-30")
    assert layout["verdict"] == "NOT_SEPARABLE"
    assert any(g["status"] == "OVERLAPS_PROTECTED"
               for g in layout["row_groups"])


# ---- 3. missing/unusable statistics -> UNVERIFIABLE
def test_missing_statistics_verdict(tmp_path):
    path = _write_book_lines(tmp_path, SPEC_ORDERED, "nostats.parquet",
                             row_group_size=6, write_statistics=False)
    layout = probe.row_group_separation(path, protected_boundary="2025-06-30")
    assert layout["verdict"] == "UNVERIFIABLE"
    assert all(g["game_date_min"] is None for g in layout["row_groups"])


# ---- 4. blocked run: no data-page read, no stage 1
def test_blocked_run_stops_before_decode(tmp_path, monkeypatch):
    interleaved = []
    for i in range(3):
        interleaved.append(("2025-04-10", f"eA{i}"))
        interleaved.append(("2026-05-01", f"eB{i}"))
    bl = _write_book_lines(tmp_path, interleaved, "mixed.parquet",
                           interleave=True, row_group_size=3)
    env = _write_envelope(tmp_path, interleaved)
    probe.__dict__["BOOK_LINES"] = bl
    probe.__dict__["ENVELOPE"] = env
    probe.__dict__["OUT"] = tmp_path / "_probe" / "board_coverage_2025H1.json"

    # capture the real scan_parquet BEFORE patching to avoid recursion
    real_scan = pl.scan_parquet
    scanned = []

    def spy_scan(source, *a, **kw):
        scanned.append(str(source))
        return real_scan(source, *a, **kw)

    monkeypatch.setattr(pl, "scan_parquet", spy_scan)
    rc = probe.main()
    assert rc == 1
    assert scanned == []  # the stage-1 data-page read never ran
    report = json.loads(probe.OUT.read_text(encoding="utf-8"))
    assert report["stage1_executed"] is False
    assert report["blocked"]["reason"]
    assert report["row_group_separation"]["verdict"] in (
        "UNVERIFIABLE", "NOT_SEPARABLE")


# ---- 5. SEPARABLE run: counts + criterion
def test_separable_run_counts(tmp_path):
    bl = _write_book_lines(tmp_path, SPEC_ORDERED, "separable.parquet",
                           row_group_size=6)
    env = _write_envelope(tmp_path, SPEC_ORDERED)
    probe.__dict__["BOOK_LINES"] = bl
    probe.__dict__["ENVELOPE"] = env
    probe.__dict__["OUT"] = tmp_path / "_probe" / "board_coverage_2025H1.json"
    rc = probe.main()
    assert rc == 0
    report = json.loads(probe.OUT.read_text(encoding="utf-8"))
    assert report["stage1_executed"] is True
    assert report["row_group_separation"]["verdict"] == "SEPARABLE"
    crit = report["declared_criterion"]
    assert crit["label"].startswith("OPERATIONAL COVERAGE HEURISTIC")
    assert crit["board_two_sided"] == 1 and crit["close_two_sided"] == 1
    assert crit["median_books_per_event_board"] == 1.0
    assert crit["verdict"] == "sparse_or_absent"  # median 1 < 2
    for clock in probe.CLOCKS:
        assert report["per_clock_counts"][clock]["n_events"] == 1
        assert report["per_clock_counts"][clock][
            "n_two_sided_contracts"] == 1
        assert report["per_clock_counts"][clock][
            "median_books_per_event"] == 1.0
    assert report["envelope_timestamps"]["close"][
        "vendor_timestamp_present"] == 1
    assert report["envelope_timestamps"]["close"]["lag_p50_sec"] == -300
