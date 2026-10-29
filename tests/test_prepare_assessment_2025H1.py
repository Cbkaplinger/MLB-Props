"""Synthetic tests for the stage-1 assessment preparation script
(prepare_assessment_2025H1.py). SYNTHETIC ONLY. Every test drives the
actual entry point (main() or prepare_assessment)."""
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


def _pa_rows():
    """2025H1 actual PAs for the two requested starts: repeated
    encounter (800001 x2 vs P1), a replacement batter 800999 (not in
    any projected lineup), and one UNRECOGNIZED event variant is built
    by the invalid-label tests (map_statcast_events keeps it at -1)."""
    rows = []
    ab = 0
    seq = ["strikeout", "single", "field_out", "walk", "strikeout",
           "double", "field_out", "walk", "strikeout"]
    for i, b in enumerate(B1):
        ab += 1
        rows.append((GAME_DATE, 900001, "Top", ab, P1, b, seq[i]))
    ab += 1
    rows.append((GAME_DATE, 900001, "Top", ab, P1, 800001, "field_out"))  # repeat
    ab += 1
    rows.append((GAME_DATE, 900001, "Top", ab, P1, 800999, "strikeout"))  # repl.
    seq2 = ["single", "strikeout", "field_out", "walk", "double",
            "strikeout", "field_out", "walk", "strikeout"]
    for i, b in enumerate(B2):
        ab += 1
        rows.append((GAME_DATE, 900001, "Bot", ab, P2, b, seq2[i]))
    return rows


def _pa_frame(with_future=True, with_2024=False):
    rows = _pa_rows()
    if with_future:
        rows.append((date(2025, 8, 1), 900001, "Top", 99, P1, 800001,
                     "strikeout"))  # confirm-window row: excluded
    if with_2024:
        rows.append((date(2024, 8, 15), 900001, "Top", 98, P1, 800001,
                     "strikeout"))  # pre-window row: excluded
    return pl.DataFrame(rows, schema={
        "game_date": pl.Date, "game_pk": pl.Int64, "side": pl.Utf8,
        "at_bat_number": pl.Int64, "pitcher": pl.Int64,
        "batter": pl.Int64, "events": pl.Utf8}, orient="row")


def _lineups():
    rows = [(900001, "Top", P1, GAME_DATE, True, *B1),
            (900001, "Bot", P2, GAME_DATE, True, *B2)]
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{i}": pl.Int64 for i in range(1, 10)})
    return pl.DataFrame(rows, schema=schema, orient="row")


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(tmp_path, pa=None, lineups=None):
    pa = pa if pa is not None else _pa_frame()
    lineups = lineups if lineups is not None else _lineups()
    pp, lp = tmp_path / "pa.parquet", tmp_path / "lineups.parquet"
    pa.write_parquet(pp)
    lineups.write_parquet(lp)
    return {"pa_path": str(pp), "lineups_path": str(lp),
            "pa_sha": _sha(pp), "lineups_sha": _sha(lp)}


def _run(tmp_path, out="prep", pa=None, lineups=None, ack=ACK,
         pa_sha=None, lineups_sha=None):
    h = _write(tmp_path, pa, lineups)
    res = prep.prepare_assessment(
        pa if pa is not None else _pa_frame(),
        lineups if lineups is not None else _lineups(),
        tmp_path / out,
        assessment_start=A_START, assessment_end=A_END,
        execution_ack=ack)
    return res, h


# ------------------------------------------------- 1. derivation contract
def test_preserves_replacements_repeats_and_window(tmp_path):
    res, h = _run(tmp_path, out="prep_ok")
    out = pl.read_parquet(Path(res["assessment_path"]))
    assert out.height == 20  # 18 projected-batter PAs + repeat + repl.
    # 6-column contract (no game_date; window enforced by derivation)
    assert out.columns == ["game_pk", "side", "pitcher", "at_bat_number",
                           "batter", "class_label"]
    # every requested starter preserved, replacements included
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
    # receipt on disk with identities + accounting
    receipt = json.loads(
        (Path(res["out_dir"]) / "preparation_receipt.json")
        .read_text(encoding="utf-8"))
    assert receipt["outputs"]["assessment_2025H1_v1.parquet"] == \
        res["assessment_sha256"]
    assert receipt["code_identity"]["m0_multiclass_resolved_path"]


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
    pa = _pa_frame().with_columns(
        pl.when(pl.col("batter") == 800002)
        .then(pl.lit("mysterious_unknown_event"))
        .otherwise(pl.col("events")).alias("events"))
    with pytest.raises(ValueError, match="invalid_class_labels"):
        _run(tmp_path, out="out_lab", pa=pa)
    out = tmp_path / "out_lab"
    failure = json.loads((out / "failure_record.json").read_text(
        encoding="utf-8"))
    assert failure["gate"] == "invalid_class_labels"
    assert failure["detail"]["n_invalid"] == 1
    # evidence preserved: the -1 row identity is in the failure detail
    assert any(r[4] == 800002 for r in failure["detail"]["examples"])
    # NO assessment parquet was written
    assert not (out / "assessment_2025H1_v1.parquet").exists()


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
            execution_ack="WRONG")
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
            "--assessment-start", A_START, "--assessment-end", A_END,
            "--out-dir", str(tmp_path / "out_sub"),
            "--execution-ack", ACK]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0
    receipt = json.loads((tmp_path / "out_sub"
                          / "preparation_receipt.json").read_text(
        encoding="utf-8"))
    assert receipt["accounting"]["assessment_starts"] == 2
    assert receipt["accounting"]["label_counts"]["-1"] == 0
