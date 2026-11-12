"""Synthetic tests for the declared ambiguous-identity exclusion policy
(--identity-policy exclude_ambiguous) in juiced_replay_ledger.py.

Scenarios (main() end to end on small fixtures):
1. default refusal remains (no policy -> ambiguous identity stops run)
2. opt-in excludes unresolved identities (never resolves them)
3. unambiguous candidates and metrics unchanged
4. ambiguity present only at morning, or only at close -> excluded
   either way; no re-entry through the other snapshot
5. no book-selection step can hide the ambiguity (both events carry
   multiple books; exclusion is determined pre-selection)
6. unexpected exclusion-set mismatch (binding) refuses
7. excluded candidates remain in coverage accounting

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
FRIEND_CSV = "game_date,player_name,line,bookmaker,over_odds,under_odds\n"

# clean + morning-ambiguous + close-ambiguous reduced identities
EVT_CLEAN = "evt1"
EVT_MORNING_A, EVT_MORNING_B = "evt2", "evt2b"
EVT_CLOSE_A, EVT_CLOSE_B = "evt3", "evt3b"


def _book_lines_rows():
    rows = []
    # clean candidate: morning+close quotes, one event
    for snap in ("morning", "close"):
        for book in ("draftkings", "fanduel"):
            for side, price in (("over", -120), ("under", 105)):
                rows.append(_bl(EVT_CLEAN, "aa p", snap, book, side, price))
    # morning-ambiguous: TWO events carry morning quotes (both with
    # two books); only evtA carries the close snapshot
    for evt in (EVT_MORNING_A, EVT_MORNING_B):
        for book in ("draftkings", "fanduel"):
            for side, price in (("over", -110), ("under", 100)):
                rows.append(_bl(evt, "bb p", "morning", book, side, price))
    for book in ("draftkings", "fanduel"):
        for side, price in (("over", -120), ("under", 105)):
            rows.append(_bl(EVT_MORNING_A, "bb p", "close", book,
                            side, price))
    # close-ambiguous: TWO events carry close quotes; only evtA has
    # the morning snapshot
    for book in ("draftkings", "fanduel"):
        for side, price in (("over", -120), ("under", 105)):
            rows.append(_bl(EVT_CLOSE_A, "cc p", "morning", book,
                            side, price))
    for evt in (EVT_CLOSE_A, EVT_CLOSE_B):
        for book in ("draftkings", "fanduel"):
            for side, price in (("over", -115), ("under", 102)):
                rows.append(_bl(evt, "cc p", "close", book, side, price))
    return rows


def _bl(evt, key, snap, book, side, price):
    return {
        "event_id": evt, "snapshot": snap,
        "snapshot_ts": f"{GD}T18:55:00Z" if snap == "close"
        else f"{GD}T14:00:00Z",
        "game_date": GD, "season_type": "regular", "book": book,
        "market": "pitcher_strikeouts", "player": key.upper(),
        "player_norm": key, "line": LINE, "side": side, "price": price,
    }


def _panel_rows():
    return [
        {"gd": GD, "key": "aa p", "line": LINE, "p_ours_cal": 0.55,
         "y": 1.0, "p_book_close": 0.50, "player_name": "Aa P"},
        {"gd": GD, "key": "bb p", "line": LINE, "p_ours_cal": 0.50,
         "y": 0.0, "p_book_close": 0.50, "player_name": "Bb P"},
        {"gd": GD, "key": "cc p", "line": LINE, "p_ours_cal": 0.50,
         "y": 1.0, "p_book_close": 0.50, "player_name": "Cc P"},
    ]


def _envelope_rows():
    return [
        {"event_id": EVT_CLEAN, "snapshot": "morning",
         "vendor_timestamp": f"{GD}T14:00:00Z",
         "reconstructed_ts": f"{GD}T14:00:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 32400},
        {"event_id": EVT_CLEAN, "snapshot": "close",
         "vendor_timestamp": f"{GD}T22:55:00Z",
         "reconstructed_ts": f"{GD}T22:55:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 300},
        {"event_id": EVT_MORNING_A, "snapshot": "morning",
         "vendor_timestamp": f"{GD}T14:00:00Z",
         "reconstructed_ts": f"{GD}T14:00:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 32400},
        {"event_id": EVT_MORNING_A, "snapshot": "close",
         "vendor_timestamp": f"{GD}T22:55:00Z",
         "reconstructed_ts": f"{GD}T22:55:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 300},
        {"event_id": EVT_MORNING_B, "snapshot": "morning",
         "vendor_timestamp": f"{GD}T14:00:00Z",
         "reconstructed_ts": f"{GD}T14:00:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 32400},
        {"event_id": EVT_CLOSE_A, "snapshot": "morning",
         "vendor_timestamp": f"{GD}T14:00:00Z",
         "reconstructed_ts": f"{GD}T14:00:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 32400},
        {"event_id": EVT_CLOSE_A, "snapshot": "close",
         "vendor_timestamp": f"{GD}T22:55:00Z",
         "reconstructed_ts": f"{GD}T22:55:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 300},
        {"event_id": EVT_CLOSE_B, "snapshot": "close",
         "vendor_timestamp": f"{GD}T22:55:00Z",
         "reconstructed_ts": f"{GD}T22:55:00Z",
         "commence_time": f"{GD}T23:00:00Z",
         "lag_vendor_vs_commence_sec": 300},
    ]


EVENTS = {
    EVT_CLEAN: GD, EVT_MORNING_A: GD, EVT_MORNING_B: GD,
    EVT_CLOSE_A: GD, EVT_CLOSE_B: GD,
}


def _setup(tmp_path: Path, binding_keys=None):
    hist = tmp_path / "hist"
    hist.mkdir(parents=True)
    jr.__dict__["HIST"] = hist
    odds_dir = tmp_path / "odds_log"
    odds_dir.mkdir(parents=True)
    jr.__dict__["ODDS_DIR"] = odds_dir
    jr.__dict__["PANEL"] = odds_dir / "universe_panel_live.parquet"
    evmap = hist / "event_date_map.json"
    jr.__dict__["EVENT_DATE_MAP"] = evmap
    evmap.write_text(json.dumps(EVENTS), encoding="utf-8")
    jr.__dict__["load_event_date_map"] = lambda: dict(EVENTS)
    friend = tmp_path / "friend.csv"
    friend.write_text(FRIEND_CSV, encoding="utf-8")
    jr.__dict__["FRIEND"] = friend

    pl.DataFrame(_book_lines_rows(), schema={
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
        orient="row").write_parquet(hist / "snapshot_envelope.parquet")

    jr.__dict__["OUT_PARQUET"] = odds_dir / "cand__t.parquet"
    jr.__dict__["OUT_REPORT"] = odds_dir / "rep__t.json"
    jr.__dict__["OUT_BASELINE"] = odds_dir / "base__t.parquet"

    binding = None
    if binding_keys is not None:
        binding = tmp_path / "binding.json"
        binding.write_text(json.dumps({
            "expected_excluded_keys": [
                {"gd": gd, "key": key, "line": line}
                for gd, key, line in binding_keys]}), encoding="utf-8")
    return binding


EXCLUDE_ARGS = ["--entry-clock", "morning_only",
                "--identity-policy", "exclude_ambiguous"]


def test_default_refusal_remains(tmp_path):
    _setup(tmp_path)
    with pytest.raises(SystemExit, match="ambiguous reduced-key"):
        jr.main(["--entry-clock", "morning_only"])


def test_optin_excludes_unresolved_identities(tmp_path):
    _setup(tmp_path)
    rc = jr.main(EXCLUDE_ARGS)
    assert rc == 0
    base = pl.read_parquet(jr.OUT_BASELINE)
    assert base.height == 3  # all candidates remain in accounting
    by_key = {r["key"]: r for r in base.iter_rows(named=True)}
    for k in ("aa p", "bb p", "cc p"):
        assert by_key[k]["baseline_reason"] in (
            "eligible", "ambiguous_event_identity")
    # morning-ambiguous candidate: excluded with both event_ids and
    # the affected snapshot; explicit eligibility status
    b = by_key["bb p"]
    assert b["entry_eligible"] is False
    assert b["entry_reason"] == "ambiguous_event_identity"
    assert sorted(b["conflicting_event_ids"].split(",")) == \
        sorted([EVT_MORNING_A, EVT_MORNING_B])
    assert b["affected_snapshots"] == "morning"
    # close-ambiguous candidate
    c = by_key["cc p"]
    assert c["entry_reason"] == "ambiguous_event_identity"
    assert sorted(c["conflicting_event_ids"].split(",")) == \
        sorted([EVT_CLOSE_A, EVT_CLOSE_B])
    assert c["affected_snapshots"] == "close"
    # excluded quote values do NOT persist
    assert b["entry_over"] is None and b["entry_under"] is None
    assert b["movement_pp"] is None
    assert c["over_hit"] is None and c["settlement_available"] is None


def test_unambiguous_candidates_unchanged(tmp_path):
    _setup(tmp_path)
    jr.main(EXCLUDE_ARGS)
    base = pl.read_parquet(jr.OUT_BASELINE)
    r = {x["key"]: x for x in base.iter_rows(named=True)}["aa p"]
    # canonical de-vig math untouched by the exclusion policy
    assert r["entry_eligible"] is True
    assert r["close_benchmark_available"] is True
    assert abs(r["fair_over_entry"] - 0.5278969957) < 1e-6
    assert abs(r["movement_pp"]) < 1e-9
    assert r["baseline_reason"] == "eligible"


def test_ambiguity_single_snapshot_no_reentry(tmp_path):
    _setup(tmp_path)
    jr.main(EXCLUDE_ARGS)
    base = pl.read_parquet(jr.OUT_BASELINE)
    by_key = {x["key"]: x for x in base.iter_rows(named=True)}
    # morning-only ambiguity still excludes (close quotes existed for
    # evtA but must not re-enter through the close path)
    assert by_key["bb p"]["entry_reason"] == "ambiguous_event_identity"
    assert by_key["bb p"]["affected_snapshots"] == "morning"
    assert by_key["bb p"]["close_reason"] == "not_assessed_excluded"
    # close-only ambiguity likewise
    assert by_key["cc p"]["entry_reason"] == "ambiguous_event_identity"
    assert by_key["cc p"]["affected_snapshots"] == "close"


def test_book_selection_cannot_hide_ambiguity(tmp_path):
    # both conflicting events carry quotes from the SAME preferred book
    # (draftkings): a pref-based first() would happily pick one event;
    # the exclusion policy must still exclude the candidate
    _setup(tmp_path)
    jr.main(EXCLUDE_ARGS)
    rep = json.loads(jr.OUT_REPORT.read_text(encoding="utf-8"))
    scr = rep["baseline_market_only"]["identity_screening"]
    by_key = {x["key"]: x for x in scr["excluded_keys"]}
    assert "bb p" in by_key and "cc p" in by_key
    # each excluded key lists BOTH event ids across the union
    assert len(by_key["bb p"]["event_ids"]) == 2
    assert len(by_key["cc p"]["event_ids"]) == 2


def test_binding_mismatch_refuses(tmp_path):
    # bind only ONE of the two detected ambiguous keys -> mismatch
    binding = _setup(tmp_path,
                     binding_keys=[(GD, "bb p", LINE)])
    with pytest.raises(SystemExit, match="exclusion-set mismatch"):
        jr.main(EXCLUDE_ARGS + ["--expected-excluded-keys", str(binding)])


def test_binding_match_passes(tmp_path):
    binding = _setup(tmp_path, binding_keys=[
        (GD, "bb p", LINE), (GD, "cc p", LINE)])
    rc = jr.main(EXCLUDE_ARGS + ["--expected-excluded-keys",
                                 str(binding)])
    assert rc == 0
    rep = json.loads(jr.OUT_REPORT.read_text(encoding="utf-8"))
    scr = rep["baseline_market_only"]["identity_screening"]
    assert scr["binding"]["matched"] is True
    assert scr["n_excluded_keys"] == 2


def test_excluded_candidates_in_coverage_accounting(tmp_path):
    binding = _setup(tmp_path, binding_keys=[
        (GD, "bb p", LINE), (GD, "cc p", LINE)])
    jr.main(EXCLUDE_ARGS + ["--expected-excluded-keys", str(binding)])
    rep = json.loads(jr.OUT_REPORT.read_text(encoding="utf-8"))
    scr = rep["baseline_market_only"]["identity_screening"]
    # population contract: before -> excluded -> after
    assert scr["population_before_screening"] == 3
    assert scr["n_excluded_keys"] == 2
    assert scr["n_excluded_rows"] == 2
    assert scr["population_after_screening"] == 1
    d = rep["baseline_market_only"]
    # subsequent denominators are computed on the post-screening
    # population, and the excluded rows never re-enter
    assert d["entry"]["denominator"] == 1
    assert d["entry"]["n_eligible"] == 1
    assert d["settlement"]["denominator"] == 1
    assert d["close_benchmark"]["denominator"] == 1
    assert d["close_benchmark"]["n_available"] == 1
    # excluded candidates keep their rows in the baseline parquet
    base = pl.read_parquet(jr.OUT_BASELINE)
    ex = [r for r in base.iter_rows(named=True)
          if r["entry_reason"] == "ambiguous_event_identity"]
    assert len(ex) == 2
    for r in ex:
        assert r["entry_eligible"] is False
        assert r["close_benchmark_available"] is False
        assert r["close_reason"] == "not_assessed_excluded"
        assert r["baseline_reason"] == "ambiguous_event_identity"
        assert r["conflicting_event_ids"] != ""
        assert r["affected_snapshots"] in ("morning", "close")
    mv = rep["market_movement"]
    assert mv["denominator"] == 1  # only the clean candidate


def test_binding_without_policy_refuses(tmp_path):
    binding = _setup(tmp_path, binding_keys=[])
    with pytest.raises(SystemExit,
                       match="requires --identity-policy"):
        jr.main(["--entry-clock", "morning_only",
                 "--expected-excluded-keys", str(binding)])
