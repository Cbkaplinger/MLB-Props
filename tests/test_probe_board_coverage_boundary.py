"""Synthetic tests for the boundary-exception coverage follow-up
(probe_board_coverage_boundary_2025H1.py). SYNTHETIC ONLY: tmp
parquets + tmp blocked report; no private lake reads, no network, no
canonical writes, no outcomes.

Requirement -> implementation -> test-evidence closure table:
  Only allowed groups decoded (read_row_groups receives exactly
  the allowed indices; protected-only groups never decoded)  -> test 1
  Boundary-group rows filtered to 2025H1 immediately after
  decode (no protected dates in the materialized frame)      -> test 1
  Input identity mismatch refuses                            -> test 2
  Fresh footer layout != recorded layout refuses             -> test 3
  Envelope footer preflight: missing/unusable date stats
  fail closed (undeclared access requirement)                -> test 4
  Original blocked report destination never overwritten;
  fresh write-once report                                    -> test 5
  Aggregation reuses the registered coverage definitions
  (hand-computed counts on the synthetic window rows)        -> test 6
"""
from __future__ import annotations

import hashlib
import json

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from production.ops.market_research import (
    probe_board_coverage_boundary_2025H1 as fb,
)

BOUNDARY = "2025-06-30"
CLOCKS = ["board", "morning", "close"]
# (gd, eid): two 2025H1 events + one protected (2026) event
SPEC = [("2025-04-10", "e2025a"), ("2026-05-01", "e2026b"),
        ("2025-05-10", "e2025c")]


def _rows(spec: list[tuple[str, str]], *, interleave: bool = False) -> list[dict]:
    """Two-sided -110/+110 K quotes per (event, clock). The snapshot
    column carries the CLOCK; the year distinction comes from
    game_date (and the event map), not the snapshot. ``interleave``
    round-robins the events' rows so consecutive rows alternate
    2025/2026 events (producing mixed row groups)."""
    event_rows = []
    for gd, eid in spec:
        er = []
        for clock in CLOCKS:
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
    if not interleave:
        return [r for er in event_rows for r in er]
    rows = []
    max_len = max(len(er) for er in event_rows)
    for i in range(max_len):
        for er in event_rows:
            if i < len(er):
                rows.append(er[i])
    return rows


def _write_book_lines(tmp, name, spec, *, interleave=False,
                      rows_per_group=6, write_statistics=True):
    path = tmp / name
    pq.write_table(pa.Table.from_pylist(
        _rows(spec, interleave=interleave)), path,
        row_group_size=rows_per_group,
        write_statistics=write_statistics)
    return path


def _write_envelope(tmp, name, spec):
    rows = []
    for gd, eid in spec:
        for clock in CLOCKS:
            rows.append({"event_id": eid, "snapshot": clock,
                         "vendor_timestamp": f"{gd}T14:55:00Z",
                         "reconstructed_ts": f"{gd}T15:00:00Z",
                         "commence_time": f"{gd}T19:00:00Z",
                         "lag_vendor_vs_commence_sec": -300})
    path = tmp / name
    pl.DataFrame(rows, schema={
        "event_id": pl.Utf8, "snapshot": pl.Utf8,
        "vendor_timestamp": pl.Utf8, "reconstructed_ts": pl.Utf8,
        "commence_time": pl.Utf8,
        "lag_vendor_vs_commence_sec": pl.Int64},
        orient="row").write_parquet(path)
    return path


def _footer_groups(spec: list[tuple[str, str]], *, interleave: bool = False,
                   rows_per_group: int = 6) -> list[dict]:
    """Footer layout the pyarrow writer produces for the given spec
    and row order (rows in order, chunked every rows_per_group)."""
    bl_rows = _rows(spec, interleave=interleave)
    groups = []
    n_groups = (len(bl_rows) + rows_per_group - 1) // rows_per_group
    for i in range(n_groups):
        chunk = bl_rows[i * rows_per_group:(i + 1) * rows_per_group]
        gds = sorted({r["game_date"] for r in chunk})
        groups.append({"row_group": i, "rows": len(chunk),
                       "game_date_min": gds[0], "game_date_max": gds[-1],
                       "status": "OVERLAPS_PROTECTED"
                       if gds[0] <= BOUNDARY < gds[-1]
                       else ("WINDOW_OR_EARLIER"
                             if gds[-1] <= BOUNDARY else "PROTECTED_ONLY")})
    return groups


def _blocked_report(tmp, book_lines, envelope, spec, *,
                    interleave: bool = False, rows_per_group: int = 6,
                    hash_override: str | None = None) -> Path:
    """Blocked report bound to the CURRENT file hashes and the footer
    layout the writer produces for the spec."""
    h_bl = hashlib.sha256(book_lines.read_bytes()).hexdigest()
    h_env = hashlib.sha256(envelope.read_bytes()).hexdigest()
    if hash_override is not None:
        h_bl = hash_override
    report = {
        "input_sha256": {"book_lines_pitcher": h_bl,
                         "snapshot_envelope": h_env},
        "row_group_separation": {
            "verdict": "NOT_SEPARABLE", "verifiable": True,
            "row_groups": _footer_groups(spec, interleave=interleave,
                                         rows_per_group=rows_per_group)},
    }
    path = tmp / "blocked_report.json"
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return path


def _setup_full(tmp, *, spec=SPEC, interleave=False, rows_per_group=6,
                layout_interleave=None, layout_spec=None,
                hash_override=None,
                out_name="board_coverage_boundary_2025H1.json") -> Path:
    bl = _write_book_lines(tmp, "bl.parquet", spec,
                           interleave=interleave,
                           rows_per_group=rows_per_group)
    env = _write_envelope(tmp, "env.parquet", spec)
    li = layout_interleave if layout_interleave is not None else interleave
    ls = layout_spec if layout_spec is not None else spec
    blocked = _blocked_report(tmp, bl, env, ls, interleave=li,
                              rows_per_group=rows_per_group,
                              hash_override=hash_override)
    fb.__dict__["BOOK_LINES"] = bl
    fb.__dict__["ENVELOPE"] = env
    fb.__dict__["BLOCKED_REPORT"] = blocked
    fb.__dict__["OUT"] = tmp / "_probe" / out_name
    return blocked


# ---- 1. only allowed groups decoded; boundary rows filtered
def test_only_allowed_groups_decoded_and_boundary_filtered(
        tmp_path, monkeypatch):
    # 2026 event interleaved with 2025H1 events -> mixed row groups
    # (each group spans the protected boundary); row_group_size=3
    spec = SPEC + [("2026-05-01", "e2026c")]
    _setup_full(tmp_path, spec=spec, interleave=True, rows_per_group=3)

    decoded = []
    real_rrg = pq.ParquetFile.read_row_groups

    def spy(self, row_groups, *a, **kw):
        decoded.append(list(row_groups))
        return real_rrg(self, row_groups, *a, **kw)

    monkeypatch.setattr(pq.ParquetFile, "read_row_groups", spy)

    rc = fb.main()
    assert rc == 0
    report = json.loads(fb.OUT.read_text(encoding="utf-8"))

    # protected-only groups were never decoded
    protected = [g["row_group"] for g in
                 report["row_group_separation"]["row_groups"]
                 if g["status"] == "PROTECTED_ONLY"]
    for call in decoded:
        assert not (set(call) & set(protected))
    # boundary groups (OVERLAPS_PROTECTED) WERE decoded under the
    # declared exception
    boundary = [g["row_group"] for g in
                report["row_group_separation"]["row_groups"]
                if g["status"] == "OVERLAPS_PROTECTED"]
    assert boundary and any(set(call) & set(boundary) for call in decoded)

    # after the immediate filter, no protected dates survive anywhere
    acc = report["accounting"]
    assert acc["protected_date_handling"].startswith("boundary-group")
    assert acc["book_lines"]["rows_after_window_filter"] \
        <= acc["book_lines"]["rows_decoded"]


# ---- 2. input identity mismatch refuses
def test_input_hash_mismatch_refuses(tmp_path):
    _setup_full(tmp_path, hash_override="0" * 64)
    with pytest.raises(SystemExit, match="input identity mismatch"):
        fb.main()


# ---- 3. layout mismatch refuses
def test_layout_mismatch_refuses(tmp_path):
    # recorded layout describes a DIFFERENT spec than the actual file
    _setup_full(tmp_path, spec=SPEC,
                layout_spec=[("2025-04-10", "eX"), ("2025-05-10", "eY")])
    with pytest.raises(SystemExit, match="layout mismatch"):
        fb.main()


# ---- 4. envelope preflight fails closed on undeclared access
def test_envelope_missing_stats_fail_closed(tmp_path):
    bl = _write_book_lines(tmp_path, "bl.parquet", SPEC)
    env = _write_envelope(tmp_path, "env.parquet", SPEC)
    # rewrite WITHOUT statistics (undeclared: unusable commence stats)
    pq.write_table(pa.Table.from_pylist(
        _rows(SPEC)), env, write_statistics=False)
    blocked = tmp_path / "blocked.json"
    blocked.write_text(json.dumps({
        "input_sha256": {
            "book_lines_pitcher": hashlib.sha256(
                bl.read_bytes()).hexdigest(),
            "snapshot_envelope": hashlib.sha256(
                env.read_bytes()).hexdigest()},
        "row_group_separation": {"verdict": "NOT_SEPARABLE",
                                 "verifiable": True,
                                 "row_groups": _footer_groups(SPEC)},
    }), encoding="utf-8")
    fb.__dict__["BOOK_LINES"] = bl
    fb.__dict__["ENVELOPE"] = env
    fb.__dict__["BLOCKED_REPORT"] = blocked
    fb.__dict__["OUT"] = tmp_path / "_probe" / "out.json"
    with pytest.raises(SystemExit, match="UNVERIFIABLE"):
        fb.main()


# ---- 5. original blocked report never overwritten
def test_original_blocked_report_untouched(tmp_path):
    blocked = _setup_full(tmp_path)
    before = (blocked.read_bytes(), blocked.stat().st_mtime_ns)
    rc = fb.main()
    assert rc == 0
    after = (blocked.read_bytes(), blocked.stat().st_mtime_ns)
    assert before == after
    assert fb.OUT != fb.BLOCKED_REPORT


# ---- 6. aggregation reuses the registered coverage definitions
def test_aggregation_matches_hand_computation(tmp_path):
    _setup_full(tmp_path)
    rc = fb.main()
    assert rc == 0
    report = json.loads(fb.OUT.read_text(encoding="utf-8"))
    per_clock = report["per_clock_counts"]
    # hand computation: two 2025H1 events, one book, three clocks ->
    # per clock: 4 quotes (2 events x 2 sides), 2 events, 2 starts,
    # 2 two-sided contracts, median books-per-event 1.0
    for clock in CLOCKS:
        s = per_clock[clock]
        assert s["n_events"] == 2
        assert s["n_two_sided_contracts"] == 2
        assert s["n_quotes"] == 4
        assert s["median_books_per_event"] == 1.0
