"""Synthetic tests for the temporal-robustness evaluation
(temporal_robustness_evaluation.py). SYNTHETIC ONLY. Every test drives
the actual entry point with hand-checkable fixtures.

Requirement -> implementation -> test-evidence closure table:
  End-to-end success across BOTH periods + manifest + receipts -> test 1
  Chronology: period constants strictly ordered; structural limits
  verified at entry; R3 partition unreachable                 -> test 2
  Period accounting: R1/R2 populations disjoint; flipping R2
  assessment labels leaves R1 results unchanged and vice versa -> test 3
  Fold/period feasibility BEFORE fitting: too-few fit date
  clusters refuses before any fit (failure record preserved)  -> test 4
  Label coverage: scored label outside the fitted class set
  refuses                                                     -> test 5
  R3/2026 structural inaccessibility: scored dates at/after
  2025-07-01 never scored; rows in the R3 partition are
  excluded with counts                                        -> test 6
  Machinery-identity anchor: exact reproduction / altered
  reference refuses / missing refuses; per-start evidence
  written before the gate                                     -> tests 7a/b/c
  Ack gate (direct + CLI exit 2); reference pin ENFORCED
  (exit 1); pin REQUIRED                                      -> tests 8a-d
  CLI end-to-end success                                      -> test 11
  Write-once refuses                                          -> test 12
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import temporal_robustness_evaluation as te  # noqa: E402

# the synthetic fixture carries 2 distinct in-window date clusters; the
# real packet keeps the declared minimum of 60 against the registered
# source (277 verified clusters in the R1 fit window)
te.MIN_FIT_DATE_CLUSTERS = 2

ACK = te.EXECUTION_ACK_TOKEN
P1, P2 = 700001, 700002
B1 = [800001 + i for i in range(9)]
B2 = [800101 + i for i in range(9)]
RUNNER = Path(te.__file__).resolve()

_PA_KEYS = ["game_date", "game_pk", "inning_topbot", "at_bat_number",
            "pitcher", "batter", "y", "stand", "p_throws"]
PA_SCHEMA = {k: (pl.Utf8 if k in ("inning_topbot", "stand", "p_throws")
                 else pl.Date if k == "game_date" else pl.Int64)
             for k in _PA_KEYS}


def _row(gd, gk, tb, abn, p, b, y, stand, throws):
    return (gd, gk, tb, abn, p, b, y, stand, throws)


def _pa_rows():
    rows = []
    # 2022 history (prior to the earliest R1 fit cutoff, so the w150/EW
    # states are non-null for the 2023 fit rows - the real pa_table has
    # 2022-04-07.. rows)
    h22 = date(2022, 6, 10)
    for i, b in enumerate(B1):
        rows.append(_row(h22, 30, "Top", 80 + i, P1, b, 0, "L", "R"))
    for i, b in enumerate(B2):
        rows.append(_row(h22, 30, "Bot", 89 + i, P2, b, 0, "R", "L"))
    # 2023 history (inside the R1 fit window)
    h23 = date(2023, 5, 10)
    for i, b in enumerate(B1):
        rows.append(_row(h23, 40, "Top", 100 + i, P1, b, 0, "L", "R"))
    for i, b in enumerate(B2):
        rows.append(_row(h23, 40, "Bot", 109 + i, P2, b, 0, "R", "L"))
    d24 = date(2024, 5, 10)
    for i, b in enumerate(B1):
        rows.append(_row(d24, 41, "Top", 120 + i, P1, b,
                         1 if i % 2 == 0 else 0, "L", "R"))
    for i, b in enumerate(B2):
        rows.append(_row(d24, 41, "Bot", 129 + i, P2, b,
                         1 if i % 3 == 0 else 0, "R", "L"))
    d24b = date(2024, 8, 10)
    for i, b in enumerate(B1):
        rows.append(_row(d24b, 42, "Top", 140 + i, P1, b,
                         1 if i % 4 == 0 else 0, "L", "R"))
    r1d = date(2024, 8, 20)
    for i, b in enumerate(B1):
        rows.append(_row(r1d, 900101, "Top", 200 + i, P1, b,
                         1 if i % 2 == 0 else 0, "L", "R"))
    for i, b in enumerate(B2):
        rows.append(_row(r1d, 900101, "Bot", 210 + i, P2, b,
                         1 if i % 2 else 0, "R", "L"))
    r2d = date(2025, 5, 1)
    for i, b in enumerate(B1):
        rows.append(_row(r2d, 900201, "Top", 300 + i, P1, b,
                         1 if i % 2 == 0 else 0, "L", "R"))
    for i, b in enumerate(B2):
        rows.append(_row(r2d, 900201, "Bot", 310 + i, P2, b,
                         1 if i % 2 else 0, "R", "L"))
    r3d = date(2025, 7, 10)  # R3 partition rows - must NEVER be scored
    for i, b in enumerate(B1[:3]):
        rows.append(_row(r3d, 900301, "Top", 400 + i, P1, b, 1,
                         "L", "R"))
    return rows


def _pa_frame():
    return pl.DataFrame(_pa_rows(), schema=PA_SCHEMA, orient="row")


def _lineups():
    rows = [(900101, "Top", P1, date(2024, 8, 20), True, *B1),
            (900101, "Bot", P2, date(2024, 8, 20), True, *B2),
            (900201, "Top", P1, date(2025, 5, 1), True, *B1),
            (900201, "Bot", P2, date(2025, 5, 1), True, *B2)]
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{i}": pl.Int64 for i in range(1, 10)})
    return pl.DataFrame(rows, schema=schema, orient="row")


def _assessment():
    rows = []
    for i, b in enumerate(B1):
        rows.append((900201, "Top", P1, 300 + i, b,
                     0 if i % 2 == 0 else 2))
    for i, b in enumerate(B2):
        rows.append((900201, "Bot", P2, 310 + i, b,
                     0 if i % 2 else 2))
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "at_bat_number": pl.Int64, "batter": pl.Int64,
        "class_label": pl.Int64}, orient="row")


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(tmp_path, pa=None, lineups=None, assessment=None):
    pa = pa if pa is not None else _pa_frame()
    lineups = lineups if lineups is not None else _lineups()
    assessment = assessment if assessment is not None else _assessment()
    h = {}
    for name, frame in (("pa", pa), ("lineups", lineups),
                        ("assessment", assessment)):
        pth = tmp_path / f"{name}.parquet"
        frame.write_parquet(pth)
        h[f"{name}_path"] = str(pth)
        h[f"{name}_sha"] = _sha(pth)
    ev = []
    for r in pa.iter_rows(named=True):
        ev.append("strikeout" if r["y"] == 1 else "field_out")
    raw = pa.select("game_pk", "at_bat_number", "batter").with_columns(
        pl.Series("events", ev))
    rp = tmp_path / "raw_events.parquet"
    raw.write_parquet(rp)
    h["raw_path"] = str(rp)
    h["raw_sha"] = _sha(rp)
    return h


def _wrong_reference():
    rows = [(900201, "Top", P1, 0.5), (900201, "Bot", P2, 0.5)]
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "rps_w0_pooled": pl.Float64}, orient="row")


def _harvest_anchor_reference(out_dir) -> pl.DataFrame:
    ps = pl.read_parquet(Path(out_dir) / "anchor_per_start.parquet")
    return ps.select(
        "game_pk", "side", "pitcher",
        pl.col("rps_anchor").alias("rps_w0_pooled"))


def _cohort_hash_of(cohort: pl.DataFrame) -> str:
    return hashlib.sha256("\n".join(sorted(
        "%d|%s|%d" % (int(r["game_pk"]), str(r["side"]),
                      int(r["pitcher"]))
        for r in cohort.iter_rows(named=True)))
        .encode("utf-8")).hexdigest()


def _run(tmp_path, out="out", pa=None, lineups=None, assessment=None,
         ack=ACK, cohort_keys=None, expected_cohort_hash=None,
         reconstruction_reference=None, reference_sha256=None):
    h = _write(tmp_path, pa, lineups, assessment)
    pa_frame = pa if pa is not None else _pa_frame()
    if reconstruction_reference is None and ack == ACK:
        boot_out = tmp_path / f"_boot_{out}"
        try:
            te.run_temporal_robustness(
                pa_frame,
                lineups if lineups is not None else _lineups(),
                assessment if assessment is not None else _assessment(),
                boot_out,
                execution_ack=ack, raw_events=[h["raw_path"]],
                cohort_keys=cohort_keys,
                expected_cohort_hash=expected_cohort_hash,
                reconstruction_reference=_wrong_reference(),
                min_fit_date_clusters=2)
        except ValueError:
            pass
        boot_ps = boot_out / "anchor_per_start.parquet"
        assert boot_ps.exists(), (
            "bootstrap run must preserve anchor per-start evidence "
            "before the gate refuses")
        reconstruction_reference = _harvest_anchor_reference(boot_out)
    return te.run_temporal_robustness(
        pa_frame, lineups if lineups is not None else _lineups(),
        assessment if assessment is not None else _assessment(),
        tmp_path / out,
        execution_ack=ack, raw_events=[h["raw_path"]],
        cohort_keys=cohort_keys, expected_cohort_hash=expected_cohort_hash,
        reconstruction_reference=reconstruction_reference,
        reconstruction_reference_sha256=reference_sha256,
        min_fit_date_clusters=2)


# ------------------------------------- 1. e2e + output-hash manifest closure
def test_e2e_both_periods_manifest_and_receipts(tmp_path):
    res = _run(tmp_path)
    expected = ["temporal_robustness_report.json",
                "temporal_per_start_R1.parquet",
                "temporal_per_start_R2.parquet",
                "keyed_pa_probabilities_R1.parquet",
                "keyed_pa_probabilities_R2.parquet",
                "anchor_per_start.parquet",
                "receipt_initial.json", "receipt_final.json"]
    for name in expected:
        assert (Path(res["out_dir"]) / name).exists(), name
    final = json.loads(
        (Path(res["out_dir"]) / "receipt_final.json")
        .read_text(encoding="utf-8"))
    for name, sha in res["outputs"].items():
        assert final["outputs"][name] == sha
        assert final["outputs"][name] == _sha(
            Path(res["out_dir"]) / name)
    assert final["reconstruction"]["verified"] is True
    assert final["acceptance"]["status"] == "COMPLETED"
    assert len(res["periods"]) == 2
    ids = [p["id"] for p in res["periods"]]
    assert ids == ["R1", "R2"]
    for po in res["periods"]:
        assert po["n_starts"] == 2
        assert po["n_matched_pas"] == 18


# ------------------------------------------------- 2. chronology + limits
def test_chronology_and_structural_limits():
    te.check_structural_limits()  # must not raise
    for p in te.PERIODS:
        assert p["fit_start"] < p["fit_end"] < p["score_start"] \
            <= p["score_end"]
        assert p["score_end"] < te.R3_START
    with pytest.raises(ValueError, match="R3 confirm partition"):
        bad = dict(te.PERIODS[0])
        bad = {**te.PERIODS[0], "score_end": date(2025, 8, 1)}
        te.PERIODS.append(bad)
        try:
            te.check_structural_limits()
        finally:
            te.PERIODS.pop()
    with pytest.raises(ValueError, match="R3 confirm partition"):
        te.PERIODS.append({**te.PERIODS[0], "id": "X",
                           "score_end": date(2025, 12, 31)})
        try:
            te.check_structural_limits()
        finally:
            te.PERIODS.pop()


# ---------------------- 3. period accounting: disjoint, no cross-leakage
def test_period_accounting_disjoint_and_leak_free(tmp_path):
    res1 = _run(tmp_path, out="acct_a")
    # flip every R2 assessment label WITHIN the fitted class set {0,2};
    # R1 results must be unchanged (period isolation), R2 results change
    rows = [(gk, s, p, abn, b, 2 - c)
            for (gk, s, p, abn, b, c) in _assessment().iter_rows()]
    flipped = pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "at_bat_number": pl.Int64, "batter": pl.Int64,
        "class_label": pl.Int64}, orient="row")
    res2 = _run(tmp_path, out="acct_b", assessment=flipped)
    r1a = pl.read_parquet(Path(res1["out_dir"])
                          / "temporal_per_start_R1.parquet")
    r1b = pl.read_parquet(Path(res2["out_dir"])
                          / "temporal_per_start_R1.parquet")
    assert r1a.equals(r1b)
    # R2 results DO change with flipped labels (they are R2's outcomes)
    r2a = pl.read_parquet(Path(res1["out_dir"])
                          / "temporal_per_start_R2.parquet")
    r2b = pl.read_parquet(Path(res2["out_dir"])
                          / "temporal_per_start_R2.parquet")
    assert not r2a.equals(r2b)
    # populations disjoint: R1 score dates (2024) never in R2 (2025)
    assert r1a["game_date"].max() < r2a["game_date"].min()
    rep1 = json.loads(
        (Path(res1["out_dir"]) / "temporal_robustness_report.json")
        .read_text(encoding="utf-8"))
    per = {p["id"]: p for p in rep1["periods"]}
    assert per["R1"]["n_starts"] == 2 and per["R2"]["n_starts"] == 2


# ------------- 4. feasibility refusal precedes fitting (too-few dates)
def test_feasibility_refusal_before_fitting(tmp_path):
    # drop the 2023 history rows: the R1 fit window then has zero
    # observed date clusters -> refusal BEFORE any model fit
    rows = [r for r in _pa_rows() if r[0] != date(2023, 5, 10)]
    pa_thin = pl.DataFrame(rows, schema=PA_SCHEMA, orient="row")
    h = _write(tmp_path, pa=pa_thin)
    with pytest.raises(ValueError, match="date clusters"):
        te.run_temporal_robustness(
            pa_thin, _lineups(), _assessment(), tmp_path / "out_thin",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())
    fr = json.loads((tmp_path / "out_thin" / "failure_record.json")
                    .read_text(encoding="utf-8"))
    assert "date clusters" in fr["error"]
    assert (tmp_path / "out_thin" / "receipt_initial.json").exists()


# ------------------------------------------ 5. label coverage refusal
def test_unknown_label_refuses(tmp_path):
    h = _write(tmp_path)
    # an R2 scored PA with class 3 (absent from the fitted class set)
    rows = _assessment().to_dicts()
    rows.append({"game_pk": 900201, "side": "Top", "pitcher": P1,
                 "at_bat_number": 320, "batter": B1[1], "class_label": 3})
    bad = pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "at_bat_number": pl.Int64, "batter": pl.Int64,
        "class_label": pl.Int64}, orient="row")
    with pytest.raises(ValueError, match="outside the fitted class set"):
        _run(tmp_path, out="out_label", assessment=bad)


# ----------------------------- 6. R3/2026 structural inaccessibility
def test_r3_partition_never_scored(tmp_path):
    res = _run(tmp_path, out="out_r3")
    # the fixture contains 2025-07-10 rows (R3 partition); the runner
    # must complete while scoring ONLY the two 2025H1/2024H2 starts
    final = json.loads((Path(res["out_dir"]) / "receipt_final.json")
                       .read_text(encoding="utf-8"))
    per = final["counts"]["periods"]
    assert {p["id"]: p["n_starts"] for p in per} == {"R1": 2, "R2": 2}
    # no per-start row carries an R3-partition date
    for pid in ("R1", "R2"):
        ps = pl.read_parquet(Path(res["out_dir"])
                             / f"temporal_per_start_{pid}.parquet")
        assert ps["game_date"].max() < te.R3_START


# --------------------- 7a/b/c. machinery-identity anchor reconstruction
def test_anchor_gate_exact_pass(tmp_path):
    res = _run(tmp_path, out="out_recon")
    rec = res["reconstruction"]
    assert rec["verified"] is True
    assert rec["max_abs_rps_diff"] == 0.0
    assert rec["reference_column"] == "rps_w0_pooled"
    # per-start evidence written BEFORE the gate
    assert (Path(res["out_dir"]) / "anchor_per_start.parquet").exists()


def test_anchor_gate_altered_reference_refuses(tmp_path):
    h = _write(tmp_path)
    boot = tmp_path / "_boot_alt"
    with pytest.raises(ValueError, match="ANCHOR reconstruction gate "
                                         "FAILED"):
        te.run_temporal_robustness(
            _pa_frame(), _lineups(), _assessment(), boot,
            execution_ack=ACK, raw_events=[h["raw_path"]],
            min_fit_date_clusters=2,
            reconstruction_reference=_wrong_reference())
    assert (boot / "failure_record.json").exists()
    ref = _harvest_anchor_reference(boot).with_columns(
        (pl.col("rps_w0_pooled") + 1e-9).alias("rps_w0_pooled"))
    with pytest.raises(ValueError, match="ANCHOR reconstruction gate "
                                         "FAILED"):
        te.run_temporal_robustness(
            _pa_frame(), _lineups(), _assessment(), tmp_path / "out_alt",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            min_fit_date_clusters=2, reconstruction_reference=ref)


def test_anchor_gate_missing_reference_refuses(tmp_path):
    h = _write(tmp_path)
    with pytest.raises(ValueError, match="reconstruction reference "
                                         "required"):
        te.run_temporal_robustness(
            _pa_frame(), _lineups(), _assessment(), tmp_path / "out_none",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            min_fit_date_clusters=2,
            reconstruction_reference=None)


# --------------------------------------------------- 8a. direct ack gate
def test_ack_gate_direct_call(tmp_path):
    h = _write(tmp_path)
    with pytest.raises(ValueError,
                       match="execution acknowledgement"):
        te.run_temporal_robustness(
            _pa_frame(), _lineups(), _assessment(), tmp_path / "out_ack",
            execution_ack="WRONG", raw_events=[h["raw_path"]],
            min_fit_date_clusters=2,
            reconstruction_reference=_wrong_reference())
    assert not (tmp_path / "out_ack").exists()


# ------------------------------------------ 8b. CLI ack gate exit 2
def test_cli_ack_gate_zero_side_effects(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--pa-source", "nope.parquet", "--lineups", "nope.parquet",
         "--assessment", "nope.parquet", "--raw-events", "nope.parquet",
         "--out-dir", str(tmp_path / "out_cli_ack"),
         "--execution-ack", "WRONG",
         "--cohort-keys", "nope.parquet", "--expected-cohort-hash",
         "0" * 64,
         "--reconstruction-reference", "nope.parquet",
         "--expected-reconstruction-sha256", "0" * 64,
         "--expected-pa-sha256", "0" * 64,
         "--expected-lineups-sha256", "0" * 64,
         "--expected-assessment-sha256", "0" * 64],
        capture_output=True, text=True)
    assert proc.returncode == 2
    assert "EXECUTION REFUSED" in proc.stderr
    assert not (tmp_path / "out_cli_ack").exists()


# --------------- 8c. CLI reconstruction-reference identity ENFORCED
def test_cli_reference_hash_enforced_before_decode(tmp_path):
    h = _write(tmp_path)
    ref_path = tmp_path / "ref.parquet"
    _wrong_reference().write_parquet(ref_path)
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
         "--assessment", h["assessment_path"],
         "--raw-events", h["raw_path"],
         "--out-dir", str(tmp_path / "out_cli_ref"),
         "--execution-ack", ACK,
         "--cohort-keys", h["lineups_path"], "--expected-cohort-hash",
         _cohort_hash_of(_lineups().select("game_pk", "side", "pitcher")),
         "--reconstruction-reference", str(ref_path),
         "--expected-reconstruction-sha256", "0" * 64,
         "--expected-pa-sha256", h["pa_sha"],
         "--expected-lineups-sha256", h["lineups_sha"],
         "--expected-assessment-sha256", h["assessment_sha"]],
        capture_output=True, text=True)
    assert proc.returncode == 1
    assert "INPUT IDENTITY MISMATCH" in proc.stderr
    assert not (tmp_path / "out_cli_ref").exists()


# --------------- 8d. CLI reconstruction pin is REQUIRED (argparse)
def test_cli_reference_hash_pin_required(tmp_path):
    h = _write(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
         "--assessment", h["assessment_path"],
         "--raw-events", h["raw_path"],
         "--out-dir", str(tmp_path / "out_cli_nopin"),
         "--execution-ack", ACK,
         "--cohort-keys", h["lineups_path"], "--expected-cohort-hash",
         _cohort_hash_of(_lineups().select("game_pk", "side", "pitcher")),
         "--reconstruction-reference", "whatever.parquet",
         "--expected-pa-sha256", h["pa_sha"],
         "--expected-lineups-sha256", h["lineups_sha"],
         "--expected-assessment-sha256", h["assessment_sha"]],
        capture_output=True, text=True)
    assert proc.returncode == 2
    assert "--expected-reconstruction-sha256" in proc.stderr


# ------------------------------------- 9. CLI end-to-end success
def test_cli_end_to_end_success(tmp_path):
    res_boot = _run(tmp_path, out="out_cli_boot")
    anchor = pl.read_parquet(Path(res_boot["out_dir"])
                             / "anchor_per_start.parquet")
    ref_path = tmp_path / "ref_cli.parquet"
    anchor.select("game_pk", "side", "pitcher",
                  pl.col("rps_anchor").alias("rps_w0_pooled")
                  ).write_parquet(ref_path)
    h = _write(tmp_path)
    out_dir = tmp_path / "out_cli"
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
         "--assessment", h["assessment_path"],
         "--raw-events", h["raw_path"],
         "--out-dir", str(out_dir),
         "--execution-ack", ACK,
         "--cohort-keys", h["lineups_path"], "--expected-cohort-hash",
         _cohort_hash_of(_lineups().select("game_pk", "side", "pitcher")),
         "--reconstruction-reference", str(ref_path),
         "--expected-reconstruction-sha256", _sha(ref_path),
         "--expected-pa-sha256", h["pa_sha"],
         "--expected-lineups-sha256", h["lineups_sha"],
         "--expected-assessment-sha256", h["assessment_sha"],
         "--min-fit-date-clusters", "2"],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    final = json.loads((out_dir / "receipt_final.json")
                       .read_text(encoding="utf-8"))
    assert final["acceptance"]["status"] == "COMPLETED"
    assert final["reconstruction"]["verified"] is True


# ------------------------------------------------ 10. write-once refuses
def test_write_once_refuses(tmp_path):
    res = _run(tmp_path, out="out_wo")
    existing = Path(res["out_dir"])
    h = _write(tmp_path)
    ref = _harvest_anchor_reference(existing)
    with pytest.raises(ValueError, match="write-once violation"):
        te.run_temporal_robustness(
            _pa_frame(), _lineups(), _assessment(), existing,
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=ref)
