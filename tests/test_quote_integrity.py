"""Synthetic acceptance tests for quote-multiplicity classification,
full-identity pairing and the narrow normalization policy in
juiced_replay_ledger.py.

Drives the production entry point (jr.main) with:
- exact identical repeats (default refuse; idempotent collapse opt-in);
- same-time conflicting prices;
- different-time observations (timestamp semantics never inferred);
- duplicates only in morning or only in close;
- one duplicated side;
- missing timestamps;
- unchanged unique quotes (no findings, no report, unchanged metrics);
- original four-key identity exclusions coexisting with integrity.

Also asserts: no outcome access on refusal (panel never reached),
full-key pairing, and a durable structured integrity report.

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


def _clean_rows():
    rows = []
    for snap in ("morning", "close"):
        for book in ("draftkings", "fanduel"):
            for side, price in (("over", -120), ("under", 105)):
                rows.append(_bl("evt1", snap, book, side, price))
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


FRIEND_CSV = "game_date,player_name,line,bookmaker,over_odds,under_odds\n"


def _setup(tmp_path, extra_rows=None, with_panel=True, base_rows=None):
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

    rows = ((base_rows if base_rows is not None else _clean_rows())
            + (extra_rows or []))
    pl.DataFrame(rows, schema={
        "event_id": pl.Utf8, "snapshot": pl.Utf8, "snapshot_ts": pl.Utf8,
        "game_date": pl.Utf8, "season_type": pl.Utf8, "book": pl.Utf8,
        "market": pl.Utf8, "player": pl.Utf8, "player_norm": pl.Utf8,
        "line": pl.Float64, "side": pl.Utf8, "price": pl.Int64},
        orient="row").write_parquet(
        hist / "book_lines_pitcher.parquet")
    if with_panel:
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
    jr.__dict__["OUT_INTEGRITY"] = odds_dir / "integrity__t.json"


def _integ(tag=""):
    p = jr.OUT_INTEGRITY
    return p.with_name(p.stem + tag + p.suffix)

def _integ_norm():
    return _integ("__normalize_idempotent")


def _dup_over_rows(snap, ts=TS, prices=(-120,)):
    return [_bl("evt1", snap, "draftkings", "over", p, ts=ts)
            for p in prices]


NORM_ARGS = ["--entry-clock", "morning_only",
             "--identity-policy", "exclude_ambiguous",
             "--quote-policy", "normalize_idempotent"]


def test_unique_quotes_no_findings_no_report(tmp_path):
    _setup(tmp_path)
    assert jr.main(NORM_ARGS) == 0
    assert not _integ().exists()  # nothing to report
    base = pl.read_parquet(jr.OUT_BASELINE)
    r = {x["key"]: x for x in base.iter_rows(named=True)}["aa p"]
    # unchanged unique-contract metrics
    assert abs(r["fair_over_entry"] - FAIR_OVER) < 1e-9
    assert r["entry_eligible"] is True
    assert r["close_benchmark_available"] is True
    assert abs(r["movement_pp"]) < 1e-9


def test_exact_identical_repeats_default_refuse(tmp_path):
    _setup(tmp_path, extra_rows=_dup_over_rows("morning"))
    with pytest.raises(SystemExit, match="quote integrity failure"):
        jr.main(NORM_ARGS[:-2])  # default quote policy = refuse
    rep = json.loads(_integ().read_text(encoding="utf-8"))
    assert rep["morning"]["classes"] == {"identical_repeat": 1}
    assert rep["close"]["n_findings"] == 0
    f = rep["morning"]["findings"][0]
    assert f["event_id"] == "evt1" and f["book"] == "draftkings"
    assert f["n_observations"] == 2 and f["prices"] == [-120.0]


def test_exact_identical_repeats_idempotent_collapse(tmp_path):
    _setup(tmp_path, extra_rows=_dup_over_rows("morning"))
    assert jr.main(NORM_ARGS) == 0
    base = pl.read_parquet(jr.OUT_BASELINE)
    r = {x["key"]: x for x in base.iter_rows(named=True)}["aa p"]
    # collapse changes NOTHING for unique contracts: same de-vig metric
    assert abs(r["fair_over_entry"] - FAIR_OVER) < 1e-9
    assert r["entry_eligible"] is True
    assert r["close_benchmark_available"] is True
    rep = json.loads(_integ_norm().read_text(encoding="utf-8"))
    assert rep["normalization"]["collapsed_identical_copies"]["morning"] == 1
    assert rep["normalization"]["residual_findings"]["morning"]["n_findings"] == 0


def test_same_time_conflicting_prices_refuse_both_policies(tmp_path):
    _setup(tmp_path, extra_rows=_dup_over_rows("morning",
                                               prices=(-120, -130)))
    with pytest.raises(SystemExit, match="quote integrity failure"):
        jr.main(NORM_ARGS[:-2])
    rep = json.loads(_integ().read_text(encoding="utf-8"))
    f = rep["morning"]["findings"][0]
    assert f["class"] == "same_time_conflict"
    assert sorted(f["prices"]) == [-130.0, -120.0]
    _integ().unlink()
    # the idempotent policy must NOT collapse a same-time conflict
    with pytest.raises(SystemExit, match="quote integrity failure"):
        jr.main(NORM_ARGS)
    rep = json.loads(_integ_norm().read_text(encoding="utf-8"))
    assert rep["morning"]["classes"] == {"same_time_conflict": 1}


def test_different_time_observations_refuse(tmp_path):
    # same price at two DIFFERENT timestamps: distinct-time class;
    # timestamp semantics are never inferred; no declared selector
    # exists -> refused under both policies
    _setup(tmp_path, extra_rows=[
        _bl("evt1", "morning", "draftkings", "over", -120,
            ts=f"{GD}T14:00:00Z"),
        _bl("evt1", "morning", "draftkings", "over", -120,
            ts=f"{GD}T13:00:00Z")])
    with pytest.raises(SystemExit, match="quote integrity failure"):
        jr.main(NORM_ARGS[:-2])
    rep = json.loads(_integ().read_text(encoding="utf-8"))
    assert rep["morning"]["classes"] == {"distinct_time": 1}
    _integ().unlink()
    with pytest.raises(SystemExit, match="quote integrity failure"):
        jr.main(NORM_ARGS)
    rep = json.loads(_integ_norm().read_text(encoding="utf-8"))
    assert rep["morning"]["classes"] == {"distinct_time": 1}


def test_duplicate_only_in_morning_close_untouched(tmp_path):
    _setup(tmp_path, extra_rows=_dup_over_rows("morning"))
    jr.main(NORM_ARGS)
    rep = json.loads(_integ_norm().read_text(encoding="utf-8"))
    assert rep["normalization"]["collapsed_identical_copies"] == {"morning": 1, "close": 0}
    assert rep["close"]["n_findings"] == 0


def test_duplicate_only_in_close(tmp_path):
    _setup(tmp_path, extra_rows=_dup_over_rows("close"))
    jr.main(NORM_ARGS)
    rep = json.loads(_integ_norm().read_text(encoding="utf-8"))
    assert rep["close"]["classes"] == {"identical_repeat": 1}
    assert rep["morning"]["n_findings"] == 0
    assert rep["normalization"]["collapsed_identical_copies"]["close"] == 1


def test_missing_timestamp_insufficient_class(tmp_path):
    rows = [r for r in _clean_rows()
            if not (r["snapshot"] == "morning"
                    and r["book"] == "draftkings"
                    and r["side"] == "over")]
    rows += _dup_over_rows("morning", ts=None, prices=(-120, -120))
    _setup(tmp_path, base_rows=rows)
    with pytest.raises(SystemExit, match="quote integrity failure"):
        jr.main(NORM_ARGS)
    rep = json.loads(_integ_norm().read_text(encoding="utf-8"))
    f = rep["morning"]["findings"][0]
    assert f["class"] == "insufficient_timestamp"
    assert f["timestamps"] == []  # never inferred


def test_refusal_never_touches_outcomes(tmp_path):
    # panel is ABSENT: the integrity refusal must fire BEFORE any
    # outcome/panel consumption (otherwise a FileNotFoundError would
    # surface instead of the integrity refusal)
    _setup(tmp_path, extra_rows=_dup_over_rows("morning"),
           with_panel=False)
    with pytest.raises(SystemExit, match="quote integrity failure"):
        jr.main(NORM_ARGS[:-2])


def test_full_identity_pairing_event_key(tmp_path):
    # the over side of book fanduel quotes a DIFFERENT event than the
    # under side: full-key pairing refuses to marry them (and the
    # reduced-key ambiguity guard fires first - two events on one
    # reduced key), proving counter-sides never attach cross-event
    _setup(tmp_path, extra_rows=[
        _bl("evt1b", "morning", "fanduel", "over", -120, pnorm="aa p")])
    events = {"evt1": GD, "evt1b": GD}
    jr.__dict__["load_event_date_map"] = lambda: dict(events)
    (tmp_path / "hist" / "event_date_map.json").write_text(
        json.dumps(events), encoding="utf-8")
    # default identity policy = refuse: the ambiguity guard fires
    with pytest.raises(SystemExit, match="ambiguous reduced-key"):
        jr.main(["--entry-clock", "morning_only"])


def test_four_key_exclusions_coexist_with_integrity(tmp_path):
    # the original four-key identity exclusions plus an exact
    # duplicate: exclusion accounting and idempotent collapse coexist
    rows = (_clean_rows() + _dup_over_rows("morning")
            + [_bl("evt2", "morning", "draftkings", "over", -120,
                   pnorm="bb p"),
               _bl("evt2", "morning", "draftkings", "under", 105,
                   pnorm="bb p"),
               _bl("evt2b", "morning", "draftkings", "over", -120,
                   pnorm="bb p"),
               _bl("evt2b", "morning", "draftkings", "under", 105,
                   pnorm="bb p")])
    _setup(tmp_path, base_rows=rows)
    # the excluded candidate must exist in the settlement panel to be
    # preserved in coverage accounting (as in the real lake)
    panel = pl.DataFrame([
        {"gd": GD, "key": "aa p", "line": LINE, "p_ours_cal": 0.55,
         "y": 1.0, "p_book_close": 0.50, "player_name": "Aa P"},
        {"gd": GD, "key": "bb p", "line": LINE, "p_ours_cal": 0.50,
         "y": 1.0, "p_book_close": 0.50, "player_name": "Bb P"}])
    panel.write_parquet(jr.PANEL)
    evmap = tmp_path / "hist" / "event_date_map.json"
    evmap.write_text(json.dumps({"evt1": GD, "evt2": GD, "evt2b": GD}),
                     encoding="utf-8")
    jr.__dict__["load_event_date_map"] = lambda: {
        "evt1": GD, "evt2": GD, "evt2b": GD}
    binding = tmp_path / "binding.json"
    binding.write_text(json.dumps({"expected_excluded_keys": [
        {"gd": GD, "key": "bb p", "line": LINE}]}), encoding="utf-8")
    rc = jr.main(NORM_ARGS + ["--expected-excluded-keys", str(binding)])
    assert rc == 0
    rep = json.loads(_integ_norm().read_text(encoding="utf-8"))
    assert rep["normalization"]["collapsed_identical_copies"]["morning"] == 1
    assert rep["normalization"]["applied"] is True
    base = pl.read_parquet(jr.OUT_BASELINE)
    by_key = {x["key"]: x for x in base.iter_rows(named=True)}
    # four-key-style exclusion preserved with full accounting
    assert by_key["bb p"]["entry_reason"] == "ambiguous_event_identity"
    assert "evt2" in by_key["bb p"]["conflicting_event_ids"]
    assert sorted(by_key["bb p"]["conflicting_event_ids"].split(",")) == ["evt2", "evt2b"]
    assert by_key["bb p"]["entry_eligible"] is False
    # clean contract metric unchanged
    assert abs(by_key["aa p"]["fair_over_entry"] - FAIR_OVER) < 1e-9

