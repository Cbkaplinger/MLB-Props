"""Synthetic acceptance tests for the opt-in close-conflict
drop-and-count policy (--quote-policy drop_close_conflicts).

Drives the production entry point (jr.main) with:
- both conflicting prices removed (drop-and-count, no price choice);
- a conflict on one side leaves no fake pair;
- a clean DK/FD closing pair remains selectable with UNCHANGED metrics;
- fallback changes only under the declared book preference;
- no valid close leaves a valid morning entry with CLV unavailable;
- morning conflicts still refuse (morning integrity NOT relaxed);
- distinct_time / insufficient_timestamp still refuse;
- four-key identity exclusions remain intact;
- conflict-signature mismatch refuses.

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
FAIR_OVER = 0.5278969957081545  # devig(-120, 105)
TS = f"{GD}T14:00:00Z"
FRIEND_CSV = "game_date,player_name,line,bookmaker,over_odds,under_odds\n"


def _bl(evt, snap, book, side, price, ts=TS, pnorm="aa p"):
    return {
        "event_id": evt, "snapshot": snap, "snapshot_ts": ts,
        "game_date": GD, "season_type": "regular", "book": book,
        "market": "pitcher_strikeouts", "player": pnorm.upper(),
        "player_norm": pnorm, "line": LINE, "side": side,
        "price": price,
    }


def _clean_rows(conflicted_book=None):
    """One clean candidate on DK/FD (+ optional third book); if
    conflicted_book is set, its CLOSE over side carries a same-time
    two-price conflict."""
    rows = []
    for snap in ("morning", "close"):
        for book in ("draftkings", "fanduel", "betmgm"):
            for side, price in (("over", -120), ("under", 105)):
                rows.append(_bl("evt1", snap, book, side, price))
    if conflicted_book:
        rows.append(_bl("evt1", "close", conflicted_book, "over", -130))
    return rows


def _panel_rows():
    return [{"gd": GD, "key": "aa p", "line": LINE, "p_ours_cal": 0.55,
             "y": 1.0, "p_book_close": 0.50, "player_name": "Aa P"}]


def _envelope_rows():
    return [
        {"event_id": "evt1", "snapshot": "morning",
         "vendor_timestamp": f"{GD}T14:00:00Z",
         "reconstructed_ts": f"{GD}T14:00:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 32400},
        {"event_id": "evt1", "snapshot": "close",
         "vendor_timestamp": f"{GD}T22:55:00Z",
         "reconstructed_ts": f"{GD}T22:55:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 300},
    ]


def _setup(tmp_path, rows, panel_rows=None):
    hist = tmp_path / "hist"
    hist.mkdir(parents=True)
    jr.__dict__["HIST"] = hist
    odds_dir = tmp_path / "odds_log"
    odds_dir.mkdir(parents=True)
    jr.__dict__["ODDS_DIR"] = odds_dir
    jr.__dict__["PANEL"] = odds_dir / "universe_panel_live.parquet"
    evmap = hist / "event_date_map.json"
    jr.__dict__["EVENT_DATE_MAP"] = evmap
    evmap.write_text(json.dumps({"evt1": GD}), encoding="utf-8")
    jr.__dict__["load_event_date_map"] = lambda: {"evt1": GD}
    friend = tmp_path / "friend.csv"
    friend.write_text(FRIEND_CSV, encoding="utf-8")
    jr.__dict__["FRIEND"] = friend
    pl.DataFrame(rows, schema={
        "event_id": pl.Utf8, "snapshot": pl.Utf8, "snapshot_ts": pl.Utf8,
        "game_date": pl.Utf8, "season_type": pl.Utf8, "book": pl.Utf8,
        "market": pl.Utf8, "player": pl.Utf8, "player_norm": pl.Utf8,
        "line": pl.Float64, "side": pl.Utf8, "price": pl.Int64},
        orient="row").write_parquet(
        hist / "book_lines_pitcher.parquet")
    pl.DataFrame(panel_rows or _panel_rows(), schema={
        "gd": pl.Utf8, "key": pl.Utf8, "line": pl.Float64,
        "p_ours_cal": pl.Float64, "y": pl.Float64,
        "p_book_close": pl.Float64, "player_name": pl.Utf8},
        orient="row").write_parquet(jr.PANEL)
    pl.DataFrame(_envelope_rows(), schema={
        "event_id": pl.Utf8, "snapshot": pl.Utf8,
        "vendor_timestamp": pl.Utf8, "reconstructed_ts": pl.Utf8,
        "commence_time": pl.Utf8,
        "lag_vendor_vs_commence_sec": pl.Int64},
        orient="row").write_parquet(hist / "snapshot_envelope.parquet")
    jr.__dict__["OUT_PARQUET"] = odds_dir / "cand__t.parquet"
    jr.__dict__["OUT_REPORT"] = odds_dir / "rep__t.json"
    jr.__dict__["OUT_BASELINE"] = odds_dir / "base__t.parquet"
    jr.__dict__["OUT_INTEGRITY"] = odds_dir / "integrity__t.json"


def _integ():
    p = jr.OUT_INTEGRITY
    return p.with_name(p.stem + "__drop_close_conflicts" + p.suffix)


def _binding(tmp_path, groups):
    p = tmp_path / "conf_binding.json"
    p.write_text(json.dumps({"expected_conflicting_groups": groups}),
                 encoding="utf-8")
    return p


def _drop_args(binding):
    return ["--entry-clock", "morning_only",
            "--identity-policy", "exclude_ambiguous",
            "--quote-policy", "drop_close_conflicts",
            "--expected-close-conflicts", str(binding)]


def _conflict_group(snapshot="close", book="draftkings",
                    side="over", prices=(-120, -130)):
    return {"gd": GD, "key": "aa p", "line": LINE, "book": book,
            "event_id": "evt1", "side": side,
            "prices": [float(prices[0]), float(prices[1])]}


DROP = ["--entry-clock", "morning_only",
        "--identity-policy", "exclude_ambiguous",
        "--quote-policy", "drop_close_conflicts"]


def test_both_conflicting_prices_removed_pair_survives_on_fd(tmp_path):
    # DK close over is conflicted: BOTH rows removed (no price choice);
    # the FD close pair survives and the benchmark uses it
    _setup(tmp_path, _clean_rows(conflicted_book="draftkings"))
    b = _binding(tmp_path, [_conflict_group(book="draftkings")])
    assert jr.main(_drop_args(b)) == 0
    base = pl.read_parquet(jr.OUT_BASELINE)
    r = {x["key"]: x for x in base.iter_rows(named=True)}["aa p"]
    assert r["close_benchmark_available"] is True
    # no fake pair: the surviving close pair is FD (DK over is gone)
    rep = json.loads(_integ().read_text(encoding="utf-8"))
    acc = rep["close_conflict_removal"]
    assert acc["conflicting_side_groups"] == 1
    assert acc["removed_observations"] == 2  # BOTH prices removed
    assert acc["implicated_source_rows"] == 2
    entry = acc["changed_or_lost_closing_selections"][0]
    assert entry["surviving_pref_best_book"] == "fanduel"
    assert r["entry_eligible"] is True
    assert abs(r["fair_over_entry"] - FAIR_OVER) < 1e-9


def test_conflict_one_side_leaves_no_fake_pair(tmp_path):
    # close quotes exist ONLY at DK (conflicted over): after removing
    # BOTH conflicting over rows, the single DK under must NOT become a
    # pair -> the morning entry stays valid with CLV unavailable
    rows = [r for r in _clean_rows() if r["snapshot"] == "morning"
            or r["book"] == "draftkings"]
    rows.append(_bl("evt1", "close", "draftkings", "over", -130))
    _setup(tmp_path, rows)
    b = _binding(tmp_path, [_conflict_group(book="draftkings")])
    assert jr.main(_drop_args(b)) == 0
    base = pl.read_parquet(jr.OUT_BASELINE)
    r = {x["key"]: x for x in base.iter_rows(named=True)}["aa p"]
    assert r["close_benchmark_available"] is False
    assert r["close_reason"] == "no_two_way_close"
    assert r["movement_pp"] is None
    # morning entry eligibility is INDEPENDENT and retained
    assert r["entry_eligible"] is True
    rep = json.loads(_integ().read_text(encoding="utf-8"))
    acc = rep["close_conflict_removal"]
    assert acc["entries_losing_close_benchmark_count"] == 1
    assert acc["changed_or_lost_closing_selections"][0][
        "selection_change_status"] == "closing_benchmark_lost"


def test_clean_dk_fd_pair_unchanged(tmp_path):
    # no conflicts at all: unique-contract outputs identical to the
    # default-policy run
    _setup(tmp_path, _clean_rows())
    assert jr.main(_drop_args(_binding(tmp_path, []))) == 0
    base = pl.read_parquet(jr.OUT_BASELINE)
    r = {x["key"]: x for x in base.iter_rows(named=True)}["aa p"]
    assert abs(r["fair_over_entry"] - FAIR_OVER) < 1e-9
    assert r["close_benchmark_available"] is True
    assert r["book"] == "draftkings"  # pref-best DK/FD pair unchanged


def test_fallback_changes_only_under_declared_preference(tmp_path):
    # conflict on betmgm (pref rank 2, AFTER DK/FD): the DK/FD pref-best
    # selection is untouched; betmgm's conflicted rows are removed
    _setup(tmp_path, _clean_rows(conflicted_book="betmgm"))
    b = _binding(tmp_path, [_conflict_group(book="betmgm")])
    assert jr.main(_drop_args(b)) == 0
    base = pl.read_parquet(jr.OUT_BASELINE)
    r = {x["key"]: x for x in base.iter_rows(named=True)}["aa p"]
    assert r["close_benchmark_available"] is True
    assert r["book"] == "draftkings"
    rep = json.loads(_integ().read_text(encoding="utf-8"))
    entry = rep["close_conflict_removal"][
        "changed_or_lost_closing_selections"][0]
    assert entry["removed_books"] == ["betmgm"]
    assert entry["surviving_pref_best_book"] == "draftkings"


def test_morning_conflicts_still_refuse(tmp_path):
    # a MORNING same_time_conflict is NOT relaxed by the drop policy
    rows = _clean_rows()
    rows.append(_bl("evt1", "morning", "draftkings", "over", -130))
    _setup(tmp_path, rows)
    b = _binding(tmp_path, [_conflict_group(book="draftkings")])
    with pytest.raises(SystemExit, match="quote integrity failure"):
        jr.main(_drop_args(b))


def test_distinct_time_still_refuses(tmp_path):
    rows = _clean_rows() + [
        _bl("evt1", "close", "betmgm", "over", -120,
            ts=f"{GD}T13:00:00Z")]
    _setup(tmp_path, rows)
    b = _binding(tmp_path, [])
    with pytest.raises(SystemExit, match="quote integrity failure"):
        jr.main(_drop_args(b))


def test_insufficient_timestamp_still_refuses(tmp_path):
    rows = [r for r in _clean_rows()
            if not (r["snapshot"] == "close"
                    and r["book"] == "betmgm" and r["side"] == "over")]
    rows += [_bl("evt1", "close", "betmgm", "over", -120, ts=None),
             _bl("evt1", "close", "betmgm", "over", -120, ts=None)]
    _setup(tmp_path, rows)
    b = _binding(tmp_path, [])
    with pytest.raises(SystemExit, match="quote integrity failure"):
        jr.main(_drop_args(b))


def test_signature_mismatch_refuses(tmp_path):
    _setup(tmp_path, _clean_rows(conflicted_book="draftkings"))
    wrong = _conflict_group(book="fanduel")  # different book
    b = _binding(tmp_path, [wrong])
    with pytest.raises(SystemExit, match="close-conflict signature"):
        jr.main(_drop_args(b))


def test_default_policy_still_refuses_close_conflict(tmp_path):
    _setup(tmp_path, _clean_rows(conflicted_book="draftkings"))
    with pytest.raises(SystemExit, match="quote integrity failure"):
        jr.main(["--entry-clock", "morning_only"])


def test_four_key_exclusions_remain_intact(tmp_path):
    # a second, ambiguous candidate is EXCLUDED while the conflicted
    # close book is dropped: both declared policies coexist
    rows = _clean_rows(conflicted_book="draftkings")
    rows += [_bl("evt2", "morning", "draftkings", "over", -120,
                 pnorm="bb p"),
             _bl("evt2", "morning", "draftkings", "under", 105,
                 pnorm="bb p"),
             _bl("evt2b", "morning", "draftkings", "over", -120,
                 pnorm="bb p"),
             _bl("evt2b", "morning", "draftkings", "under", 105,
                 pnorm="bb p")]
    panel = _panel_rows() + [
        {"gd": GD, "key": "bb p", "line": LINE, "p_ours_cal": 0.50,
         "y": 1.0, "p_book_close": 0.50, "player_name": "Bb P"}]
    _setup(tmp_path, rows, panel_rows=panel)
    jr.__dict__["load_event_date_map"] = lambda: {
        "evt1": GD, "evt2": GD, "evt2b": GD}
    (tmp_path / "hist" / "event_date_map.json").write_text(
        json.dumps({"evt1": GD, "evt2": GD, "evt2b": GD}),
        encoding="utf-8")
    exb = tmp_path / "ex_binding.json"
    ex_dict = {"expected_excluded_keys": [
        {"gd": GD, "key": "bb p", "line": LINE}]}
    ex_binding = tmp_path / "ex_binding.json"
    ex_binding.write_text(json.dumps(ex_dict), encoding="utf-8")
    b = _binding(tmp_path, [_conflict_group(book="draftkings")])
    rc = jr.main(_drop_args(b) + ["--expected-excluded-keys",
                                  str(ex_binding)])
    assert rc == 0
    base = pl.read_parquet(jr.OUT_BASELINE)
    by_key = {x["key"]: x for x in base.iter_rows(named=True)}
    assert by_key["bb p"]["entry_reason"] == "ambiguous_event_identity"
    assert by_key["bb p"]["entry_eligible"] is False
    assert abs(by_key["aa p"]["fair_over_entry"] - FAIR_OVER) < 1e-9
