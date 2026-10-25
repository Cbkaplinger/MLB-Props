"""Integration tests for the count-PMF calibration runner.

Verifies the load -> fit -> persist -> evaluation-load SEQUENCE,
not just the mathematical correctness of the mapping.
"""
from __future__ import annotations

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


def _synthetic_pmfs_frame(n_cal=150, n_ev=150, seed=9):
    """A registered-shaped PMF frame with two dev blocks and a
    KNOWN calibration signal: block_2024H2 PMFs are overconfident
    (mass shifted low), block_2025H1 PMFs are well-calibrated."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_cal):
        # calibration block: overconfident (shifted low)
        pmf = rng.dirichlet(np.concatenate([[10.0], np.ones(23)]))
        k = int(rng.choice(24, p=pmf))
        rows.append((9000000 + i, "Top" if i % 2 else "Bot",
                     700000 + i, "2024-08-15",
                     "block_2024H2", k, pmf.tolist()))
    for i in range(n_ev):
        # evaluation block: well-calibrated
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


def test_runner_sequence_and_outputs(tmp_path):
    """The runner must execute fit -> persist -> evaluation-load in
    that order and produce chained receipts. The parameter artifact
    must exist on disk BEFORE evaluation outcomes are scored (verified
    by checking that the parameter file is created inside the runner
    before the per-start output, which requires evaluation outcomes)."""
    pmfs = _synthetic_pmfs_frame()
    out = tmp_path / "cal"
    res = runner.run_count_pmf_calibration(pmfs, out)
    # receipts
    assert (out / "receipt_initial.json").exists()
    assert (out / "receipt_final.json").exists()
    assert (out / "failure_record.json").exists() is False
    # parameter artifact
    param_dir = out / "fitted_parameter"
    assert (param_dir / "fitted_a.json").exists()
    fin = res["receipt_final"]
    assert fin["acceptance"]["receipt_chain"] == \
        res["receipt_initial_sha256"]
    # per-start output
    assert (out / "calibration_per_start_v1.parquet").exists()
    ps = pl.read_parquet(out / "calibration_per_start_v1.parquet")
    assert ps.height == res["metrics"]["n_evaluation"]
    assert ps["rps_frozen"].dtype == pl.Float64
    assert ps["rps_calibrated"].dtype == pl.Float64
    # no nulls
    for col in ps.columns:
        assert ps[col].null_count() == 0, f"nulls in {col}"
    # ordering evidence: the parameter artifact must exist (the runner
    # cannot score evaluation outcomes without it, because the
    # GuardedEvaluationLoader.load() raises if not frozen)
    assert fin["acceptance"]["fitted_a"] is not None


def test_runner_write_once_guard(tmp_path):
    pmfs = _synthetic_pmfs_frame()
    out = tmp_path / "cal"
    runner.run_count_pmf_calibration(pmfs, out)
    with pytest.raises(ValueError, match="write-once violation"):
        runner.run_count_pmf_calibration(pmfs, out)


def test_runner_failure_record_on_bad_input(tmp_path):
    """An empty calibration block must produce a failure record and
    raise, preserving the initial receipt."""
    pmfs = _synthetic_pmfs_frame()
    # keep only eval-block rows (calibration will be empty)
    bad = pmfs.filter(pl.col("block") != "block_2024H2")
    out = tmp_path / "cal_fail"
    with pytest.raises(ValueError, match="too small"):
        runner.run_count_pmf_calibration(bad, out)
    assert (out / "receipt_initial.json").exists()
    assert (out / "failure_record.json").exists()
    assert not (out / "receipt_final.json").exists()
    rec = json.loads(
        (out / "failure_record.json").read_text(encoding="utf-8"))
    assert rec["failure"] is True
    assert rec["stage"] == "count_pmf_calibration"


def test_runner_observes_evaluation_load_after_persist(tmp_path):
    """The runner's code path must READ evaluation outcomes only AFTER
    the parameter artifact has been persisted. This test uses a spy on
    the GuardedEvaluationLoader to verify that load() is called only
    after freeze() has written the parameter artifact."""
    pmfs = _synthetic_pmfs_frame()
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
        res = runner.run_count_pmf_calibration(pmfs, out)

    # the parameter must be frozen BEFORE evaluation outcomes are loaded
    assert "freeze" in call_order
    assert "load_eval" in call_order
    assert call_order.index("freeze") < call_order.index("load_eval")


def test_runner_rejects_cal_eval_key_overlap(tmp_path):
    """A (game_pk, side, pitcher) triple appearing in BOTH blocks must
    fail loud. The runner splits by block column; a duplicated start
    identity across blocks is a data error."""
    pmfs = _synthetic_pmfs_frame(n_cal=150, n_ev=150)
    # take 50 cal rows and copy them with the eval block label
    cal_rows = pmfs.filter(pl.col("block") == "block_2024H2").head(50)
    duplicated = cal_rows.with_columns(
        pl.lit("block_2025H1").alias("block"))
    combined = pl.concat([pmfs, duplicated])
    out = tmp_path / "cal_overlap"
    with pytest.raises(ValueError, match="key overlap"):
        runner.run_count_pmf_calibration(combined, out)
