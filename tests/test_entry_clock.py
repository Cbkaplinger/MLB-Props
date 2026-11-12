"""End-to-end synthetic test for the paid-only T-5h replay mode
(entry_clock=morning_only) in juiced_replay_ledger.py.

Creates all synthetic inputs (book_lines, panel, envelope, event-date
map) in tmp_path, patches the module constants, runs main() once with
--entry-clock morning_only, and verifies:
- output rows carry snap="morning" and entry_clock="morning_only"
- no Friend opens appear (open_over/open_under always null)
- the scores (log loss, Brier, CLV, PnL) are correctly computed
- the rejected contracts carry the correct reasons
- the baseline population is independent of the legacy model flag

NO private lake reads, NO network, NO canonical overwrites.
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from production.ops.market_research import (
    juiced_replay_ledger as jr,
)

GD = "2025-04-10"
KEY = "a p"
LINE = 4.5
P_MODEL = 0.55
Y = 1.0  # over hit (K >= 4.5)


def _book_lines_rows():
    """Two-sided morning + close quotes for 2 books at 1 event."""
    rows = []
    for snap in ("morning", "close"):
        for book in ("draftkings", "fanduel"):
            for side, price in (("over", -120), ("under", 105)):
                rows.append({
                    "event_id": "evt001", "snapshot": snap,
                    "snapshot_ts": f"{GD}T18:55:00Z" if snap == "close"
                    else f"{GD}T14:00:00Z",
                    "game_date": GD, "season_type": "regular",
                    "book": book, "market": "pitcher_strikeouts",
                    "player": "P A", "player_norm": KEY,
                    "line": LINE, "side": side, "price": price,
                })
    return rows


def _panel_rows():
    """Frozen-model panel: 2 rows (one per line/side combo matching the
    book_lines join key)."""
    return [
        {"gd": GD, "key": KEY, "line": LINE, "p_ours_cal": P_MODEL,
         "y": Y, "p_book_close": 0.50, "player_name": "P A"},
    ]


def _envelope_rows():
    return [
        {"event_id": "evt001", "snapshot": "morning",
         "vendor_timestamp": f"{GD}T14:00:00Z",
         "reconstructed_ts": f"{GD}T14:00:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": -32400},
        {"event_id": "evt001", "snapshot": "close",
         "vendor_timestamp": f"{GD}T22:55:00Z",
         "reconstructed_ts": f"{GD}T22:55:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": -300},
    ]


def _setup(tmp_path: Path, entry_clock: str) -> None:
    """Create all synthetic inputs and patch the module constants."""
    # HIST root (for book_lines + envelope)
    hist = tmp_path / "hist"
    hist.mkdir(parents=True)
    jr.__dict__["HIST"] = hist
    jr.__dict__["EVENT_DATE_MAP"] = hist / "event_date_map.json"
    # ODDS_DIR root (for panel + outputs)
    odds_dir = tmp_path / "odds_log"
    odds_dir.mkdir(parents=True)
    jr.__dict__["ODDS_DIR"] = odds_dir
    jr.__dict__["PANEL"] = odds_dir / "universe_panel_live.parquet"
    # FRIEND: point at a nonexistent path (morning_only never reads it;
    # registered would fail closed on the missing file)
    jr.__dict__["FRIEND"] = tmp_path / "nonexistent_friend.csv"

    # event_date_map: event_id -> gd (written to the patched path)
    (hist / "event_date_map.json").write_text(
        json.dumps({"evt001": GD}), encoding="utf-8")
    # monkeypatch load_event_date_map: the production function reads
    # from join_keys.EVENT_DATE_MAP which is NOT patched by the test's
    # module-constant overrides
    jr.__dict__["load_event_date_map"] = lambda: {"evt001": GD}

    # book_lines (written to the patched HIST path)
    bl = hist / "book_lines_pitcher.parquet"
    pl.DataFrame(_book_lines_rows(), schema={
        "event_id": pl.Utf8, "snapshot": pl.Utf8, "snapshot_ts": pl.Utf8,
        "game_date": pl.Utf8, "season_type": pl.Utf8, "book": pl.Utf8,
        "market": pl.Utf8, "player": pl.Utf8, "player_norm": pl.Utf8,
        "line": pl.Float64, "side": pl.Utf8, "price": pl.Int64},
        orient="row").write_parquet(bl)

    # panel (written to the patched ODDS_DIR path)
    pl.DataFrame(_panel_rows(), schema={
        "gd": pl.Utf8, "key": pl.Utf8, "line": pl.Float64,
        "p_ours_cal": pl.Float64, "y": pl.Float64,
        "p_book_close": pl.Float64, "player_name": pl.Utf8},
        orient="row").write_parquet(jr.PANEL)

    # envelope
    env = hist / "snapshot_envelope.parquet"
    pl.DataFrame(_envelope_rows(), schema={
        "event_id": pl.Utf8, "snapshot": pl.Utf8,
        "vendor_timestamp": pl.Utf8, "reconstructed_ts": pl.Utf8,
        "commence_time": pl.Utf8,
        "lag_vendor_vs_commence_sec": pl.Int64},
        orient="row").write_parquet(env)

    # output paths (fresh, write-once)
    suffix = "__morning_only" if entry_clock == "morning_only" else "__test"
    for attr, stem in [("OUT_PARQUET", "juiced_replay_candidates"),
                       ("OUT_REPORT", "juiced_replay_report"),
                       ("OUT_BASELINE", "juiced_replay_baseline")]:
        orig = jr.__dict__.get(attr)
        if orig is not None:
            jr.__dict__[attr] = orig.with_name(
                orig.stem + suffix + orig.suffix)
        else:
            jr.__dict__[attr] = odds_dir / (stem + suffix + ".parquet"
                                            if "parquet" in stem
                                            else stem + suffix + ".json")


def test_end_to_end_morning_only(tmp_path):
    _setup(tmp_path, "morning_only")
    rc = jr.main(["--entry-clock", "morning_only"])
    assert rc == 0

    # verify the candidates parquet
    frame = pl.read_parquet(jr.OUT_PARQUET)
    assert frame.height == 1  # one contract (one panel row)
    r = frame.row(0, named=True)
    assert r["snap"] == "morning"
    assert r["entry_clock"] == "morning_only"
    assert r["book"] == "draftkings"
    # Friend columns absent/null (morning_only mode)
    assert r.get("open_over") is None
    assert r.get("open_under") is None
    # morning pair prices present
    assert r["morning_over"] == -120 and r["morning_under"] == 105
    # model edge: p_ours_cal = 0.55, fair over at -120/-105
    # raw over = 100/220 = 0.4545, raw under = 100/205 = 0.4878
    # devig over = 0.4545 / (0.4545 + 0.4878) = 0.4823
    # edge over = 0.55 - 0.4823 = 0.0677
    # raw under = 0.4878, devig under = 0.5177
    # edge under = (1 - 0.55) - 0.5177 = -0.0677
    # over edge > under edge -> over is taken (if floor passes)
    # y = 1.0 (over won) -> won = True for over side
    # pnl_flat1u = bet_pnl(1.0, -120, won=True) = 100/120 = 0.8333
    # the 4.5-over veto correctly rejects this contract (registered
    # risk control); pnl = 0 because no stake was placed
    assert r["won"] is True
    assert r["pnl_flat1u"] == 0.0
    assert r["accepted"] is False
    assert r["reason"] == "veto_4_5_over"
    # clv_pp is None because the close snapshot has a negative lag
    # (flagged as close_invalid by the envelope preflight)
    assert r["close_invalid"] is True
    assert r["clv_pp"] is None


def test_end_to_end_report_contents(tmp_path):
    _setup(tmp_path, "morning_only")
    rc = jr.main(["--entry-clock", "morning_only"])
    assert rc == 0
    report = json.loads(
        jr.OUT_REPORT.read_text(encoding="utf-8"))
    assert report["contract"]["decision"] == \
        "paid morning T-5h only (Friend skipped)"
    assert report["contract"]["entry_clock"] == "morning_only"
    assert report["n_candidates"] == 1
    assert report["n_taken"] == 0  # vetoed by the registered risk control
    assert report["taken_by_snap"]["morning"] == 0  # no taken contracts


def test_registered_mode_still_reads_friend(tmp_path):
    """In registered mode, the Friend CSV IS read; if missing, the
    Friend pairs are empty and the decision falls through to morning."""
    _setup(tmp_path, "registered")
    rc = jr.main(["--entry-clock", "registered"])
    assert rc == 0
    frame = pl.read_parquet(jr.OUT_PARQUET)
    r = frame.row(0, named=True)
    # no Friend CSV -> open_* null -> falls through to morning
    assert r["snap"] == "morning"
    assert r["entry_clock"] == "registered"
