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

# Every synthetic test call site passes the token explicitly: the
# synthetic-test route is an acknowledged route, not an unacknowledged
# bypass. The token is a technical execution-acceptance gate only and
# is NOT evidence of owner authorization.
ACK = runner.EXECUTION_ACK_TOKEN


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
            pmfs, out, execution_ack=ACK,
            expected_cal_hash=cal_h, expected_eval_hash=ev_h)
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
            pmfs, out, execution_ack=ACK,
            expected_cal_hash=cal_h, expected_eval_hash=ev_h)
    with pytest.raises(ValueError, match="write-once violation"):
        runner.run_count_pmf_calibration(
            pmfs, out, execution_ack=ACK,
            expected_cal_hash=cal_h, expected_eval_hash=ev_h)


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
            bad, out, execution_ack=ACK,
            expected_cal_hash=cal_h, expected_eval_hash=ev_h)
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
            pmfs, out, execution_ack=ACK,
            expected_cal_hash=wrong_cal, expected_eval_hash=ev_h)
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
            combined, out, execution_ack=ACK,
            expected_cal_hash=cal_h, expected_eval_hash=ev_h)
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
        trimmed, out, execution_ack=ACK,
        expected_cal_hash=cal_h_t, expected_eval_hash=ev_h_t)
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
            combined, out, execution_ack=ACK,
            expected_cal_hash="0" * 64, expected_eval_hash="0" * 64)


def test_runner_rejects_arbitrary_unexpected_label(tmp_path):
    """An unrecognized block label must also be rejected."""
    pmfs = _synthetic_pmfs_frame(n_cal=1100, n_ev=1100)
    weird = pmfs.head(1).with_columns(
        pl.lit("block_2026 preseason").alias("block"))
    combined = pl.concat([pmfs, weird])
    out = tmp_path / "cal_weird"
    with pytest.raises(ValueError, match="unexpected block labels"):
        runner.run_count_pmf_calibration(
            combined, out, execution_ack=ACK,
            expected_cal_hash="0" * 64, expected_eval_hash="0" * 64)


def test_runner_secondary_diagnostics_numerical(tmp_path):
    """The secondary diagnostics must match independently calculated
    values, not just field-existence assertions."""
    pmfs = _synthetic_pmfs_frame(n_cal=1100, n_ev=1100)
    cal_h, ev_h = _expected_hashes(pmfs)
    out = tmp_path / "cal_diag"
    res = runner.run_count_pmf_calibration(
            pmfs, out, execution_ack=ACK,
            expected_cal_hash=cal_h, expected_eval_hash=ev_h)
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


def test_runner_full_cdf_bucket_axis_and_row_order_invariance(tmp_path):
    """Regression test for Defect 1:
    - Multiple starts with distinct, hand-checkable PMFs.
    - Every reported CDF bucket k=0..23 checked against an independently
      calculated expected value (accumulated across buckets axis=1, then
      averaged across starts).
    - All reported CDF values in [0, 1], nondecreasing across buckets,
      and final bucket k=23 equal to 1.0.
    - Reordering evaluation rows does not change aggregate diagnostics.
    """
    # Construct two distinct hand-checkable PMFs:
    # PMF A: mass 0.25 at k=0, 0.50 at k=1, 0.25 at k=2 (CDF: 0.25, 0.75, 1.0, ..., 1.0)
    # PMF B: mass 0.50 at k=2, 0.50 at k=4 (CDF: 0, 0, 0.50, 0.50, 1.0, ..., 1.0)
    pmf_a = np.zeros(24, dtype=np.float64)
    pmf_a[0], pmf_a[1], pmf_a[2] = 0.25, 0.50, 0.25
    pmf_b = np.zeros(24, dtype=np.float64)
    pmf_b[2], pmf_b[4] = 0.50, 0.50

    rows = []
    # 1,000 calibration starts (alternating A and B so fitted_a is deterministic)
    for i in range(1000):
        pmf = pmf_a if (i % 2 == 0) else pmf_b
        k = 1 if (i % 2 == 0) else 3
        rows.append((9000000 + i, "Top", 700000 + i, "2024-08-15",
                     "block_2024H2", k, pmf.tolist()))
    # 4 evaluation starts: 2 with PMF A (realized k=1), 2 with PMF B (realized k=4)
    ev_specs = [
        (9100000, "Top", 800000, "2025-04-15", "block_2025H1", 1, pmf_a.tolist()),
        (9100001, "Bot", 800001, "2025-04-15", "block_2025H1", 4, pmf_b.tolist()),
        (9100002, "Top", 800002, "2025-04-16", "block_2025H1", 1, pmf_a.tolist()),
        (9100003, "Bot", 800003, "2025-04-16", "block_2025H1", 4, pmf_b.tolist()),
    ]
    rows.extend(ev_specs)
    frame = pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "game_date": pl.Utf8, "block": pl.Utf8,
        "realized_k": pl.Int64, "pmf_baseline": pl.List(pl.Float64),
    }, orient="row")

    cal_h, ev_h = _expected_hashes(frame)
    res1 = runner.run_count_pmf_calibration(
            frame, tmp_path / "run_order1",
            execution_ack=ACK,
            expected_cal_hash=cal_h, expected_eval_hash=ev_h, n_boot=50)

    fitted_a = res1["metrics"]["fitted_a"]
    cdf_rows = res1["metrics"]["secondary"]["cdf_calibration"]
    assert len(cdf_rows) == 24

    # Hand-computed expected frozen CDF average (50% PMF A + 50% PMF B):
    # k=0: 0.5*0.25 + 0.5*0.00 = 0.125
    # k=1: 0.5*0.75 + 0.5*0.00 = 0.375
    # k=2: 0.5*1.00 + 0.5*0.50 = 0.750
    # k=3: 0.5*1.00 + 0.5*0.50 = 0.750
    # k>=4: 0.5*1.00 + 0.5*1.00 = 1.000
    exp_frozen_cdf = [0.125, 0.375, 0.750, 0.750] + [1.0] * 20
    cal_a = cpc.linear_cdf_calibrate(pmf_a, fitted_a)
    cal_b = cpc.linear_cdf_calibrate(pmf_b, fitted_a)
    exp_cal_cdf = 0.5 * np.cumsum(cal_a) + 0.5 * np.cumsum(cal_b)
    exp_emp_cdf = [0.0, 0.5, 0.5, 0.5] + [1.0] * 20

    prev_f, prev_c, prev_e = 0.0, 0.0, 0.0
    for k in range(24):
        row = cdf_rows[k]
        assert row["bucket"] == k
        pf = row["pred_cdf_frozen"]
        pc = row["pred_cdf_calibrated"]
        pe = row["empirical_cdf"]
        # In [0, 1]
        assert 0.0 <= pf <= 1.0
        assert 0.0 <= pc <= 1.0
        assert 0.0 <= pe <= 1.0
        # Nondecreasing across buckets
        assert pf >= prev_f - 1e-12
        assert pc >= prev_c - 1e-12
        assert pe >= prev_e - 1e-12
        prev_f, prev_c, prev_e = pf, pc, pe
        # Exact match to hand-calculated values
        assert pf == pytest.approx(exp_frozen_cdf[k], abs=1e-12)
        assert pc == pytest.approx(float(exp_cal_cdf[k]), abs=1e-12)
        assert pe == pytest.approx(exp_emp_cdf[k], abs=1e-12)

    assert cdf_rows[23]["pred_cdf_frozen"] == pytest.approx(1.0, abs=1e-12)
    assert cdf_rows[23]["pred_cdf_calibrated"] == pytest.approx(1.0, abs=1e-12)
    assert cdf_rows[23]["empirical_cdf"] == pytest.approx(1.0, abs=1e-12)

    # Row-reordering invariance: reverse the evaluation rows and shuffle calibration rows
    frame_reordered = frame.reverse()
    res2 = runner.run_count_pmf_calibration(
            frame_reordered, tmp_path / "run_order2",
            execution_ack=ACK,
            expected_cal_hash=cal_h, expected_eval_hash=ev_h, n_boot=50)
    assert res2["metrics"]["fitted_a"] == pytest.approx(fitted_a, abs=1e-12)
    assert res2["metrics"]["rps_frozen_mean"] == pytest.approx(
        res1["metrics"]["rps_frozen_mean"], abs=1e-12)
    assert res2["metrics"]["rps_calibrated_mean"] == pytest.approx(
        res1["metrics"]["rps_calibrated_mean"], abs=1e-12)
    for k in range(24):
        assert res2["metrics"]["secondary"]["cdf_calibration"][k] == pytest.approx(
            cdf_rows[k], abs=1e-12)
    assert res2["metrics"]["secondary"]["own_line_ll_frozen"] == pytest.approx(
        res1["metrics"]["secondary"]["own_line_ll_frozen"], abs=1e-12)
    assert res2["metrics"]["secondary"]["own_line_ll_calibrated"] == pytest.approx(
        res1["metrics"]["secondary"]["own_line_ll_calibrated"], abs=1e-12)
    assert res2["metrics"]["secondary"]["own_line_brier_frozen"] == pytest.approx(
        res1["metrics"]["secondary"]["own_line_brier_frozen"], abs=1e-12)
    assert res2["metrics"]["secondary"]["own_line_brier_calibrated"] == pytest.approx(
        res1["metrics"]["secondary"]["own_line_brier_calibrated"], abs=1e-12)


def test_runner_own_line_event_consistency_across_integer_boundary(tmp_path):
    """Regression test for Defect 2:
    Construct a case where calibration moves the PMF mean across an
    integer boundary (e.g. frozen mean = 4.8 -> t_own = 4.5, i.e. K >= 5,
    while calibrated mean > 5.0, which under the old bug switched the
    calibrated event to K >= 6 while still scoring against o = 1{K >= 5}).
    Verify both frozen and calibrated probabilities are evaluated at the
    identical frozen-derived half-line t_own = 4.5 and scored against the
    same label o = 1{realized_k > 4.5}.
    """
    # Calibration cohort: 1,000 starts where realized K is systematically high
    # so fitted_a > 1 (stretches survival curve upward, increasing mean K).
    pmf_cal = np.zeros(24, dtype=np.float64)
    pmf_cal[0] = 0.30
    pmf_cal[5] = 0.40
    pmf_cal[8] = 0.30
    rows = []
    for i in range(1000):
        rows.append((9000000 + i, "Top", 700000 + i, "2024-08-15",
                     "block_2024H2", 8, pmf_cal.tolist()))

    # Evaluation PMF:
    # p(0) = 0.20, p(5) = 0.40, p(7) = 0.40
    # Frozen mean = 0*0.20 + 5*0.40 + 7*0.40 = 4.80 (< 5.0)
    # Deterministic frozen half-line: floor(4.80 + 0.5) - 0.5 = 4.5 (event: K >= 5)
    # Under frozen PMF: P(K > 4.5) = p(5) + p(7) = 0.80, whereas P(K > 5.2) = p(7) = 0.40.
    pmf_ev = np.zeros(24, dtype=np.float64)
    pmf_ev[0] = 0.20
    pmf_ev[5] = 0.40
    pmf_ev[7] = 0.40
    mean_f = float((pmf_ev * np.arange(24)).sum())
    assert mean_f == pytest.approx(4.80, abs=1e-12)

    # Set realized_k = 5 (so K > 4.5 is True: o = 1.0, whereas K > 5.5 is False)
    for i in range(10):
        rows.append((9100000 + i, "Bot", 800000 + i, "2025-04-15",
                     "block_2025H1", 5, pmf_ev.tolist()))

    frame = pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "game_date": pl.Utf8, "block": pl.Utf8,
        "realized_k": pl.Int64, "pmf_baseline": pl.List(pl.Float64),
    }, orient="row")

    cal_h, ev_h = _expected_hashes(frame)
    res = runner.run_count_pmf_calibration(
            frame, tmp_path / "run_boundary",
            execution_ack=ACK,
            expected_cal_hash=cal_h, expected_eval_hash=ev_h, n_boot=50)

    fitted_a = res["metrics"]["fitted_a"]
    pmf_c = cpc.linear_cdf_calibrate(pmf_ev, fitted_a)
    mean_c = float((pmf_c * np.arange(24)).sum())
    # Confirm that calibration crossed the integer 5.0 boundary:
    # mean_f = 4.80 < 5.0 < mean_c
    assert mean_f < 5.0 < mean_c

    # Expected shared threshold is t_own = 4.5 (event K >= 5) for BOTH arms
    t_own = 4.5
    p_over_f = float(pmf_ev[5:].sum())
    p_over_c_same_event = float(pmf_c[5:].sum())
    p_over_c_wrong_event = float(pmf_c[6:].sum())  # what mean_c > 5.0 previously gave
    assert p_over_c_same_event != pytest.approx(p_over_c_wrong_event, abs=1e-3)

    eps = 1e-12
    exp_ll_f = -np.log(p_over_f + eps)
    exp_ll_c = -np.log(p_over_c_same_event + eps)
    exp_brier_f = (p_over_f - 1.0) ** 2
    exp_brier_c = (p_over_c_same_event - 1.0) ** 2

    sec = res["metrics"]["secondary"]
    assert sec["own_line_ll_frozen"] == pytest.approx(exp_ll_f, abs=1e-12)
    assert sec["own_line_ll_calibrated"] == pytest.approx(exp_ll_c, abs=1e-12)
    assert sec["own_line_brier_frozen"] == pytest.approx(exp_brier_f, abs=1e-12)
    assert sec["own_line_brier_calibrated"] == pytest.approx(exp_brier_c, abs=1e-12)


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
            combined, out, execution_ack=ACK,
            expected_cal_hash=cal_h, expected_eval_hash=ev_h)


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
            pmfs, out, execution_ack=ACK,
            expected_cal_hash=cal_h, expected_eval_hash=ev_h)

    assert "freeze" in call_order
    assert "load_eval" in call_order
    assert call_order.index("freeze") < call_order.index("load_eval")

def test_runner_refuses_without_ack_before_output_creation(tmp_path):
    """A missing or invalid execution_ack must refuse BEFORE the
    write-once check, directory creation, receipt writing, fitting, or
    scoring: the output directory must not exist at all. Omitting the
    keyword entirely also refuses (required keyword-only argument)."""
    pmfs = _synthetic_pmfs_frame()
    out = tmp_path / "no_ack"
    with pytest.raises(ValueError, match="execution acknowledgement"):
        runner.run_count_pmf_calibration(
            pmfs, out, execution_ack=None,
            expected_cal_hash="0" * 64,
            expected_eval_hash="0" * 64)
    assert not out.exists()
    assert not (out / "receipt_initial.json").exists()
    assert not (out / "failure_record.json").exists()
    with pytest.raises(TypeError):
        runner.run_count_pmf_calibration(
            pmfs, out,
            expected_cal_hash="0" * 64, expected_eval_hash="0" * 64)
    assert not out.exists()


def test_runner_refuses_wrong_token_before_output_creation(tmp_path):
    """A wrong token is also refused before any side effect."""
    pmfs = _synthetic_pmfs_frame()
    out = tmp_path / "bad_token"
    with pytest.raises(ValueError, match="execution acknowledgement"):
        runner.run_count_pmf_calibration(
            pmfs, out, execution_ack="NOT-THE-REGISTERED-TOKEN",
            expected_cal_hash="0" * 64, expected_eval_hash="0" * 64)
    assert not out.exists()


def test_runner_accepted_ack_records_acknowledgement_in_receipt(tmp_path):
    """The accepted path must record the technical acknowledgement
    (token, route, and the not-owner-authorization note) in the
    initial receipt, and the chained final receipt inherits it."""
    pmfs = _synthetic_pmfs_frame()
    cal_h, ev_h = _expected_hashes(pmfs)
    out = tmp_path / "ack_receipt"
    res = runner.run_count_pmf_calibration(
        pmfs, out, execution_ack=ACK,
        expected_cal_hash=cal_h, expected_eval_hash=ev_h)
    init = json.loads(
        (out / "receipt_initial.json").read_text(encoding="utf-8"))
    ack = init["execution_acknowledgement"]
    assert ack["token"] == runner.EXECUTION_ACK_TOKEN
    assert ack["route"] == "direct-call"
    assert "NOT proof of owner authorization" in ack["note"]
    fin = res["receipt_final"]
    assert fin["execution_acknowledgement"]["token"] == \
        runner.EXECUTION_ACK_TOKEN


def test_runner_accepted_ack_preserves_calculations(tmp_path):
    """The acknowledged synthetic path must produce identical metrics
    across two identical runs (same seed) and match the independent
    frozen-arm MAE, proving the gate did not alter calculations."""
    pmfs = _synthetic_pmfs_frame()
    cal_h, ev_h = _expected_hashes(pmfs)
    res1 = runner.run_count_pmf_calibration(
        pmfs, tmp_path / "ack_calc1", execution_ack=ACK,
        expected_cal_hash=cal_h, expected_eval_hash=ev_h, n_boot=50)
    res2 = runner.run_count_pmf_calibration(
        pmfs, tmp_path / "ack_calc2", execution_ack=ACK,
        expected_cal_hash=cal_h, expected_eval_hash=ev_h, n_boot=50)
    assert res1["metrics"] == res2["metrics"]
    ps = pl.read_parquet(
        tmp_path / "ack_calc1" / "calibration_per_start_v1.parquet")
    mean_ks = []
    for r in ps.iter_rows(named=True):
        pmfs_row = pmfs.filter(
            (pl.col("game_pk") == r["game_pk"])
            & (pl.col("pitcher") == r["pitcher"]))
        pmf = np.asarray(pmfs_row["pmf_baseline"][0], dtype=np.float64)
        mean_ks.append(float((pmf * np.arange(24)).sum()))
    sec = res1["metrics"]["secondary"]
    assert sec["mae_frozen"] == pytest.approx(
        np.mean(np.abs(np.asarray(mean_ks) - ps["realized_k"].to_numpy())),
        abs=1e-9)


def test_cli_refuses_without_ack_before_input_load_or_output(
        tmp_path, monkeypatch, capsys):
    """The registered CLI must exit 2 WITHOUT a valid token BEFORE
    reading the input parquet and BEFORE creating the output
    directory. A missing --execution-ack flag is refused by argparse
    with exit code 2; a present-but-invalid token is refused by the
    gate with the same code and no side effects."""
    loaded = []
    real_read = runner.pl.read_parquet

    def spy_read(path, *a, **k):
        loaded.append(str(path))
        return real_read(path, *a, **k)

    monkeypatch.setattr(runner.pl, "read_parquet", spy_read)
    pmfs_path = tmp_path / "pmfs.parquet"
    _synthetic_pmfs_frame().write_parquet(pmfs_path)
    out = tmp_path / "cli_out"
    with pytest.raises(SystemExit) as ei:
        runner.main([
            "--pmfs", str(pmfs_path), "--out-dir", str(out),
            "--expected-cal-hash", "0" * 64,
            "--expected-eval-hash", "0" * 64,
        ])
    assert ei.value.code == 2
    assert loaded == []
    assert not out.exists()
    out2 = tmp_path / "cli_out_bad_token"
    rc = runner.main([
        "--pmfs", str(pmfs_path), "--out-dir", str(out2),
        "--expected-cal-hash", "0" * 64,
        "--expected-eval-hash", "0" * 64,
        "--execution-ack", "WRONG-TOKEN",
    ])
    assert rc == 2
    assert loaded == []
    assert not out2.exists()
    assert "EXECUTION REFUSED" in capsys.readouterr().err


def test_cli_refuses_wrong_token_before_input_load_or_output(
        tmp_path, monkeypatch):
    loaded = []
    real_read = runner.pl.read_parquet

    def spy_read(path, *a, **k):
        loaded.append(str(path))
        return real_read(path, *a, **k)

    monkeypatch.setattr(runner.pl, "read_parquet", spy_read)
    pmfs_path = tmp_path / "pmfs.parquet"
    _synthetic_pmfs_frame().write_parquet(pmfs_path)
    out = tmp_path / "cli_out_wrong"
    rc = runner.main([
        "--pmfs", str(pmfs_path), "--out-dir", str(out),
        "--expected-cal-hash", "0" * 64,
        "--expected-eval-hash", "0" * 64,
        "--execution-ack", "WRONG-TOKEN",
    ])
    assert rc == 2
    assert loaded == []
    assert not out.exists()


def test_cli_accepted_ack_runs_registered_path(tmp_path, capsys):
    """With the token, the CLI loads the parquet, runs the registered
    experiment, records route="cli" in the receipt, and prints the
    metrics JSON."""
    pmfs = _synthetic_pmfs_frame()
    cal_h, ev_h = _expected_hashes(pmfs)
    pmfs_path = tmp_path / "pmfs.parquet"
    pmfs.write_parquet(pmfs_path)
    out = tmp_path / "cli_ok"
    rc = runner.main([
        "--pmfs", str(pmfs_path), "--out-dir", str(out),
        "--expected-cal-hash", cal_h, "--expected-eval-hash", ev_h,
        "--execution-ack", runner.EXECUTION_ACK_TOKEN,
    ])
    assert rc == 0
    assert (out / "receipt_final.json").exists()
    fin = json.loads(
        (out / "receipt_final.json").read_text(encoding="utf-8"))
    assert fin["execution_acknowledgement"]["route"] == "cli"
    assert fin["execution_acknowledgement"]["token"] == \
        runner.EXECUTION_ACK_TOKEN
    out_json = capsys.readouterr().out
    assert "fitted_a" in out_json
