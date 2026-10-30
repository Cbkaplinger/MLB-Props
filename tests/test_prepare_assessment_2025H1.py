"""Synthetic tests for the stage-1 assessment preparation script
(prepare_assessment_2025H1.py) under the ACTUAL declared PA schema:
no side, no events, y present; multiclass labels arrive via the
explicit raw-file terminal-event bridge. SYNTHETIC ONLY."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import prepare_assessment_2025H1 as prep  # noqa: E402

ACK = prep.EXECUTION_ACK_TOKEN
P1, P2 = 700001, 700002
B1 = [800001, 800002, 800003, 800004, 800005, 800006, 800007, 800008,
      800009]
B2 = [800101, 800102, 800103, 800104, 800105, 800106, 800107, 800108,
      800109]
A_START, A_END = "2025-01-01", "2025-06-30"
GAME_DATE = date(2025, 4, 15)
HIST_DATE = date(2024, 6, 20)


def _pa_rows(with_future=False, with_2024=False):
    """SCHEMA-FAITHFUL PA rows (actual pa_table schema: no side, no
    events; y is the binary K indicator). 2025H1 actual PAs for the two
    requested starters: repeated encounter (800001 x2 vs P1), a
    replacement batter 800999 (not in any projected lineup)."""
    rows = []
    # declared pre-assessment history (2024 rows): never in the window
    if with_2024:
        for i, b in enumerate(B1):
            rows.append((date(2024, 6, 20), 500, 100 + i, P1, b, 1))
    ab = 0
    yv = [1, 0, 0, 0, 1, 0, 0, 0, 1]
    for i, b in enumerate(B1):
        ab += 1
        rows.append((GAME_DATE, 900001, ab, P1, b, yv[i]))
    ab += 1
    rows.append((GAME_DATE, 900001, ab, P1, 800001, 0))  # repeat
    ab += 1
    rows.append((GAME_DATE, 900001, ab, P1, 800999, 1))  # repl.
    seq2 = ["single", "strikeout", "field_out", "walk", "double",
            "strikeout", "field_out", "walk", "strikeout"]
    for i, b in enumerate(B2):
        ab += 1
        rows.append((GAME_DATE, 900001, ab, P2, b, 0))
    if with_future:
        rows.append((date(2025, 8, 1), 900001, 99, P1, 800001,
                     1))  # confirm-window row: excluded
    return rows


PA_SCHEMA = {"game_date": pl.Date, "game_pk": pl.Int64,
             "at_bat_number": pl.Int64, "pitcher": pl.Int64,
             "batter": pl.Int64, "y": pl.Int64}


def _pa_frame(with_future=False, with_2024=False):
    return pl.DataFrame(_pa_rows(with_future, with_2024),
                        schema=PA_SCHEMA, orient="row")


def _lineups():
    rows = [(900001, "Top", P1, GAME_DATE, True, *B1),
            (900001, "Bot", P2, GAME_DATE, True, *B2)]
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{i}": pl.Int64 for i in range(1, 10)})
    return pl.DataFrame(rows, schema=schema, orient="row")


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _raw_from_events(pa_events: pl.DataFrame) -> pl.DataFrame:
    """Multi-pitch rows precede each terminal row; events non-null only
    on the terminal row."""
    rows = []
    first = True
    for r in pa_events.iter_rows(named=True):
        key = (r["game_pk"], r["at_bat_number"], r["batter"])
        if first:  # ordinary pitch rows before the terminal row
            rows.append({"game_pk": key[0], "at_bat_number": key[1],
                         "batter": key[2], "events": None})
            rows.append({"game_pk": key[0], "at_bat_number": key[1],
                         "batter": key[2], "events": None})
            first = False
        rows.append({"game_pk": key[0], "at_bat_number": key[1],
                     "batter": key[2], "events": r["events"]})
    schema = {"game_pk": pl.Int64, "at_bat_number": pl.Int64,
              "batter": pl.Int64, "events": pl.Utf8}
    return pl.DataFrame(rows, schema=schema, orient="row")


def _enriched(with_unknown=False):
    """Events-bearing copy of the PA rows (label-source fixture)."""
    pa = _pa_frame()
    out = pa.with_columns(pl.col("y").cast(pl.Int64).alias("_k"))
    ev = []
    for r in out.iter_rows(named=True):
        ev.append("strikeout" if r["y"] == 1 else "field_out")
    if with_unknown:
        ev = ["mysterious_unknown_event" if i == 0 else e
              for i, e in enumerate(ev)]
    return pa.with_columns(pl.Series("events", ev))


def _write(tmp_path, pa=None, lineups=None, raw=None):
    pa = pa if pa is not None else _pa_frame()
    lineups = lineups if lineups is not None else _lineups()
    raw = raw if raw is not None else _raw_from_events(_enriched())
    pp, lp, rp = (tmp_path / "pa.parquet", tmp_path / "lineups.parquet",
                  tmp_path / "raw_events.parquet")
    pa.write_parquet(pp)
    lineups.write_parquet(lp)
    raw.write_parquet(rp)
    return {"pa_path": str(pp), "lineups_path": str(lp),
            "raw_path": str(rp), "pa_sha": _sha(pp),
            "lineups_sha": _sha(lp), "raw_sha": _sha(rp)}


def _run(tmp_path, out="prep", pa=None, lineups=None, raw=None, ack=ACK,
         pa_sha=None, lineups_sha=None, raw_sha=None):
    h = _write(tmp_path, pa, lineups, raw)
    res = prep.prepare_assessment(
        pa if pa is not None else _pa_frame(),
        lineups if lineups is not None else _lineups(),
        tmp_path / out,
        assessment_start=A_START, assessment_end=A_END,
        execution_ack=ack, raw_events=[h["raw_path"]])
    return res, h


# ------------------------------------------------- 1. derivation contract
def test_preserves_replacements_repeats_and_window(tmp_path):
    res, h = _run(tmp_path, out="prep_ok")
    out = pl.read_parquet(Path(res["assessment_path"]))
    assert out.height == 20  # 18 projected-batter PAs + repeat + repl.
    assert out.columns == ["game_pk", "side", "pitcher", "at_bat_number",
                           "batter", "class_label"]
    keys = {(r["game_pk"], r["side"], r["pitcher"])
            for r in out.iter_rows(named=True)}
    assert keys == {(900001, "Top", P1), (900001, "Bot", P2)}
    assert out.filter(pl.col("batter") == 800999).height == 1
    assert out.filter((pl.col("batter") == 800001)).height == 2
    acc = res["accounting"]
    assert acc["assessment_pas"] == 20
    assert acc["request_starts"] == 2
    assert acc["assessment_starts"] == 2
    assert acc["missing_outcome_starts"] == 0
    assert acc["unrequested_outcome_starts"] == 0
    assert acc["label_counts"]["-1"] == 0
    receipt = json.loads(
        (Path(res["out_dir"]) / "preparation_receipt.json")
        .read_text(encoding="utf-8"))
    assert receipt["outputs"]["assessment_2025H1_v1.parquet"] == \
        res["assessment_sha256"]
    assert receipt["code_identity"]["m0_multiclass_resolved_path"]
    # y-consistency gate recorded: class-0 agrees with binary y
    assert receipt["accounting"]["label_bridge"]["raw_files"]


def test_future_and_2024_rows_excluded_by_window(tmp_path):
    res_a, _ = _run(tmp_path, out="out_win_a")
    res_b, _ = _run(tmp_path, out="out_win_b",
                    pa=_pa_frame(with_future=True, with_2024=True))
    a = pl.read_parquet(Path(res_a["assessment_path"]))
    b = pl.read_parquet(Path(res_b["assessment_path"]))
    # identical derived assessment: future + 2024 rows never enter
    assert a.rows() == b.rows()


# ------------------------------------------------------- 2. label refusal
def test_unrecognized_event_refuses_before_output(tmp_path):
    """Unknown events map to -1; the bridge's require_complete refusal
    preserves evidence (missing/unknown counts) before any output."""
    enriched = _enriched(with_unknown=True)
    raw = _raw_from_events(enriched)
    with pytest.raises(ValueError, match="label integrity failure"):
        _run(tmp_path, out="out_lab", raw=raw)
    out = tmp_path / "out_lab"
    failure = json.loads((out / "failure_record.json").read_text(
        encoding="utf-8"))
    assert "1 carry unrecognized events" in failure["error"]
    assert not (out / "assessment_2025H1_v1.parquet").exists()


def test_y_label_inconsistency_refuses(tmp_path):
    """A terminal event that contradicts the PA table's binary y must
    refuse (conflicting outcome sources are never scored)."""
    enriched = _enriched()
    raw = _raw_from_events(enriched.with_columns(
        pl.when(pl.col("y") == 1).then(pl.lit("single"))
        .otherwise(pl.lit("strikeout")).alias("events")))
    with pytest.raises(ValueError, match="y_label_inconsistent"):
        _run(tmp_path, out="out_yinc", raw=raw)
    failure = json.loads((tmp_path / "out_yinc" / "failure_record.json")
                         .read_text(encoding="utf-8"))
    assert failure["gate"] == "y_label_inconsistent"


# ------------------------------------------------------- 3. duplicates
def test_duplicate_pa_identity_refused(tmp_path):
    pa = pl.concat([_pa_frame(), _pa_frame().head(1)])
    with pytest.raises(ValueError, match="duplicate_pa_identity"):
        _run(tmp_path, out="out_dup", pa=pa)
    failure = json.loads((tmp_path / "out_dup" / "failure_record.json")
                         .read_text(encoding="utf-8"))
    assert failure["gate"] == "duplicate_pa_identity"


# ------------------------------------------------------- 4. ack + hashes
def test_invalid_ack_no_side_effects(tmp_path):
    _write(tmp_path)
    with pytest.raises(ValueError, match="preparation acknowledgement"):
        prep.prepare_assessment(
            _pa_frame(), _lineups(), tmp_path / "out_ack",
            assessment_start=A_START, assessment_end=A_END,
            execution_ack="WRONG", raw_events=["whatever.parquet"])
    assert not (tmp_path / "out_ack").exists()


def test_input_hash_mismatch_refuses_before_decode(tmp_path):
    h = _write(tmp_path)
    script = (Path(__file__).resolve().parents[1] / "research"
              / "offseason_2026" / "pregame_pa_ext"
              / "prepare_assessment_2025H1.py")
    argv = [sys.executable, str(script),
            "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
            "--expected-pa-sha256", "0" * 64,
            "--expected-lineups-sha256", h["lineups_sha"],
            "--raw-events", h["raw_path"],
            "--expected-raw-events-sha256", h["raw_sha"],
            "--assessment-start", A_START, "--assessment-end", A_END,
            "--out-dir", str(tmp_path / "out_sha"),
            "--execution-ack", ACK]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    assert r.returncode == 1
    assert "INPUT IDENTITY MISMATCH" in r.stderr
    assert not (tmp_path / "out_sha").exists()


def test_subprocess_preparation_produces_receipt(tmp_path):
    h = _write(tmp_path)
    script = (Path(__file__).resolve().parents[1] / "research"
              / "offseason_2026" / "pregame_pa_ext"
              / "prepare_assessment_2025H1.py")
    argv = [sys.executable, str(script),
            "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
            "--expected-pa-sha256", h["pa_sha"],
            "--expected-lineups-sha256", h["lineups_sha"],
            "--raw-events", h["raw_path"],
            "--expected-raw-events-sha256", h["raw_sha"],
            "--assessment-start", A_START, "--assessment-end", A_END,
            "--out-dir", str(tmp_path / "out_sub"),
            "--execution-ack", ACK]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-500:]
    receipt = json.loads((tmp_path / "out_sub"
                          / "preparation_receipt.json").read_text(
        encoding="utf-8"))
    assert receipt["accounting"]["assessment_starts"] == 2
    assert receipt["accounting"]["label_counts"]["-1"] == 0


# ------------------- D1 repair: side attached from the (game_pk,
# pitcher) request mapping; schema-faithful PA source has NO side
def test_schema_faithful_pa_without_side_attaches_request_side(
        tmp_path):
    res, _ = _run(tmp_path, out="out_noside")
    out = pl.read_parquet(Path(res["assessment_path"]))
    assert out.height == 20
    keys = {(r["game_pk"], r["side"], r["pitcher"])
            for r in out.iter_rows(named=True)}
    assert keys == {(900001, "Top", P1), (900001, "Bot", P2)}
    assert out.filter((pl.col("pitcher") == P1))["side"].unique().to_list() \
        == ["Top"]
    assert out.filter((pl.col("pitcher") == P2))["side"].unique().to_list() \
        == ["Bot"]
    assert out.filter((pl.col("batter") == 800001)).height == 2
    assert out.filter(pl.col("batter") == 800999).height == 1


def test_subprocess_schema_faithful_pa_without_side(tmp_path):
    h = _write(tmp_path)
    script = (Path(__file__).resolve().parents[1] / "research"
              / "offseason_2026" / "pregame_pa_ext"
              / "prepare_assessment_2025H1.py")
    argv = [sys.executable, str(script),
            "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
            "--expected-pa-sha256", h["pa_sha"],
            "--expected-lineups-sha256", h["lineups_sha"],
            "--raw-events", h["raw_path"],
            "--expected-raw-events-sha256", h["raw_sha"],
            "--assessment-start", A_START, "--assessment-end", A_END,
            "--out-dir", str(tmp_path / "out_nosub"),
            "--execution-ack", ACK]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-500:]
    out = pl.read_parquet(tmp_path / "out_nosub"
                          / "assessment_2025H1_v1.parquet")
    assert out.height == 20


def test_ambiguous_side_mapping_refuses(tmp_path):
    """One (game_pk, pitcher) mapped to BOTH halves: refuse rather than
    guess which side the actual PAs belong to."""
    rows = [(900001, "Top", P1, GAME_DATE, True, *B1),
            (900001, "Bot", P1, GAME_DATE, True, *B2)]
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{i}": pl.Int64 for i in range(1, 10)})
    lineups = pl.DataFrame(rows, schema=schema, orient="row")
    with pytest.raises(ValueError, match="ambiguous side mapping"):
        _run(tmp_path, out="out_amb", lineups=lineups)


def test_conflicting_source_side_refuses(tmp_path):
    """A side-carrying source whose values CONFLICT with the validated
    request mapping refuses (never silently replaced)."""
    pa = _pa_frame().with_columns(
        pl.when(pl.col("pitcher") == P1)
        .then(pl.lit("Bot")).otherwise(pl.lit("Top")).alias("side"))
    with pytest.raises(ValueError, match="side consistency violation"):
        _run(tmp_path, out="out_conflict", pa=pa)


def test_nonrequested_pitcher_pas_excluded(tmp_path):
    """PAs of a pitcher with no projected request are structurally
    excluded (the (game_pk, pitcher) mapping has no entry)."""
    pa = _pa_frame()
    extra = pl.DataFrame(
        [(GAME_DATE, 900001, 90, 700099, 800001, 0)],
        schema=PA_SCHEMA, orient="row")
    res, _ = _run(tmp_path, out="out_nonreq", pa=pl.concat([pa, extra]))
    out = pl.read_parquet(Path(res["assessment_path"]))
    assert set(out["pitcher"].to_list()) == {P1, P2}  # 700099 excluded
