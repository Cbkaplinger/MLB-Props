"""Synthetic tests for the keyed K-PMF diagnostic
(count_pmf_diagnostic.py). Hand-computed fixtures only; no real
artifacts, no private checkpoint reads, no fitting, no live-path edit.

Hand fixture (both starts carry BOTH arm PMFs; rows shuffled):
  control PMF:    p[2]=0.5, p[3]=0.5
  challenger PMF: p[5]=0.25, p[23]=0.75 (overflow bucket 23)
  observed: start A K=3 (half-line boundary); start B K=30 (declared
  overflow category, K >= 23)

Hand values:
  count_logscore (natural log, clip 1e-12, POSITIVE log loss):
    A control -ln(0.5); B control -ln(1e-12) (overflow bucket 23
    empty -> clip); A challenger -ln(1e-12) (p[3]=0); B challenger
    -ln(0.75).
  count RPS (summed-CDF-squared, tail-aware):
    A control 0.25; B control 1.125; A challenger 12.125;
    B challenger 1.125.
  Lines: control p_over_2_5 = 0.5, p_over_3_5..9_5 = 0.0;
    challenger p_over_2_5 = 1.0, p_over_3_5 = 1.0, p_over_4_5 = 1.0,
    p_over_5_5..9_5 = 0.75 (the K=5 mass drops out above 5.5).
    Observed over frequency: 2.5 -> 1.0 (K=3 and K=30 both over);
    3.5..9.5 -> 0.5 (only the overflow start).
  Brier: control 2.5 -> ((0.5-1)^2+(0.5-1)^2)/2 = 0.25;
    control 3.5..9_5 -> (0^2 + 1^2)/2 = 0.5; challenger 2.5 -> 0.0;
    challenger 3.5/4_5 -> ((1-0)^2+(1-1)^2)/2 = 0.5;
    challenger 5_5..9_5 -> ((0.75-0)^2+(0.75-1)^2)/2 = 0.3125.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"
                       / "pregame_pa_ext"))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import count_pmf_diagnostic as cpd  # noqa: E402
from pregame_pa_ext import market_eval_k as mk  # noqa: E402
from Python.count_layer import PROJECTION_K_LINES  # noqa: E402

START_A = (900201, "Top", 700001)
START_B = (900201, "Bot", 700002)
STARTS = [START_A, START_B]


def _pmf_control() -> np.ndarray:
    pmf = np.zeros(ad.K_MAX)
    pmf[2] = 0.5
    pmf[3] = 0.5
    return pmf


def _pmf_challenger() -> np.ndarray:
    pmf = np.zeros(ad.K_MAX)
    pmf[5] = 0.25
    pmf[ad.K_MAX - 1] = 0.75
    return pmf


def _k_pmf_frame(shuffle=True) -> pl.DataFrame:
    rows = []
    for gk, side, p in STARTS:
        for b in range(ad.K_MAX):
            rows.append((gk, side, p, b, float(_pmf_control()[b]),
                         float(_pmf_challenger()[b])))
    if shuffle:
        perm = np.random.default_rng(20261001).permutation(len(rows))
        rows = [rows[i] for i in perm]
    return pl.DataFrame(
        rows, schema={"game_pk": pl.Int64, "side": pl.Utf8,
                      "pitcher": pl.Int64, "bucket": pl.Int64,
                      "pmf_control": pl.Float64,
                      "pmf_challenger": pl.Float64}, orient="row")


def _observed_frame(ks=(3, 30), shuffle=True) -> pl.DataFrame:
    rows = [(gk, side, p, k) for (gk, side, p), k in zip(STARTS, ks)]
    if shuffle:
        perm = np.random.default_rng(20261001).permutation(len(rows))
        rows = [rows[i] for i in perm]
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "realized_k": pl.Int64}, orient="row")


def _assessment_frame() -> pl.DataFrame:
    """Per-PA prepared-assessment fixture: start A 4 PAs, labels
    [0,0,0,2] -> realized_k 3; start B 30 PAs, all strikeouts ->
    realized_k 30 (declared overflow category)."""
    rows = []
    for gi, (gk, side, p) in enumerate(STARTS):
        n = 4 if gi == 0 else 30
        for i in range(n):
            label = 0 if (gi == 1 or i < 3) else 2
            rows.append((gk, side, p, i + 1, 900000 + i, label))
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "at_bat_number": pl.Int64, "batter": pl.Int64,
        "class_label": pl.Int64}, orient="row")


# ------------------- 1. log-score sign + RPS (hand values, overflow)
def test_logscore_sign_and_rps_hand_values():
    observed = _observed_frame()
    result = cpd.diagnose(_k_pmf_frame(), observed,
                          pmf_columns=["pmf_control",
                                       "pmf_challenger"])
    ctrl = result["arms"]["pmf_control"]
    chall = result["arms"]["pmf_challenger"]
    # natural log, positive log loss; overflow K=30 reads bucket 23
    # (control: empty -> 1e-12 clip)
    assert ctrl["count_logloss_mean"] == pytest.approx(
        (-math.log(0.5) + -math.log(1e-12)) / 2)
    assert chall["count_logloss_mean"] == pytest.approx(
        (-math.log(1e-12) + -math.log(0.75)) / 2)
    assert ctrl["count_logloss_mean"] > 0
    # summed-CDF-squared RPS, hand-computed, tail-aware:
    #   A (K=3, control): cdf 0.5 at t=2 -> (0.5-0)^2 = 0.25
    #   B (K=30, control): cdf 1.0 from t=3, obs 1 from t=23 (hit=23)
    #     -> sum (1-0)^2 over t=3..22 = 20.25
    #   A (K=3, challenger): cdf 0 through t=4 -> (0-1)^2 x2 = 2, plus
    #     (0.25-1)^2 x18 = 10.125 -> 12.125
    #   B (K=30, challenger): (0.25-0)^2 x18 = 1.125
    assert ctrl["count_rps_mean"] == pytest.approx(
        (0.25 + 20.25) / 2)
    assert chall["count_rps_mean"] == pytest.approx(
        (12.125 + 1.125) / 2)
    # overflow start (K=30) is observed-over at every in-scope line
    for name, s in ctrl["lines"].items():
        expected_freq = 1.0 if name == "2.5" else 0.5
        assert s["observed_over_frequency"] == pytest.approx(
            expected_freq)


# ------------------- 2. half-line boundaries (parametrized)
@pytest.mark.parametrize("k,line,expected_over", [
    (3, 2.5, 1.0),   # K=3 is over 2.5
    (3, 3.5, 0.0),   # K=3 is under 3.5
    (2, 2.5, 0.0),   # K=2 is under 2.5 (boundary bucket itself)
    (4, 3.5, 1.0),
    (30, 9.5, 1.0),  # overflow start is over every in-scope line
])
def test_half_line_boundaries(k, line, expected_over):
    pmf = _pmf_control()
    start = START_A
    rows = []
    for b in range(ad.K_MAX):
        rows.append((start[0], start[1], start[2], b,
                     float(pmf[b])))
    k_pmf = pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "bucket": pl.Int64, "pmf_control": pl.Float64}, orient="row")
    observed = pl.DataFrame([start + (k,)], schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "realized_k": pl.Int64}, orient="row")
    result = cpd.diagnose(k_pmf, observed, pmf_columns=["pmf_control"])
    s = result["arms"]["pmf_control"]["lines"][str(line)]
    assert s["observed_over_frequency"] == pytest.approx(
        expected_over)
    assert s["predicted_over_mean"] == pytest.approx(
        mk.model_p_over(pmf, line))


# ------------------- 3. reliability: fixed bins, edges, empty bins
def test_fixed_reliability_edges_and_empty_bins():
    pred = np.asarray([0.0, 0.1, 0.95, 1.0])
    obs = np.asarray([1.0, 0.0, 1.0, 0.0])
    summary = cpd._fixed_reliability(pred, obs)
    by_bin = {(s["bin_lo"], s["bin_hi"]): s for s in summary}
    assert len(summary) == 10
    first = by_bin[(0.0, 0.1)]
    assert first["n"] == 1
    assert first["mean_forecast"] == pytest.approx(0.0)
    assert first["observed_frequency"] == pytest.approx(1.0)
    second = by_bin[(0.1, 0.2)]
    assert second["n"] == 1
    assert second["mean_forecast"] == pytest.approx(0.1)
    assert second["observed_frequency"] == pytest.approx(0.0)
    last = by_bin[(0.9, 1.0)]
    assert last["n"] == 2  # p = 1 included in the last bin
    assert last["mean_forecast"] == pytest.approx(0.975)
    assert last["observed_frequency"] == pytest.approx(0.5)
    for (lo, hi), s in by_bin.items():
        if s["n"] == 0:
            assert s["mean_forecast"] is None
            assert s["observed_frequency"] is None
    assert by_bin[(0.2, 0.3)]["n"] == 0


# ------------------- 4. paired deltas + shuffled-row alignment
def test_paired_deltas_and_shuffle_alignment():
    result_shuffled = cpd.diagnose(
        _k_pmf_frame(shuffle=True), _observed_frame(shuffle=True),
        pmf_columns=["pmf_control", "pmf_challenger"])
    result_sorted = cpd.diagnose(
        _k_pmf_frame(shuffle=False), _observed_frame(shuffle=False),
        pmf_columns=["pmf_control", "pmf_challenger"])
    assert result_shuffled == result_sorted
    paired = result_shuffled["paired"]
    assert paired is not None
    assert paired["challenger"] == "pmf_challenger"
    assert paired["control"] == "pmf_control"
    assert paired["n_paired_starts"] == 2
    ctrl = result_shuffled["arms"]["pmf_control"]
    chall = result_shuffled["arms"]["pmf_challenger"]
    assert paired["count_logloss_delta_mean"] == pytest.approx(
        chall["count_logloss_mean"] - ctrl["count_logloss_mean"])
    assert paired["count_rps_delta_mean"] == pytest.approx(
        chall["count_rps_mean"] - ctrl["count_rps_mean"])
    assert paired["per_line_brier_delta_mean"]["2.5"] == \
        pytest.approx(0.0 - 0.25)
    for name in ("3.5", "4.5"):
        assert paired["per_line_brier_delta_mean"][name] == \
            pytest.approx(0.5 - 0.5)
    for name in ("5.5", "6.5", "7.5", "8.5", "9.5"):
        assert paired["per_line_brier_delta_mean"][name] == \
            pytest.approx(0.3125 - 0.5)
    assert paired["count_rps_delta_mean"] == pytest.approx(-3.625)
    # arms stay separate: distinct per-start tables
    assert (ctrl["per_start_count_rps"]
            != chall["per_start_count_rps"])


def test_single_arm_has_no_paired_section():
    result = cpd.diagnose(_k_pmf_frame(), _observed_frame(),
                          pmf_columns=["pmf_control"])
    assert result["paired"] is None
    assert list(result["arms"]) == ["pmf_control"]


# ------------------- 5. key/identity/label refusals
def test_duplicate_observed_start_refused():
    bad = pl.concat([_observed_frame(), _observed_frame().head(1)])
    with pytest.raises(ValueError, match="duplicate identity key"):
        cpd.diagnose(_k_pmf_frame(), bad,
                     pmf_columns=["pmf_control"])


def test_duplicate_start_bucket_refused():
    bad = pl.concat([_k_pmf_frame(), _k_pmf_frame().head(1)])
    with pytest.raises(ValueError, match="duplicate identity"):
        cpd.diagnose(bad, _observed_frame(),
                     pmf_columns=["pmf_control"])


def test_null_keys_refused():
    bad = _observed_frame().with_columns(
        pl.when(pl.col("pitcher") == 700001).then(None)
        .otherwise(pl.col("pitcher")).alias("pitcher"))
    with pytest.raises(ValueError, match="null value"):
        cpd.diagnose(_k_pmf_frame(), bad,
                     pmf_columns=["pmf_control"])
    bad = _k_pmf_frame().with_columns(
        pl.when(pl.col("bucket") == 0).then(None)
        .otherwise(pl.col("bucket")).alias("bucket"))
    with pytest.raises(ValueError, match="null bucket label"):
        cpd.diagnose(bad, _observed_frame(),
                     pmf_columns=["pmf_control"])


def test_key_mismatch_reports_both_directions():
    # forecast has an extra start the observations lack
    extra = (900301, "Top", 700003)
    rows = []
    for b in range(ad.K_MAX):
        rows.append((extra[0], extra[1], extra[2], b,
                     float(_pmf_control()[b]),
                     float(_pmf_challenger()[b])))
    bad = pl.concat([_k_pmf_frame(), pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "bucket": pl.Int64, "pmf_control": pl.Float64,
        "pmf_challenger": pl.Float64}, orient="row")])
    with pytest.raises(ValueError) as exc:
        cpd.diagnose(bad, _observed_frame(),
                     pmf_columns=["pmf_control"])
    assert "missing_from_observed=1" in str(exc.value)
    assert "missing_from_forecast=0" in str(exc.value)
    # observed has a start the forecast lacks
    extra_obs = pl.DataFrame([(900301, "Top", 700003, 7)], schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "realized_k": pl.Int64}, orient="row")
    with pytest.raises(ValueError) as exc:
        cpd.diagnose(_k_pmf_frame(),
                     pl.concat([_observed_frame(), extra_obs]),
                     pmf_columns=["pmf_control"])
    assert "missing_from_observed=0" in str(exc.value)
    assert "missing_from_forecast=1" in str(exc.value)


def test_malformed_labels_and_observed_k_refused():
    bad = _assessment_frame().with_columns(
        pl.when(pl.col("at_bat_number") == 1).then(9)
        .otherwise(pl.col("class_label")).alias("class_label"))
    with pytest.raises(ValueError, match="class labels outside"):
        cpd.derive_observed_k(bad)
    bad = _observed_frame().with_columns(
        pl.when(pl.col("pitcher") == 700001).then(2.5)
        .otherwise(pl.col("realized_k")).cast(pl.Float64)
        .alias("realized_k"))
    with pytest.raises(ValueError, match="integer-valued"):
        cpd.diagnose(_k_pmf_frame(), bad,
                     pmf_columns=["pmf_control"])
    bad = _observed_frame().with_columns(
        pl.when(pl.col("pitcher") == 700001).then(-1)
        .otherwise(pl.col("realized_k")).alias("realized_k"))
    with pytest.raises(ValueError, match="nonnegative"):
        cpd.diagnose(_k_pmf_frame(), bad,
                     pmf_columns=["pmf_control"])


def test_malformed_pmf_mass_refused():
    bad = _k_pmf_frame().with_columns(
        pl.when((pl.col("bucket") == 2)
                & (pl.col("pitcher") == 700001)).then(-0.1)
        .otherwise(pl.col("pmf_control")).alias("pmf_control"))
    with pytest.raises(ad.AdapterError, match="PMF out of"):
        cpd.diagnose(bad, _observed_frame(),
                     pmf_columns=["pmf_control"])
    bad = _k_pmf_frame().with_columns(
        pl.when(pl.col("bucket") == 3).then(float("nan"))
        .otherwise(pl.col("pmf_challenger")).alias("pmf_challenger"))
    with pytest.raises(ad.AdapterError, match="non-finite PMF"):
        cpd.diagnose(bad, _observed_frame(),
                     pmf_columns=["pmf_control", "pmf_challenger"])


# ------------------- 6. CLI: ack gate, write-once, success
def test_cli_ack_write_once_and_success(tmp_path):
    k_pmf_path = tmp_path / "k_pmf.parquet"
    assessment_path = tmp_path / "assessment.parquet"
    _k_pmf_frame().write_parquet(k_pmf_path)
    _assessment_frame().write_parquet(assessment_path)
    out = tmp_path / "diag_out"
    argv = ["--k-pmf", str(k_pmf_path),
            "--assessment", str(assessment_path),
            "--arms", "pmf_control,pmf_challenger",
            "--out-dir", str(out),
            "--execution-ack", cpd.EXECUTION_ACK_TOKEN]
    assert cpd.main(argv) == 0
    payload = json.loads(
        (out / "count_pmf_diagnostic.json").read_text(
            encoding="utf-8"))
    assert payload["diagnostic_id"] == "count_pmf_diagnostic_v1"
    assert payload["arms"]["pmf_control"]["n_matched_starts"] == 2
    assert payload["paired"]["count_rps_delta_mean"] == \
        pytest.approx(-3.625)
    # write-once: same destination refuses
    with pytest.raises(ValueError, match="destination exists"):
        cpd.main(argv)
    # wrong ack refuses
    bad_argv = list(argv)
    bad_argv[bad_argv.index("--execution-ack") + 1] = "WRONG"
    with pytest.raises(ValueError, match="execution acknowledgement"):
        cpd.main(bad_argv)
