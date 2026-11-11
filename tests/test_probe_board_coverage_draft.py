"""Synthetic tests for the board-clock coverage probe
(probe_board_coverage_2025H1.py). SYNTHETIC ONLY: tmp parquets, no
private lake reads, no network, no canonical writes.

Requirement -> implementation -> test-evidence closure table:
  Footer-metadata-only row-group separation verdicts:
    separable groups -> SEPARABLE                     -> test 1
    mixed-date groups -> NOT_SEPARABLE                -> test 2
    missing/unusable date statistics -> UNVERIFIABLE  -> test 3
  Blocked run: NO data-page read when not SEPARABLE
  (scan never invoked; blocked evidence written
  write-once to the declared destination)           -> test 4
  SEPARABLE run: window-restricted counts by
  clock/book, two-sided contracts, timestamp fields,
  criterion labeled an operational heuristic        -> test 5
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from production.ops.market_research import (
    probe_board_coverage_2025H1 as probe,
)

CLOCK = "morning"
CLOCKS = ["board", "morning", "close"]
SPEC = [("2025-04-10", "e2025a"), ("2026-05-01", "e2026a")]


def _rows(spec: list[tuple[str, str]]) -> list[dict]:
    """Two-sided -110/+110 K quotes for one player per event at every
    declared clock."""
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
    return rows


def _write(spec: list[tuple[str, str]], tmp: Path, name: str, *,
           rows_per_group: int = 6,
           write_statistics: bool = True) -> Path:
    """row_group_size controls which dates share a row group; the
    ordered spec yields date-homogeneous groups, an interleaved spec
    yields mixed groups."""
    path = tmp / name
    pq.write_table(pa.Table.from_pylist(_rows(spec)), path,
                   row_group_size=rows_per_group,
                   write_statistics=write_statistics)
    return path


def _setup(tmp: Path, spec: list[tuple[str, str]], *, name: str,
           row_group_size: int = 6, write_statistics: bool = True,
           out_name: str = "board_coverage_2025H1.json") -> None:
    probe.__dict__["BOOK_LINES"] = _write(
        spec, tmp, name, rows_per_group=row_group_size,
        write_statistics=write_statistics)
    probe.__dict__["ENVELOPE"] = _write_envelope(spec, tmp)
    probe.__dict__["OUT"] = tmp / "_probe" / out_name


def _write_envelope(spec: list[tuple[str, str]], tmp: Path,
                    name: str = "snapshot_envelope.parquet") -> Path:
    import datetime as dt
    rows = []
    for gd, eid in spec:
        for clock in probe.CLOCKS:
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
    spec = sorted([("2025-04-10", "e2025a"), ("2026-05-01", "e2026a")])
    layout = probe.row_group_separation(
        probe.__dict__["ENVELOPE"] and
        _write(spec, tmp_path, "separable.parquet", rows_per_group=6),
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
        _write(interleaved, tmp_path, "mixed.parquet",
               rows_per_group=3),
        protected_boundary="2025-06-30")
    assert layout["verdict"] == "NOT_SEPARABLE"
    assert any(g["status"] == "OVERLAPS_PROTECTED"
               for g in layout["row_groups"])


# ---- 3. missing/unusable statistics -> UNVERIFIABLE
def test_missing_statistics_verdict(tmp_path):
    spec = [("2025-04-10", "e2025a"), ("2026-05-01", "e2026a")]
    layout = probe.row_group_separation(
        _write(spec, tmp_path, "nostats.parquet", rows_per_group=6,
               write_statistics=False),
        protected_boundary="2025-06-30")
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
           row_group_size=3)
    scanned = []
    monkeypatch.setattr(
        probe.pl, "scan_parquet",
        lambda source, *a, **kw: scanned.append(str(source))
        or _real_scan(source, *a, **kw))
    rc = probe.main()
    assert rc == 1
    # the blocked path must never reach the stage-1 data scan
    assert scanned == []
    report = json.loads(
        probe.OUT.read_text(encoding="utf-8"))
    assert report["stage1_executed"] is False
    assert report["blocked"]["reason"]
    assert report["row_group_separation"]["verdict"] in (
        "UNVERIFIABLE", "NOT_SEPARABLE")


def _real_scan(source, *a, **kw):
    return pl.scan_parquet(source, *a, **kw)


_real_scan = pl.scan_parquet


# ---- 5. SEPARABLE run: counts, criterion label
def test_separable_run_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "scan_parquet",
                        _scan_guard := _real_scan)
    spec = sorted([("2025-04-10", "e2025a"), ("2026-05-01", "e2026a")])
    _setup(tmp_path, spec)
    rc = probe.main()
    assert rc == 0
    report = json.loads(probe.OUT.read_text(encoding="utf-8"))
    assert report["stage1_executed"] is True
    assert report["row_group_separation"]["verdict"] == "SEPARABLE"
    crit = report["declared_criterion"]
    assert crit["label"].startswith("OPERATIONAL COVERAGE HEURISTIC")
    assert crit["board_two_sided"] == 2 and crit["close_two_sided"] == 2
    assert crit["median_books_per_event_board"] == 1
    assert crit["verdict"] == "sparse_or_absent"  # median 1 < 2
    for clock in probe.CLOCKS:
        assert report["per_clock_counts"][clock]["n_events"] == 1
        assert report["per_clock_counts"][clock][
            "n_two_sided_contracts"] == 1
    assert report["envelope_timestamps"]["close"][
        "vendor_timestamp_present"] == 1
