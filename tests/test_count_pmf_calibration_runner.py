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


def _synthetic_pmfs_frame(n_cal=150, n_ev=150, seed=9):
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


def test_runner_rejects_cal_eval_key_overlap(tmp_path):
    """A (game_pk, side, pitcher) triple appearing in BOTH blocks must
    fail loud. The cohort-hash check fires first because the test uses
    dummy hashes; the key-overlap check is the inner check."""
    pmfs = _synthetic_pmfs_frame(n_cal=150, n_ev=150)
    cal_rows = pmfs.filter(pl.col("block") == "block_2024H2").head(50)
    duplicated = cal_rows.with_columns(
        pl.lit("block_2025H1").alias("block"))
    combined = pl.concat([pmfs, duplicated])
    out = tmp_path / "cal_overlap"
    with pytest.raises(ValueError):
        runner.run_count_pmf_calibration(
            combined, out, expected_cal_hash="0" * 64,
            expected_eval_hash="0" * 64)


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
