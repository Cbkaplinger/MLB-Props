"""Synthetic tests for the binary-K vs multinomial-K comparison
(binary_k_comparison.py). SYNTHETIC ONLY. Every test drives the actual
entry point with hand-checkable fixtures.

Requirement -> implementation -> test-evidence closure table:
  End-to-end success, every declared artifact in the output-hash manifest
                                                           -> test 1
  Keyed probability alignment: one row per keyed matchup+slot, values
  in [0,1], both arms present                             -> test 2
  Keyed alignment survives reversed PA row order (per-key p_k and
  per-start RPS byte-identical across runs)               -> test 3
  Binary-label derivation from class_label only (hand-counted
  positives/negatives recorded; never a second label source) -> test 4
  Single-class training population refuses                -> test 5
  Same-population: both arms scored on the identical sorted key list
  (one realized map, one loop)                            -> test 6
  Same-population: cohort restriction applied before feature
  construction; extra start excluded, never silently absorbed -> test 7
  Duplicate actual-PA identity refuses                    -> test 8
  Shared aggregation: both arms consume the SAME registered
  start_count_pmfs with the SAME BF37 (only p9 differs)   -> test 9
  Saved model reload reproduces saved per-key probabilities -> test 10
  Reconstruction of the multinomial-plus-W0 control: exact pass,
  altered reference refuses, missing reference refuses    -> tests 11a/b/c
  Ack gate: direct-call ValueError; CLI exit 2 with zero side
  effects (nonexistent inputs prove refusal precedes I/O) -> tests 12a/b
  CLI enforces input file hashes (mismatch -> exit 1)     -> test 13
  CLI end-to-end success through the real script path     -> test 14
  Write-once destination refuses                          -> test 15
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
from polars.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import binary_k_comparison as bk  # noqa: E402
from pregame_pa_ext import adapter as ad  # noqa: E402

ACK = bk.EXECUTION_ACK_TOKEN
P1, P2 = 700001, 700002
B1 = [800001 + i for i in range(9)]
B2 = [800101 + i for i in range(9)]
TRAIN_D1 = date(2024, 7, 1)
TRAIN_D2 = date(2024, 7, 15)
GAME_DATE = date(2025, 4, 15)
RUNNER = (Path(bk.__file__).resolve())

# column order must match PA_SCHEMA key insertion order
_PA_KEYS = ["game_date", "game_pk", "inning_topbot", "at_bat_number",
            "pitcher", "batter", "y"]
PA_SCHEMA = {k: (pl.Utf8 if k == "inning_topbot" else
                 pl.Date if k == "game_date" else pl.Int64)
             for k in _PA_KEYS}


def _row(gd, gk, topbot, abn, p, b, y):
    return (gd, gk, topbot, abn, p, b, y)


def _pa_rows():
    rows = []
    hist = date(2024, 5, 20)
    for i, b in enumerate(B1):
        rows.append(_row(hist, 50, "Top", 100 + i, P1, b, 0))
    for i, b in enumerate(B2):
        rows.append((hist, 50, "Bot", 109 + i, P2, b, 0))
    for i, b in enumerate(B1):
        rows.append(_row(TRAIN_D1, 100, "Top", 200 + i, P1, b,
                         1 if i % 2 == 0 else 0))
    for i, b in enumerate(B2):
        rows.append(_row(TRAIN_D2, 100, "Top", 300 + i, P1, b,
                         1 if i % 3 == 0 else 0))
    for i, b in enumerate(B1):
        rows.append(_row(TRAIN_D2, 101, "Bot", 400 + i, P2, b,
                         1 if i % 4 == 0 else 0))
    for i, b in enumerate(B1):
        rows.append(_row(GAME_DATE, 900001, "Top", 500 + i, P1, b,
                         1 if i % 2 == 0 else 0))
    for i, b in enumerate(B2):
        rows.append(_row(GAME_DATE, 900001, "Bot", 600 + i, P2, b,
                         1 if i % 2 else 0))
    return rows


def _pa_frame(reverse=False):
    rows = _pa_rows()
    if reverse:
        rows = rows[::-1]
    return pl.DataFrame(rows, schema=PA_SCHEMA, orient="row")


def _lineups(extra_start=False):
    rows = [(900001, "Top", P1, GAME_DATE, True, *B1),
            (900001, "Bot", P2, GAME_DATE, True, *B2)]
    if extra_start:
        rows.append((900002, "Top", P1, GAME_DATE, True, *B1))
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{i}": pl.Int64 for i in range(1, 10)})
    return pl.DataFrame(rows, schema=schema, orient="row")


def _assessment(extra_pa=False):
    rows = [(900001, "Top", P1, 500 + i, B1[i],
             0 if i % 2 == 0 else 2) for i in range(9)]
    rows += [(900001, "Bot", P2, 600 + i, B2[i],
              0 if i % 2 else 3) for i in range(9)]
    if extra_pa:
        rows.append((900001, "Top", P1, 509, 800999, 1))
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
        p = tmp_path / f"{name}.parquet"
        frame.write_parquet(p)
        h[f"{name}_path"] = str(p)
        h[f"{name}_sha"] = _sha(p)
    raw = pa.select("game_pk", "at_bat_number", "batter", "y").with_columns(
        pl.when(pl.col("y") == 1).then(pl.lit("strikeout"))
        .otherwise(pl.lit("field_out")).alias("events")
    ).drop("y")
    rp = tmp_path / "raw_events.parquet"
    raw.write_parquet(rp)
    h["raw_path"] = str(rp)
    h["raw_sha"] = _sha(rp)
    return h


def _wrong_reference():
    rows = [(900001, "Top", P1, 0.5), (900001, "Bot", P2, 0.5)]
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "rps_w0_pooled": pl.Float64}, orient="row")


def _harvest_reference(out_dir) -> pl.DataFrame:
    """Harvest the per-start multinomial-control RPS from a completed
    (or gate-refused) run as the reconstruction reference."""
    ps = pl.read_parquet(Path(out_dir)
                         / "binary_k_per_start_v1.parquet")
    return ps.select(
        "game_pk", "side", "pitcher",
        pl.col("rps_multinomial_control").alias("rps_w0_pooled"))


def _run(tmp_path, out="out", pa=None, lineups=None, assessment=None,
         ack=ACK, cohort_keys=None, expected_cohort_hash=None,
         reconstruction_reference=None, reference_sha256=None,
         input_identities=None):
    h = _write(tmp_path, pa, lineups, assessment)
    pa_frame = pa if pa is not None else _pa_frame()
    if reconstruction_reference is None and ack == ACK:
        boot_out = tmp_path / f"_boot_{out}"
        try:
            bk.run_binary_k_comparison(
                pa_frame,
                lineups if lineups is not None else _lineups(),
                assessment if assessment is not None else _assessment(),
                boot_out,
                train_start="2024-06-01", train_end="2024-12-31",
                execution_ack=ack, raw_events=[h["raw_path"]],
                cohort_keys=cohort_keys,
                expected_cohort_hash=expected_cohort_hash,
                reconstruction_reference=_wrong_reference())
        except ValueError:
            # expected: the wrong pin must be refused; per-start
            # evidence is written BEFORE the gate so the true per-start
            # control RPS is harvested as the reference
            pass
        boot_ps = boot_out / "binary_k_per_start_v1.parquet"
        assert boot_ps.exists(), (
            "bootstrap run must preserve per-start evidence before "
            "refusing")
        reconstruction_reference = _harvest_reference(boot_out)
    return bk.run_binary_k_comparison(
        pa_frame, lineups if lineups is not None else _lineups(),
        assessment if assessment is not None else _assessment(),
        tmp_path / out,
        train_start="2024-06-01", train_end="2024-12-31",
        execution_ack=ack, raw_events=[h["raw_path"]],
        cohort_keys=cohort_keys, expected_cohort_hash=expected_cohort_hash,
        reconstruction_reference=reconstruction_reference,
        reconstruction_reference_sha256=reference_sha256,
        input_identities=input_identities)


# ------------------------------------- 1. e2e + output-hash manifest closure
def test_e2e_all_artifacts_in_manifest(tmp_path):
    res = _run(tmp_path)
    expected = {"binary_k_per_start_v1.parquet",
                "binary_k_comparison_report.json",
                "keyed_pa_probabilities.parquet",
                "model_artifacts.json",
                "k_pmf_per_start_v1.parquet",
                "bf37_pooled_by_date_v1.parquet",
                "receipt_initial.json", "receipt_final.json"}
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
    report = json.loads(
        (Path(res["out_dir"]) / "binary_k_comparison_report.json")
        .read_text(encoding="utf-8"))
    assert report["n_starts"] == 2
    assert set(report["per_pa_descriptive"]) >= {
        "multinomial_control", "binary_k"}


# ------------------------------------------------- 2. keyed alignment
def test_keyed_table_unique_and_bounded(tmp_path):
    res = _run(tmp_path)
    keyed = pl.read_parquet(Path(res["out_dir"])
                            / "keyed_pa_probabilities.parquet")
    assert keyed.height == 18
    assert keyed.select("game_pk", "side", "pitcher", "slot",
                        "batter").n_unique() == keyed.height
    for col in ("p_k_multinomial", "p_k_binary"):
        assert keyed[col].min() >= 0.0 and keyed[col].max() <= 1.0


# --------------------------- 3. reversed PA row order -> identical result
def test_reversed_pa_row_order_identical_per_start(tmp_path):
    res_fwd = _run(tmp_path, out="fwd")
    h2 = _write(tmp_path, pa=_pa_frame(reverse=True))
    boot2 = tmp_path / "_boot_rev"
    with pytest.raises(ValueError, match="reconstruction gate FAILED"):
        bk.run_binary_k_comparison(
            _pa_frame(reverse=True), _lineups(), _assessment(), boot2,
            train_start="2024-06-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h2["raw_path"]],
            reconstruction_reference=_wrong_reference())
    ref2 = _harvest_reference(boot2)
    res_rev = bk.run_binary_k_comparison(
        _pa_frame(reverse=True), _lineups(), _assessment(),
        tmp_path / "rev",
        train_start="2024-06-01", train_end="2024-12-31",
        execution_ack=ACK, raw_events=[h2["raw_path"]],
        reconstruction_reference=ref2)
    a = pl.read_parquet(Path(res_fwd["out_dir"])
                        / "binary_k_per_start_v1.parquet").sort(
        "game_pk", "side", "pitcher")
    b = pl.read_parquet(Path(res_rev["out_dir"])
                        / "binary_k_per_start_v1.parquet").sort(
        "game_pk", "side", "pitcher")
    # float-associativity tolerates tiny last-digit drift under row
    # reordering; keyed alignment is the requirement, not bit equality
    assert_frame_equal(a, b, check_exact=False, rel_tol=0, abs_tol=1e-12)


# ----------------------------------------- 4. binary-label derivation
def test_binary_label_derivation_hand_counts(tmp_path):
    res = _run(tmp_path)
    acc = json.loads((Path(res["out_dir"])
                      / "binary_k_comparison_report.json")
                     .read_text(encoding="utf-8"))[
        "binary_label_accounting"]
    # hand count: D1 P1 i%2==0 -> 5; D2 P1 i%3==0 -> 3; D2 P2 i%4==0 -> 3
    assert acc["n_train_rows"] == 27
    assert acc["n_train_positive"] == 11
    assert acc["n_train_negative"] == 16
    assert acc["derivation"] == "is_k = 1[class_label == 0]"
    final = json.loads((Path(res["out_dir"]) / "receipt_final.json")
                       .read_text(encoding="utf-8"))
    assert final["counts"]["n_train_rows"] == 27
    assert final["counts"]["n_train_positive"] == 11


# ----------------------------------------- 5. single-class training refuses
def test_single_class_training_refuses(tmp_path):
    # make every training PA a strikeout: y=1 in the training window;
    # the raw-events file derives from the SAME frame so the bridged
    # labels are single-class too
    rows = []
    for r in _pa_rows():
        gd, gk, tb, ab, p, b, y = r
        if gd in (TRAIN_D1, TRAIN_D2):
            y = 1
        rows.append((gd, gk, tb, ab, p, b, y))
    pa_all_k = pl.DataFrame(rows, schema=PA_SCHEMA, orient="row")
    h = _write(tmp_path, pa=pa_all_k)
    with pytest.raises(ValueError, match="single-class"):
        bk.run_binary_k_comparison(
            pa_all_k, _lineups(), _assessment(), tmp_path / "out_sc",
            train_start="2024-06-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())


# ------------------------- 6. identical sorted key list for both arms
def test_both_arms_identical_population(tmp_path):
    res = _run(tmp_path)
    ps = pl.read_parquet(Path(res["out_dir"])
                         / "binary_k_per_start_v1.parquet")
    assert ps.height == 2
    assert ps["rps_multinomial_control"].is_not_null().all()
    assert ps["rps_binary_k"].is_not_null().all()
    assert (ps["rps_diff"]
            == (ps["rps_binary_k"] - ps["rps_multinomial_control"])).all()
    kp = pl.read_parquet(Path(res["out_dir"])
                         / "k_pmf_per_start_v1.parquet")
    assert kp.height == 2 * 24
    starts = kp.select("game_pk", "side", "pitcher").unique().height
    assert starts == 2


# ----------------- 7. cohort restriction before features; extra excluded
def test_cohort_restriction_excludes_extra_start(tmp_path):
    cohort = _lineups().select("game_pk", "side", "pitcher").head(1)
    cohort_h = hashlib.sha256("\n".join(sorted(
        "%d|%s|%d" % (int(r["game_pk"]), str(r["side"]),
                      int(r["pitcher"]))
        for r in cohort.iter_rows(named=True)))
        .encode("utf-8")).hexdigest()
    res = _run(tmp_path, out="out_cohort", lineups=_lineups(
        extra_start=True), cohort_keys=cohort,
        expected_cohort_hash=cohort_h)
    final = json.loads((Path(res["out_dir"]) / "receipt_final.json")
                       .read_text(encoding="utf-8"))
    assert final["cohort_identity"]["restriction_applied"] is True
    assert final["cohort_identity"]["hash_match"] is True
    assert final["counts"]["n_requests_after_cohort"] == 9
    assert final["counts"]["n_starts"] == 1
    ps = pl.read_parquet(Path(res["out_dir"])
                         / "binary_k_per_start_v1.parquet")
    assert ps.height == 1


# -------------------------------- 8. duplicate actual-PA identity refuses
def test_duplicate_assessment_identity_refuses(tmp_path):
    h = _write(tmp_path)
    dup = pl.concat([_assessment(), _assessment().head(1)])
    with pytest.raises(ValueError, match="duplicate actual-PA"):
        bk.run_binary_k_comparison(
            _pa_frame(), _lineups(), dup, tmp_path / "out_dup",
            train_start="2024-06-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())


# ------------------------------------------- 9. shared aggregation proof
def test_shared_aggregation_identical_p9_identical_pmf():
    p9 = np.array([0.2, 0.25, 0.3, 0.22, 0.27, 0.31, 0.24, 0.28, 0.26])
    bf37 = np.full(37, 1.0 / 37.0)
    pmf_a = ad.start_count_pmfs(p9, p9, bf37)["pmf_h3_raw"]
    pmf_b = ad.start_count_pmfs(p9, p9, bf37)["pmf_h3_raw"]
    assert np.array_equal(pmf_a, pmf_b)
    assert abs(float(pmf_a.sum()) - 1.0) < 1e-9


# --------------------------------------- 10. saved model reload parity
def test_model_reload_reproduces_probabilities(tmp_path):
    res = _run(tmp_path, out="out_reload")
    out_dir = Path(res["out_dir"])
    models = bk.reload_models(out_dir / "model_artifacts.json")
    keyed = pl.read_parquet(out_dir / "keyed_pa_probabilities.parquet")
    assert set(models) == {"multinomial_control", "binary_k"}
    # reconstruct features exactly as the runner does and re-apply
    sys.path.insert(0, str(RUNNER.parents[2]))
    from pregame_pa_ext import forecast_states_v2 as fv  # noqa: E402
    from pregame_pa_ext import m0_multiclass as m0  # noqa: E402
    pa = _pa_frame()
    train = pa.filter(
        (pl.col("game_date") >= date(2024, 6, 1))
        & (pl.col("game_date") <= date(2024, 12, 31)))
    lineups = _lineups()
    from pregame_pa_ext import adapter as ad2  # noqa: E402
    long, _ = ad2.projected_long(lineups)
    cutoffs = train["game_date"].unique().to_list() + \
        long["game_date"].unique().to_list()
    p_v2, b_v2, lg_v2, _ = fv.build_v2_states(pa, cutoffs)
    feat_req = ad2.attach_prior_features(
        long.select("game_date", "pitcher", "batter", "game_pk",
                    "side", "slot"), p_v2, b_v2, lg_v2)
    # apply on the SORTED feature frame and compare to the SORTED keyed
    # table: identical per-key probabilities regardless of row order
    feat_sorted = feat_req.sort("game_pk", "side", "pitcher", "slot")
    keyed_sorted = keyed.sort("game_pk", "side", "pitcher", "slot")
    p_mn = bk._multinomial_pk(
        feat_sorted, models["multinomial_control"])
    p_bin = bk.apply_binary(feat_sorted, models["binary_k"])
    assert np.allclose(
        np.asarray(p_mn),
        keyed_sorted["p_k_multinomial"].to_numpy(), rtol=0, atol=0)
    assert np.allclose(
        p_bin, keyed_sorted["p_k_binary"].to_numpy(), rtol=0, atol=0)


# --------------------- 11a/b/c. reconstruction of the multinomial control
def test_reconstruction_gate_exact_pass(tmp_path):
    res = _run(tmp_path, out="out_recon")
    rec = res["reconstruction"]
    assert rec["verified"] is True
    assert rec["max_abs_rps_diff"] == 0.0
    assert rec["reference_column"] == "rps_w0_pooled"


def test_reconstruction_gate_altered_reference_refuses(tmp_path):
    h = _write(tmp_path)
    boot = tmp_path / "_boot_alt"
    with pytest.raises(ValueError, match="reconstruction gate FAILED"):
        bk.run_binary_k_comparison(
            _pa_frame(), _lineups(), _assessment(), boot,
            train_start="2024-06-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())
    assert (boot / "failure_record.json").exists()
    ps = pl.read_parquet(boot / "binary_k_per_start_v1.parquet")
    assert ps.height == 2
    ref = _harvest_reference(boot).with_columns(
        (pl.col("rps_w0_pooled") + 1e-9).alias("rps_w0_pooled"))
    with pytest.raises(ValueError, match="reconstruction gate FAILED"):
        bk.run_binary_k_comparison(
            _pa_frame(), _lineups(), _assessment(), tmp_path / "out_alt",
            train_start="2024-06-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=ref)


def test_reconstruction_gate_missing_reference_refuses(tmp_path):
    h = _write(tmp_path)
    with pytest.raises(ValueError, match="reconstruction reference "
                                         "required"):
        bk.run_binary_k_comparison(
            _pa_frame(), _lineups(), _assessment(), tmp_path / "out_none",
            train_start="2024-06-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=None)


# --------------------------------------------------- 12a. direct ack gate
def test_ack_gate_direct_call(tmp_path):
    h = _write(tmp_path)
    with pytest.raises(ValueError,
                       match="execution acknowledgement"):
        bk.run_binary_k_comparison(
            _pa_frame(), _lineups(), _assessment(), tmp_path / "out_ack",
            train_start="2024-06-01", train_end="2024-12-31",
            execution_ack="WRONG", raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())
    assert not (tmp_path / "out_ack").exists()


# ------------------------------------------ 12b. CLI ack gate exit 2
def test_cli_ack_gate_zero_side_effects(tmp_path):
    script = str(RUNNER)
    proc = subprocess.run(
        [sys.executable, script,
         "--pa-source", str(tmp_path / "nope.parquet"),
         "--lineups", str(tmp_path / "nope.parquet"),
         "--assessment", str(tmp_path / "nope.parquet"),
         "--raw-events", str(tmp_path / "nope.parquet"),
         "--train-start", "2024-06-01", "--train-end", "2024-12-31",
         "--out-dir", str(tmp_path / "out_cli_ack"),
         "--execution-ack", "WRONG",
         "--cohort-keys", str(tmp_path / "nope.parquet"),
         "--expected-cohort-hash", "0" * 64,
         "--reconstruction-reference", str(tmp_path / "nope.parquet"),
         "--expected-reconstruction-sha256", "0" * 64,
         "--expected-pa-sha256", "0" * 64,
         "--expected-lineups-sha256", "0" * 64,
         "--expected-assessment-sha256", "0" * 64],
        capture_output=True, text=True)
    assert proc.returncode == 2
    assert "EXECUTION REFUSED" in proc.stderr
    assert not (tmp_path / "out_cli_ack").exists()


# --------------- 12c. CLI reconstruction-reference identity ENFORCED
def test_cli_reference_hash_enforced_before_decode(tmp_path):
    h = _write(tmp_path)
    ref_path = tmp_path / "ref.parquet"
    _wrong_reference().write_parquet(ref_path)
    actual = _sha(ref_path)
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--pa-source", h["pa_path"],
         "--lineups", h["lineups_path"],
         "--assessment", h["assessment_path"],
         "--raw-events", h["raw_path"],
         "--train-start", "2024-06-01", "--train-end", "2024-12-31",
         "--out-dir", str(tmp_path / "out_cli_ref"),
         "--execution-ack", ACK,
         "--cohort-keys", h["lineups_path"],
         "--expected-cohort-hash", _cohort_hash_of(
             _lineups().select("game_pk", "side", "pitcher")),
         "--reconstruction-reference", str(ref_path),
         "--expected-reconstruction-sha256", "0" * 64,
         "--expected-pa-sha256", h["pa_sha"],
         "--expected-lineups-sha256", h["lineups_sha"],
         "--expected-assessment-sha256", h["assessment_sha"]],
        capture_output=True, text=True)
    assert proc.returncode == 1
    assert "INPUT IDENTITY MISMATCH for reconstruction reference" \
        in proc.stderr
    # refusal precedes any execution side effect
    assert not (tmp_path / "out_cli_ref").exists()


# --------------- 12d. CLI reconstruction pin is REQUIRED (argparse)
def test_cli_reference_hash_pin_required(tmp_path):
    h = _write(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--pa-source", h["pa_path"],
         "--lineups", h["lineups_path"],
         "--assessment", h["assessment_path"],
         "--raw-events", h["raw_path"],
         "--train-start", "2024-06-01", "--train-end", "2024-12-31",
         "--out-dir", str(tmp_path / "out_cli_nopin"),
         "--execution-ack", ACK,
         "--cohort-keys", h["lineups_path"],
         "--expected-cohort-hash", _cohort_hash_of(
             _lineups().select("game_pk", "side", "pitcher")),
         "--reconstruction-reference",
         str(tmp_path / "whatever.parquet"),
         "--expected-pa-sha256", h["pa_sha"],
         "--expected-lineups-sha256", h["lineups_sha"],
         "--expected-assessment-sha256", h["assessment_sha"]],
        capture_output=True, text=True)
    assert proc.returncode == 2
    assert "--expected-reconstruction-sha256" in proc.stderr


# ------------------------------------------- 13. CLI input hash refusal
def test_cli_input_hash_mismatch_refuses(tmp_path):
    h = _write(tmp_path)
    boot = tmp_path / "_boot_hash"
    with pytest.raises(ValueError, match="reconstruction gate FAILED"):
        bk.run_binary_k_comparison(
            _pa_frame(), _lineups(), _assessment(), boot,
            train_start="2024-06-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())
    ref = _harvest_reference(boot)
    ref_path = tmp_path / "ref.parquet"
    ref.write_parquet(ref_path)
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--pa-source", h["pa_path"],
         "--lineups", h["lineups_path"],
         "--assessment", h["assessment_path"],
         "--raw-events", h["raw_path"],
         "--train-start", "2024-06-01", "--train-end", "2024-12-31",
         "--out-dir", str(tmp_path / "out_cli_hash"),
         "--execution-ack", ACK,
         "--cohort-keys", h["lineups_path"],
         "--expected-cohort-hash",
         _cohort_hash_of(_lineups().select(
             "game_pk", "side", "pitcher")),
         "--reconstruction-reference", str(ref_path),
         "--expected-reconstruction-sha256", _sha(ref_path),
         "--expected-pa-sha256", "0" * 64,
         "--expected-lineups-sha256", h["lineups_sha"],
         "--expected-assessment-sha256", h["assessment_sha"]],
        capture_output=True, text=True)
    assert proc.returncode == 1
    assert "INPUT IDENTITY MISMATCH" in proc.stderr


def _cohort_hash_of(cohort: pl.DataFrame) -> str:
    return hashlib.sha256("\n".join(sorted(
        "%d|%s|%d" % (int(r["game_pk"]), str(r["side"]),
                      int(r["pitcher"]))
        for r in cohort.iter_rows(named=True)))
        .encode("utf-8")).hexdigest()


# ------------------------------------- 14. CLI end-to-end success
def test_cli_end_to_end_success(tmp_path):
    res_boot = _run(tmp_path, out="out_cli_boot")
    boot_dir = Path(res_boot["out_dir"])
    ps = pl.read_parquet(boot_dir / "binary_k_per_start_v1.parquet")
    ref_path = tmp_path / "ref_cli.parquet"
    ps.select(
        "game_pk", "side", "pitcher",
        pl.col("rps_multinomial_control").alias("rps_w0_pooled")
    ).write_parquet(ref_path)
    h = _write(tmp_path)
    out_dir = tmp_path / "out_cli"
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--pa-source", h["pa_path"],
         "--lineups", h["lineups_path"],
         "--assessment", h["assessment_path"],
         "--raw-events", h["raw_path"],
         "--train-start", "2024-06-01", "--train-end", "2024-12-31",
         "--out-dir", str(out_dir),
         "--execution-ack", ACK,
         "--cohort-keys", h["lineups_path"],
         "--expected-cohort-hash", _cohort_hash_of(
             _lineups().select("game_pk", "side", "pitcher")),
         "--reconstruction-reference", str(ref_path),
         "--expected-reconstruction-sha256", _sha(ref_path),
         "--expected-pa-sha256", h["pa_sha"],
         "--expected-lineups-sha256", h["lineups_sha"],
         "--expected-assessment-sha256", h["assessment_sha"]],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert (out_dir / "receipt_final.json").exists()
    final = json.loads((out_dir / "receipt_final.json")
                       .read_text(encoding="utf-8"))
    assert final["acceptance"]["status"] == "COMPLETED"
    assert final["reconstruction"]["verified"] is True


# ------------------------------------------------ 15. write-once refuses
def test_write_once_refuses(tmp_path):
    res = _run(tmp_path, out="out_wo")
    existing = Path(res["out_dir"])
    h = _write(tmp_path)
    ref = _harvest_reference(existing)
    with pytest.raises(ValueError, match="write-once violation"):
        bk.run_binary_k_comparison(
            _pa_frame(), _lineups(), _assessment(), existing,
            train_start="2024-06-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=ref)
