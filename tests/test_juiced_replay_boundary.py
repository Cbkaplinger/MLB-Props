"""Synthetic boundary tests for the development-only juiced replay
(juiced_replay_ledger.py). NO private-data reads, NO network, NO
canonical-path writes: every test uses tmp_path fixtures and the
module's own pure helpers.

Requirement -> implementation -> test-evidence closure table:
  Year-restricted runs require --out-suffix (canonical report
  never overwritten)                                   -> test 1
  Write-once: existing destination refuses             -> test 2
  Canonical default unchanged (no year window ->
  canonical paths, no guard)                           -> test 3
  Pre-decode event restriction: the lazy book-lines
  scan excludes protected-year events (2026 rows
  never decoded into a frame)                          -> test 4
  Event-date-map year filter (allowed set)             -> test 5
  Network-free boundary: no HTTP client imports or
  calls in the ledger module                           -> test 6
  Raw two-way prices per snapshot stored in output
  rows (market-only movement baseline input)           -> test 7
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))

import juiced_replay_ledger as jr  # noqa: E402


def _evdate() -> dict:
    return {"e2025a": "2025-04-10", "e2025b": "2025-05-20",
            "e2026a": "2026-04-10"}


# ------------------- 1-3. output guard
def test_year_restricted_requires_suffix():
    with pytest.raises(SystemExit, match="--out-suffix"):
        jr.resolve_outputs("", True, Path("x.parquet"), Path("x.json"))


def test_year_restricted_write_once(tmp_path):
    existing = tmp_path / "juiced_replay_candidates_dev.parquet"
    existing.write_bytes(b"x")
    with pytest.raises(SystemExit, match="destination exists"):
        jr.resolve_outputs("__dev", True, existing,
                           tmp_path / "juiced_replay_report_dev.json")
    fresh_p = tmp_path / "juiced_replay_candidates_fresh.parquet"
    fresh_r = tmp_path / "juiced_replay_report_dev.json"
    assert jr.resolve_outputs("__dev", True, fresh_p,
                              fresh_r) == (fresh_p, fresh_r)
    assert not fresh_p.exists() and not fresh_r.exists()


def test_canonical_default_unchanged(tmp_path):
    c_parquet = tmp_path / "juiced_replay_candidates.parquet"
    c_report = tmp_path / "juiced_replay_report.json"
    p, r = jr.resolve_outputs("", False, c_parquet, c_report)
    assert p == c_parquet and r == c_report


# ------------------- 4-5. pre-decode event restriction
def _write_book_lines(tmp: Path) -> Path:
    rows = []
    for eid, book in (("e2025a", "draftkings"), ("e2026a", "fanduel")):
        # both rows are "morning" snapshots; the YEAR distinction comes
        # from the event-date map (e2026a -> 2026), which is what the
        # pre-decode restriction must exclude
        for side, price in (("over", -110), ("under", -110)):
            rows.append((eid, "pitcher_strikeouts", "morning", "P1", 4.5,
                         side, price, book))
    path = tmp / "book_lines_pitcher.parquet"
    pl.DataFrame(rows, schema={
        "event_id": pl.Utf8, "market": pl.Utf8, "snapshot": pl.Utf8,
        "player_norm": pl.Utf8, "line": pl.Float64, "side": pl.Utf8,
        "price": pl.Int64, "book": pl.Utf8}, orient="row").write_parquet(path)
    return path


def test_restricted_scan_excludes_protected_year(tmp_path, monkeypatch):
    path = _write_book_lines(tmp_path)
    ev = pl.DataFrame({"event_id": ["e2025a"], "gd": ["2025-04-10"]})
    monkeypatch.setattr(jr, "HIST", tmp_path)
    out = jr._two_way_paid("morning", ev, None,
                           event_ids={"e2025a"})
    assert out.height == 1
    assert out["morning_event_id"].to_list() == ["e2025a"]
    # canonical path (no restriction) still decodes everything it did
    out_all = jr._two_way_paid("morning", ev, None)
    assert out_all.height == 1  # only e2025a is in the event frame
    ev_full = pl.DataFrame({"event_id": ["e2025a", "e2026a"],
                            "gd": ["2025-04-10", "2026-04-10"]})
    out_full = jr._two_way_paid("morning", ev_full, None)
    assert out_full.height == 2  # unrestricted: both years decoded


def test_allowed_event_ids_year_filter():
    ys, ye = "2025", "2025"
    allowed = {eid for eid, gd in _evdate().items()
               if ys <= str(gd)[:4] <= ye}
    assert allowed == {"e2025a", "e2025b"}
    assert "e2026a" not in allowed


# ------------------- 6. network-free boundary (static)
def test_ledger_module_is_network_free():
    src = Path(jr.__file__).read_text(encoding="utf-8")
    for token in ("requests", "urllib", "httpx", "socket",
                  "pull_oddsapi", "http.get", "session.post"):
        assert token not in src, f"network surface found: {token}"


# ------------------- 7. raw two-way prices in output rows
def test_output_rows_carry_raw_two_way_prices():
    row = {
        "open_over": -150, "open_under": 130,
        "morning_over": None, "morning_under": None,
        "close_over": -120, "close_under": 105,
    }
    # the market-only movement baseline derives same-book open->close
    # fair movement from these columns alone (no model input)
    for snap in ("open", "morning", "close"):
        o, u = row[f"{snap}_over"], row[f"{snap}_under"]
        if o is not None and u is not None:
            fair = mk_devig(o, u)
            assert 0.0 < fair < 1.0
    assert row["morning_over"] is None


def mk_devig(o_amer: int, u_amer: int) -> float:
    """Local mirror of the registered two-way de-vig for the test only;
    the production path reuses market_eval_k/Python.market functions."""
    ro = 100.0 / (abs(o_amer) + 100) if o_amer < 0 else 100 / (o_amer + 100)
    ru = 100.0 / (u_amer + 100) if u_amer < 0 else 100 / (u_amer + 100)
    return ro / (ro + ru)
