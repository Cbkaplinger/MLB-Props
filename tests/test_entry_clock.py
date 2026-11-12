"""End-to-end synthetic tests for the market-only paid T-5h replay
(entry_clock=morning_only) in juiced_replay_ledger.py.

Covers the assigned acceptance matrix:
- market-only path bypasses model probability / policy / sizing
- full identity guards: duplicate quote sides and ambiguous
  reduced-key joins are refused, never resolved with first()
- authoritative vendor timestamps for morning and close; missing or
  post-commence timing is an explicit unavailable/refusal state
- separated entry / settlement / close-benchmark states with
  independent report denominators
- calendar-date validation (2025-02-30 refused, not just shape)
- registered (canonical) mode still reads the Friend fixture

NO private lake reads, NO network, NO canonical overwrites.
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from production.ops.market_research import (
    juiced_replay_ledger as jr,
)

GD = "2025-04-10"
LINE = 4.5


def _book_lines_rows(extra=None):
    """Two-sided morning + close quotes for 2 books per event.

    evt001: full morning+close, valid envelope timing both snapshots
    evt002: morning+close quotes, envelope morning only (close timing
            unavailable)
    evt003: morning+close quotes, close envelope POST-commence
            (lag < 0 -> close_invalid_vendor)
    evt004: morning quotes only (no close snapshot at all)
    evt005: morning+close quotes, morning vendor timestamp at T-1h
            (lag 3600 < 18000): pregame but NOT available at the
            declared T-5h decision -> entry_timing_after_decision
    """
    rows = []
    for evt, pk, snaps in (("evt001", "aa p", ("morning", "close")),
                           ("evt002", "bb p", ("morning", "close")),
                           ("evt003", "cc p", ("morning", "close")),
                           ("evt004", "dd p", ("morning",)),
                           ("evt005", "ee p", ("morning", "close"))):
        for snap in snaps:
            for book in ("draftkings", "fanduel"):
                for side, price in (("over", -120), ("under", 105)):
                    rows.append({
                        "event_id": evt, "snapshot": snap,
                        "snapshot_ts": f"{GD}T18:55:00Z"
                        if snap == "close" else f"{GD}T14:00:00Z",
                        "game_date": GD, "season_type": "regular",
                        "book": book, "market": "pitcher_strikeouts",
                        "player": pk.upper(),
                        "player_norm": pk,                        "line": LINE, "side": side, "price": price,
                    })
    if extra:
        rows.extend(extra)
    return rows


def _panel_rows():
    """One settled row per event. evt002 has NO model probability."""
    return [
        {"gd": GD, "key": "aa p", "line": LINE, "p_ours_cal": 0.55,
         "y": 1.0, "p_book_close": 0.50, "player_name": "P A"},
        {"gd": GD, "key": "bb p", "line": LINE, "p_ours_cal": None,
         "y": 0.0, "p_book_close": 0.50, "player_name": "P B"},
        {"gd": GD, "key": "cc p", "line": LINE, "p_ours_cal": 0.50,
         "y": 1.0, "p_book_close": 0.50, "player_name": "P C"},
        {"gd": GD, "key": "dd p", "line": LINE, "p_ours_cal": 0.50,
         "y": 0.0, "p_book_close": 0.50, "player_name": "P D"},
        {"gd": GD, "key": "ee p", "line": LINE, "p_ours_cal": 0.50,
         "y": 1.0, "p_book_close": 0.50, "player_name": "P E"},
    ]


def _envelope_rows():
    # lag = commence - vendor; positive = vendor BEFORE commence (valid)
    return [
        {"event_id": "evt001", "snapshot": "morning",
         "vendor_timestamp": f"{GD}T14:00:00Z",
         "reconstructed_ts": f"{GD}T14:00:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 32400},
        {"event_id": "evt001", "snapshot": "close",
         "vendor_timestamp": f"{GD}T22:55:00Z",
         "reconstructed_ts": f"{GD}T22:55:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 300},
        {"event_id": "evt002", "snapshot": "morning",
         "vendor_timestamp": f"{GD}T14:00:00Z",
         "reconstructed_ts": f"{GD}T14:00:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 32400},
        {"event_id": "evt003", "snapshot": "morning",
         "vendor_timestamp": f"{GD}T14:00:00Z",
         "reconstructed_ts": f"{GD}T14:00:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 32400},
        {"event_id": "evt003", "snapshot": "close",
         "vendor_timestamp": f"{GD}T23:05:00Z",
         "reconstructed_ts": f"{GD}T22:55:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": -300},
        {"event_id": "evt004", "snapshot": "morning",
         "vendor_timestamp": f"{GD}T14:00:00Z",
         "reconstructed_ts": f"{GD}T14:00:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 32400},
        # evt005: vendor morning quote stamped T-1h before commence
        {"event_id": "evt005", "snapshot": "morning",
         "vendor_timestamp": f"{GD}T22:00:00Z",
         "reconstructed_ts": f"{GD}T18:00:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 3600},
    ]


FRIEND_CSV = "game_date,player_name,line,bookmaker,over_odds,under_odds\n"


def _setup(tmp_path: Path, extra_book_rows=None, friend_csv=None,
           extra_events=None, with_envelope=True):
    """Create all synthetic inputs in tmp_path and patch constants."""
    hist = tmp_path / "hist"
    hist.mkdir(parents=True)
    jr.__dict__["HIST"] = hist
    odds_dir = tmp_path / "odds_log"
    odds_dir.mkdir(parents=True)
    jr.__dict__["ODDS_DIR"] = odds_dir
    jr.__dict__["PANEL"] = odds_dir / "universe_panel_live.parquet"
    # cached event-date map (must EXIST; market-only refuses a rebuild)
    evmap = hist / "event_date_map.json"
    jr.__dict__["EVENT_DATE_MAP"] = hist / "event_date_map.json"
    # Friend fixture (registered mode reads it; morning_only must not)
    friend = tmp_path / "friend.csv"
    friend.write_text(friend_csv if friend_csv is not None
                      else FRIEND_CSV, encoding="utf-8")
    jr.__dict__["FRIEND"] = friend

    events = {"evt001": GD, "evt002": GD, "evt003": GD, "evt004": GD,
              "evt005": GD}
    if extra_events:
        events.update(extra_events)
    jr.__dict__["load_event_date_map"] = lambda: dict(events)
    # the cached map file must physically exist (no rebuild authorized)
    evmap.write_text(json.dumps(events), encoding="utf-8")

    pl.DataFrame(_book_lines_rows(extra_book_rows), schema={
        "event_id": pl.Utf8, "snapshot": pl.Utf8, "snapshot_ts": pl.Utf8,
        "game_date": pl.Utf8, "season_type": pl.Utf8, "book": pl.Utf8,
        "market": pl.Utf8, "player": pl.Utf8, "player_norm": pl.Utf8,
        "line": pl.Float64, "side": pl.Utf8, "price": pl.Int64},
        orient="row").write_parquet(hist / "book_lines_pitcher.parquet")

    pl.DataFrame(_panel_rows(), schema={
        "gd": pl.Utf8, "key": pl.Utf8, "line": pl.Float64,
        "p_ours_cal": pl.Float64, "y": pl.Float64,
        "p_book_close": pl.Float64, "player_name": pl.Utf8},
        orient="row").write_parquet(jr.PANEL)

    pl.DataFrame(_envelope_rows(), schema={
        "event_id": pl.Utf8, "snapshot": pl.Utf8,
        "vendor_timestamp": pl.Utf8, "reconstructed_ts": pl.Utf8,
        "commence_time": pl.Utf8,
        "lag_vendor_vs_commence_sec": pl.Int64},
        orient="row").write_parquet(hist / "snapshot_envelope.parquet") \
        if with_envelope else None

    jr.__dict__["OUT_PARQUET"] = odds_dir / "juiced_replay_candidates__t.parquet"
    jr.__dict__["OUT_REPORT"] = odds_dir / "juiced_replay_report__t.json"
    jr.__dict__["OUT_BASELINE"] = odds_dir / "juiced_replay_baseline__t.parquet"
    return friend


def test_market_only_end_to_end(tmp_path):
    _setup(tmp_path)
    rc = jr.main(["--entry-clock", "morning_only"])
    assert rc == 0

    base = pl.read_parquet(jr.OUT_BASELINE)
    assert base.height == 5
    by_key = {r["key"]: r for r in base.iter_rows(named=True)}
    # evt002: missing model probability is NOT a barrier in market-only
    assert by_key["bb p"]["has_model_probability"] is None
    assert by_key["bb p"]["entry_eligible"] is True
    # evt003: close vendor quote post-commence -> explicit refusal
    assert by_key["cc p"]["close_reason"] == "close_invalid_vendor"
    assert by_key["cc p"]["close_benchmark_available"] is False
    # evt004: valid entry, no close snapshot
    assert by_key["dd p"]["entry_eligible"] is True
    assert by_key["dd p"]["close_reason"] == "no_two_way_close"
    assert by_key["dd p"]["close_benchmark_available"] is False
    # evt005: T-1h vendor quote is pregame but NOT available at the
    # declared T-5h decision -> explicit refusal
    assert by_key["ee p"]["entry_eligible"] is False
    assert by_key["ee p"]["entry_reason"] == "entry_timing_after_decision"
    # evt001: fully available; movement from canonical de-vig
    # -120 -> 120/220 = 0.5455 implied; +105 -> 100/205 = 0.4878
    # fair over = 0.5455 / (0.5455 + 0.4878) = 0.5279
    r = by_key["aa p"]
    assert r["entry_eligible"] is True
    assert r["settlement_available"] is True
    assert r["close_benchmark_available"] is True
    assert abs(r["fair_over_entry"] - 0.5278969957) < 1e-6
    assert abs(r["movement_pp"]) < 1e-9  # identical entry/close prices
    assert r["snap"] == "morning"
    assert r["entry_clock"] == "morning_only"


def test_market_only_report_denominators(tmp_path):
    _setup(tmp_path)
    rc = jr.main(["--entry-clock", "morning_only"])
    assert rc == 0
    rep = json.loads(jr.OUT_REPORT.read_text(encoding="utf-8"))
    c = rep["contract"]
    assert c["mode"] == "market_only"
    assert c["model"] == "bypassed (p_ours_cal not required)"
    assert c["policy"] == "bypassed (no floors/veto/probation filter)"
    assert c["sizing"] == "bypassed (no Kelly/edge-band execution)"
    assert c["vendor_timing_enforced"] is True
    # legacy model sections are absent from a market-only report
    for legacy in ("all", "y2025", "y2026_confirmatory", "n_taken",
                   "probation_2_5_3_5", "taken_by_book"):
        assert legacy not in rep
    d = rep["baseline_market_only"]
    assert d["n_baseline_rows"] == 5
    # independent denominators
    assert d["entry"]["denominator"] == 5
    assert d["entry"]["n_eligible"] == 4
    assert d["entry"]["reason_counts"]["entry_timing_after_decision"] == 1
    assert d["settlement"]["denominator"] == 5
    assert d["settlement"]["n_available"] == 5
    # close benchmark is assessed over the entry-eligible population
    assert d["close_benchmark"]["denominator"] == 4
    assert d["close_benchmark"]["n_available"] == 1  # evt001 only
    assert d["close_benchmark"]["reason_counts"] == {
        "available": 1, "no_two_way_close": 1,
        "close_invalid_vendor": 1, "close_timing_unavailable": 2}
    # model probability was never accessed in market-only mode
    assert d["has_model_probability_share"] is None
    mv = rep["market_movement"]
    assert mv["n"] == 1 and mv["denominator"] == 4
    assert rep["contract"]["units"]["movement_pp"].startswith(
        "percentage points")


def test_entry_timing_after_decision_refused(tmp_path):
    _setup(tmp_path)
    jr.main(["--entry-clock", "morning_only"])
    base = pl.read_parquet(jr.OUT_BASELINE)
    r = {x["key"]: x for x in base.iter_rows(named=True)}["ee p"]
    assert r["entry_reason"] == "entry_timing_after_decision"
    assert r["entry_eligible"] is False
    assert r["movement_pp"] is None


def test_market_only_fails_closed_without_envelope(tmp_path):
    _setup(tmp_path, with_envelope=False)
    with pytest.raises(SystemExit, match="fail closed"):
        jr.main(["--entry-clock", "morning_only"])


def test_market_only_refuses_2026_window(tmp_path):
    _setup(tmp_path)
    with pytest.raises(SystemExit, match="2026 rows stay closed"):
        jr.main(["--entry-clock", "morning_only",
                 "--gd-start", "2025-01-01", "--gd-end", "2026-06-30",
                 "--out-suffix", "__x"])


def test_market_only_refuses_missing_event_map(tmp_path):
    _setup(tmp_path)
    (tmp_path / "hist" / "event_date_map.json").unlink()
    with pytest.raises(SystemExit, match="event-date map"):
        jr.main(["--entry-clock", "morning_only"])


def test_close_timing_unavailable_state(tmp_path):
    _setup(tmp_path)
    jr.main(["--entry-clock", "morning_only"])
    base = pl.read_parquet(jr.OUT_BASELINE)
    r = {x["key"]: x for x in base.iter_rows(named=True)}["bb p"]
    # close quotes exist but the envelope has no close row for evt002:
    # explicit unavailable, never implicit validity
    assert r["close_reason"] == "close_timing_unavailable"
    assert r["close_benchmark_available"] is False
    assert r["movement_pp"] is None


def test_registered_mode_reads_friend_fixture(tmp_path):
    # player_name "Aa P" normalizes through sorted_key to "aa p", the
    # panel key of evt001, so the Friend open wins the registered clock
    friend = _setup(tmp_path, friend_csv=(
        FRIEND_CSV + f"{GD},Aa P,{LINE},draftkings,-115,102\n"))
    jr.__dict__["_two_way_friend"] = jr._two_way_friend  # real reader
    rc = jr.main(["--entry-clock", "registered"])
    assert rc == 0
    frame = pl.read_parquet(jr.OUT_PARQUET)
    # Friend open pair wins the registered decision clock for its key
    z = [r for r in frame.iter_rows(named=True) if r["key"] == "aa p"]
    assert z and z[0]["snap"] == "open"
    assert z[0]["book"] == "draftkings"
    assert z[0]["open_over"] == -115 and z[0]["open_under"] == 102
    assert friend.exists()


def test_morning_only_never_touches_friend(tmp_path):
    _setup(tmp_path)
    def _spy(*a, **k):  # raising spy
        raise AssertionError("Friend CSV accessed in morning_only mode")
    jr.__dict__["_two_way_friend"] = _spy
    rc = jr.main(["--entry-clock", "morning_only"])
    assert rc == 0  # spy never fired


def test_duplicate_quote_sides_refused(tmp_path):
    dup = {"event_id": "evt001", "snapshot": "morning",
           "snapshot_ts": f"{GD}T14:00:00Z", "game_date": GD,
           "season_type": "regular", "book": "draftkings",
           "market": "pitcher_strikeouts", "player": "P A",
           "player_norm": "aa p", "line": LINE, "side": "over",
           "price": -120}
    _setup(tmp_path, extra_book_rows=[dup])
    with pytest.raises(SystemExit, match="duplicate over-side"):
        jr.main(["--entry-clock", "morning_only"])


def test_ambiguous_reduced_key_refused(tmp_path):
    # second event_id mapping to the same (gd, key, line): the reduced
    # join key is ambiguous -> refuse, do NOT resolve with first()
    amb = {"event_id": "evt001b", "snapshot": "morning",
           "snapshot_ts": f"{GD}T14:00:00Z", "game_date": GD,
           "season_type": "regular", "book": "draftkings",
           "market": "pitcher_strikeouts", "player": "P A",
           "player_norm": "aa p", "line": LINE, "side": "over",
           "price": -130}
    _setup(tmp_path, extra_book_rows=[amb],
           extra_events={"evt001b": GD})
    with pytest.raises(SystemExit, match="ambiguous reduced-key"):
        jr.main(["--entry-clock", "morning_only"])


def test_calendar_date_validation(tmp_path):
    _setup(tmp_path)
    with pytest.raises(SystemExit, match="valid YYYY-MM-DD"):
        jr.main(["--entry-clock", "morning_only",
                 "--gd-start", "2025-02-30", "--gd-end", "2025-06-30",
                 "--out-suffix", "__cal"])


def test_main_entry_restricted_command(tmp_path):
    """The intended development command end to end: paid-only
    T-5h market-only replay inside a 2025H1 development window."""
    _setup(tmp_path)
    rc = jr.main([
        "--entry-clock", "morning_only",
        "--gd-start", "2025-01-01", "--gd-end", "2025-06-30",
        "--out-suffix", "__dev2025H1",
    ])
    assert rc == 0
    out_rep = jr.OUT_REPORT.with_name(
        jr.OUT_REPORT.stem + "__dev2025H1" + jr.OUT_REPORT.suffix)
    rep = json.loads(out_rep.read_text(encoding="utf-8"))
    assert rep["contract"]["gd_window"] == \
        "2025-01-01..2025-06-30 (confirm_2025H2 excluded pre-decode)"
    assert rep["n_candidates"] == 5
    # gd window excludes nothing here (all events are 2025-04-10)
    base = pl.read_parquet(jr.OUT_BASELINE.with_name(
        jr.OUT_BASELINE.stem + "__dev2025H1" + jr.OUT_BASELINE.suffix))
    assert base.height == 5
