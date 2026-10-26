"""Integration tests for the count-PMF calibration runner.

Verifies the cohort-hash verification, the fit -> persist ->
evaluation sequence, and the loading order.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import count_pmf_calibration as cpc  # noqa: E402
from pregame_pa_ext import count_pmf_calibration_runner as runner  # noqa: E402


def _cohort_hash(df):
    rows = sorted(
        ["%d|%s|%d" % (r["game_pk"], r["side"], r["pitcher"])
         for r in df.select("game_pk", "side", "pitcher")
         .iter_rows(named=True)])
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _synthetic_pmfs_frame(n_cal=1100, n_ev=1100, seed=9):
    """A registered-shaped PMF frame with two dev blocks."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_cal):
        pmf = rng.dirichlet(np.concatenate([[10.0], np.ones(23)]))
        k = int(rng.choice(24, p=pmf))
        rows.append((9000000 + i, "Top" if i % 2 else "Bot",
                     700000 + i, "2024-08-15",
                     "block_2024H2", k, pmf.tolist()))
    for i in range(n_ev):
        pmf = rng.dirichlet(np.ones(24) * 5)
        k = int(rng.choice(24, p=pmf))
        rows.append((9100000 + i, "Bot" if i % 2 else "Top",
                     800000 + i, "2025-04-15",
                     "block_2025H1", k, pmf.tolist()))
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "game_date": pl.Utf8, "block": pl.Utf8,
        "realized_k": pl.Int64, "pmf_baseline": pl.List(pl.Float64),
    }, orient="row")


def _expected_hashes(pmfs):
    cal = pmfs.filter(pl.col("block") == "block_2024H2")
    ev = pmfs.filter(pl.col("block") == "block_2025H1")
    return _cohort_hash(cal), _cohort_hash(ev)


def test_runner_sequence_and_outputs(tmp_path):
    """The runner must verify cohort hashes, execute fit -> persist ->
    evaluation in that order, and produce chained receipts."""
    pmfs = _synthetic_pmfs_frame()
    cal_h, ev_h = _expected_hashes(pmfs)
    out = tmp_path / "cal"
    res = runner.run_count_pmf_calibration(
        pmfs, out, expected_cal_hash=cal_h, expected_eval_hash=ev_h)
    # receipts
    assert (out / "receipt_initial.json").exists()
    assert (out / "receipt_final.json").exists()
    assert not (out / "failure_record.json").exists()
    # parameter artifact
    param_dir = out / "fitted_parameter"
    assert (param_dir / "fitted_a.json").exists()
    fin = res["receipt_final"]
    assert fin["acceptance"]["receipt_chain"] == \
        res["receipt_initial_sha256"]
    # code identity
    assert "runner_sha256" in fin["code_config"]["code_identity"]
    assert "calibration_module_sha256" in \
        fin["code_config"]["code_identity"]
    # expected cohort hashes recorded in initial receipt
    init = json.loads(
        (out / "receipt_initial.json").read_text(encoding="utf-8"))
    assert init["expected_cohort_hashes"]["calibration"] == cal_h
    assert init["expected_cohort_hashes"]["evaluation"] == ev_h
    assert init["hash_recipe"] != ""
    # actual cohort hashes in metrics
    assert res["metrics"]["calibration_cohort_hash"] == cal_h
    assert res["metrics"]["evaluation_cohort_hash"] == ev_h
    # per-start output
    assert (out / "calibration_per_start_v1.parquet").exists()
    ps = pl.read_parquet(out / "calibration_per_start_v1.parquet")
    assert ps.height == res["metrics"]["n_evaluation"]
    for col in ps.columns:
        assert ps[col].null_count() == 0, f"nulls in {col}"


def test_runner_write_once_guard(tmp_path):
    pmfs = _synthetic_pmfs_frame()
    cal_h, ev_h = _expected_hashes(pmfs)
    out = tmp_path / "cal"
    runner.run_count_pmf_calibration(
        pmfs, out, expected_cal_hash=cal_h, expected_eval_hash=ev_h)
    with pytest.raises(ValueError, match="write-once violation"):
        runner.run_count_pmf_calibration(
            pmfs, out, expected_cal_hash=cal_h,
            expected_eval_hash=ev_h)


def test_runner_failure_record_on_bad_input(tmp_path):
    """A bad input frame must produce a failure record and raise,
    preserving the initial receipt. The specific error (cohort hash
    mismatch or size) depends on the frame, but a failure record must
    always be written."""
    pmfs = _synthetic_pmfs_frame()
    # keep only eval-block rows (cal cohort is empty -> hash mismatch)
    bad = pmfs.filter(pl.col("block") != "block_2024H2")
    cal_h, ev_h = _expected_hashes(pmfs)
    out = tmp_path / "cal_fail"
    with pytest.raises(ValueError):
        runner.run_count_pmf_calibration(
            bad, out, expected_cal_hash=cal_h,
            expected_eval_hash=ev_h)
    assert (out / "receipt_initial.json").exists()
    assert (out / "failure_record.json").exists()
    assert not (out / "receipt_final.json").exists()
    rec = json.loads(
        (out / "failure_record.json").read_text(encoding="utf-8"))
    assert rec["failure"] is True
    assert rec["stage"] == "count_pmf_calibration"


def test_runner_rejects_cohort_hash_mismatch(tmp_path):
    """The runner must reject a cohort whose hash doesn't match the
    expected value (wrong population supplied)."""
    pmfs = _synthetic_pmfs_frame()
    wrong_cal = "0" * 64
    ev_h = _cohort_hash(pmfs.filter(pl.col("block") == "block_2025H1"))
    out = tmp_path / "cal_mismatch"
    with pytest.raises(ValueError, match="cohort hash mismatch"):
        runner.run_count_pmf_calibration(
            pmfs, out, expected_cal_hash=wrong_cal,
            expected_eval_hash=ev_h)
    assert (out / "failure_record.json").exists()


def test_runner_rejects_999_calibration_starts(tmp_path):
    """999 calibration starts: below the registered 1,000 threshold,
    fitting must never be called."""
    pmfs = _synthetic_pmfs_frame(n_cal=1100, n_ev=1100)
    cal_h, ev_h = _expected_hashes(pmfs)
    bad = pmfs.filter(pl.col("block") == "block_2024H2").head(999)
    combined = pl.concat([bad,
                          pmfs.filter(pl.col("block") == "block_2025H1")])
    out = tmp_path / "cal999"
    with pytest.raises(ValueError, match="1,000-start"):
        runner.run_count_pmf_calibration(
            combined, out, expected_cal_hash=cal_h,
            expected_eval_hash=ev_h)
    assert (out / "failure_record.json").exists()
    assert not (out / "receipt_final.json").exists()
    assert not (out / "fitted_parameter" / "fitted_a.json").exists()


def test_runner_accepts_exactly_1000_calibration_starts(tmp_path):
    """Exactly 1,000 calibration starts: pass the size gate and
    proceed to evaluation."""
    pmfs = _synthetic_pmfs_frame(n_cal=1100, n_ev=1100)
    cal_h, ev_h = _expected_hashes(pmfs)
    cal = pmfs.filter(pl.col("block") == "block_2024H2").head(1000)
    ev = pmfs.filter(pl.col("block") == "block_2025H1")
    trimmed = pl.concat([cal, ev])
    cal_h_t, ev_h_t = _expected_hashes(trimmed)
    out = tmp_path / "cal1000"
    res = runner.run_count_pmf_calibration(
        trimmed, out, expected_cal_hash=cal_h_t,
        expected_eval_hash=ev_h_t)
    assert res["metrics"]["n_calibration"] == 1000


def test_runner_rejects_protected_block_row(tmp_path):
    """A single confirm_2025H2 row in the input frame must be rejected
    before fitting."""
    pmfs = _synthetic_pmfs_frame(n_cal=1100, n_ev=1100)
    confirm_row = pmfs.head(1).with_columns(
        pl.lit("confirm_2025H2").alias("block"))
    combined = pl.concat([pmfs, confirm_row])
    out = tmp_path / "cal_confirm"
    with pytest.raises(ValueError, match="unexpected block labels"):
        runner.run_count_pmf_calibration(
            combined, out, expected_cal_hash="0" * 64,
            expected_eval_hash="0" * 64)


def test_runner_rejects_arbitrary_unexpected_label(tmp_path):
    """An unrecognized block label must also be rejected."""
    pmfs = _synthetic_pmfs_frame(n_cal=1100, n_ev=1100)
    weird = pmfs.head(1).with_columns(
        pl.lit("block_2026 preseason").alias("block"))
    combined = pl.concat([pmfs, weird])
    out = tmp_path / "cal_weird"
    with pytest.raises(ValueError, match="unexpected block labels"):
        runner.run_count_pmf_calibration(
            combined, out, expected_cal_hash="0" * 64,
            expected_eval_hash="0" * 64)


def test_runner_secondary_diagnostics_numerical(tmp_path):
    """The secondary diagnostics must match independently calculated
    values, not just field-existence assertions."""
    pmfs = _synthetic_pmfs_frame(n_cal=1100, n_ev=1100)
    cal_h, ev_h = _expected_hashes(pmfs)
    out = tmp_path / "cal_diag"
    res = runner.run_count_pmf_calibration(
        pmfs, out, expected_cal_hash=cal_h, expected_eval_hash=ev_h)
    sec = res["metrics"]["secondary"]
    # independently verify MAE for the frozen arm
    ps = pl.read_parquet(out / "calibration_per_start_v1.parquet")
    mean_ks = []
    for r in ps.iter_rows(named=True):
        pmfs_row = pmfs.filter(
            (pl.col("game_pk") == r["game_pk"])
            & (pl.col("pitcher") == r["pitcher"]))
        pmf = np.asarray(pmfs_row["pmf_baseline"][0], dtype=np.float64)
        mean_ks.append(float((pmf * np.arange(24)).sum()))
    actual = ps["realized_k"].to_numpy()
    assert sec["mae_frozen"] == pytest.approx(
        np.mean(np.abs(np.asarray(mean_ks) - actual)), abs=1e-9)
    # threshold reliability: predicted vs observed must be in [0,1]
    for r in sec["threshold_reliability"]:
        assert 0 <= r["mean_predicted"] <= 1
        assert 0 <= r["observed_frequency"] <= 1


def test_runner_rejects_cal_eval_key_overlap(tmp_path):
    """A (game_pk, side, pitcher) triple appearing in BOTH blocks must
    fail loud. Uses sufficiently large cohorts and correctly computed
    expected hashes so the overlap check (not the hash or size check)
    fires."""
    pmfs = _synthetic_pmfs_frame(n_cal=1100, n_ev=1100)
    cal_part = pmfs.filter(pl.col("block") == "block_2024H2")
    # take 50 cal rows and copy them with the eval block label
    cal_rows = cal_part.head(50)
    duplicated = cal_rows.with_columns(
        pl.lit("block_2025H1").alias("block"))
    combined = pl.concat([pmfs, duplicated])
    cal_h, ev_h = _expected_hashes(combined)
    out = tmp_path / "cal_overlap"
    with pytest.raises(ValueError, match="key overlap"):
        runner.run_count_pmf_calibration(
            combined, out, expected_cal_hash=cal_h,
            expected_eval_hash=ev_h)


def test_runner_observes_evaluation_load_after_persist(tmp_path):
    """The runner's code path must READ evaluation outcomes only AFTER
    the parameter artifact has been persisted."""
    pmfs = _synthetic_pmfs_frame()
    cal_h, ev_h = _expected_hashes(pmfs)
    out = tmp_path / "cal"

    call_order = []
    original_freeze = cpc.GuardedEvaluationLoader.freeze
    original_load = cpc.GuardedEvaluationLoader.load

    def spy_freeze(self, a):
        call_order.append("freeze")
        return original_freeze(self, a)

    def spy_load(self, pmfs, outcomes):
        call_order.append("load_eval")
        return original_load(self, pmfs, outcomes)

    import unittest.mock as mock
    with mock.patch.object(cpc.GuardedEvaluationLoader, "freeze",
                           spy_freeze), \
         mock.patch.object(cpc.GuardedEvaluationLoader, "load",
                           spy_load):
        res = runner.run_count_pmf_calibration(
            pmfs, out, expected_cal_hash=cal_h,
            expected_eval_hash=ev_h)

    assert "freeze" in call_order
    assert "load_eval" in call_order
    assert call_order.index("freeze") < call_order.index("load_eval")
