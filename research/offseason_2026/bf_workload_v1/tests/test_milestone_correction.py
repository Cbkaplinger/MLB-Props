"""Correction tests for the bf-workload-v1 milestone-Brier bug (v2).

v1 bug: the milestone Brier used cdf[m:].sum() (a sum of CDF values over
k >= m) instead of the PMF-tail exceedance P(K>=m) = 1 - CDF(m-1)
= sum_{k>=m} P(K=k) (kcount_combiner.exceedance). These tests pin the
corrected definition and guard the unchanged metrics.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

WORK = Path(__file__).resolve().parent.parent
HELPERS = Path(
    r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees"
    r"\main-active\research\offseason_2026"
)
sys.path.insert(0, str(HELPERS))
from kcount_combiner import exceedance  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "run_kcount_correction_v2",
    str(WORK / "scripts" / "run_kcount_correction_v2.py"),
)
corr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(corr)

MILESTONES = (6, 8, 10, 12)
K_MAX = 24


def _random_pmf(rng: np.random.Generator, k_max: int = K_MAX) -> np.ndarray:
    p = rng.dirichlet(np.full(k_max, 0.7))
    return p / p.sum()


def test_pmf_tail_equals_one_minus_cdf():
    """P(K>=m) from the PMF tail must equal 1 - CDF(m-1)."""
    rng = np.random.default_rng(20261001)
    for _ in range(200):
        p = _random_pmf(rng)
        cdf = np.cumsum(p)
        for m in range(1, len(p)):
            assert abs(exceedance(p, m) - (1.0 - cdf[m - 1])) <= 1e-12
        assert exceedance(p, 0) == 1.0


def test_tail_probs_in_unit_interval_and_decreasing():
    rng = np.random.default_rng(7)
    for _ in range(50):
        p = _random_pmf(rng)
        prev = 1.0
        for m in range(0, K_MAX + 4):
            e = exceedance(p, m)
            assert 0.0 <= e <= 1.0
            assert e <= prev + 1e-15  # non-increasing in threshold
            prev = e


def test_k_equals_m_equality_case():
    """Point mass at K=m: P(K>=m)=1, P(K>=m+1)=0; Brier is 0 iff K>=m."""
    m = 8
    p = np.zeros(K_MAX)
    p[m] = 1.0
    assert exceedance(p, m) == 1.0
    assert exceedance(p, m + 1) == 0.0
    assert exceedance(p, m - 1) == 1.0
    # realized K == m: perfect milestone score at every m' <= m
    assert corr.corrected_metrics_for(p, m, mean_k=float(m))[f"brier_ge{m}"] == 0.0
    # realized K == m-1: the exceedance forecast is maximally wrong
    assert corr.corrected_metrics_for(p, m - 1, mean_k=float(m))[
        f"brier_ge{m}"] == 1.0


def test_absorbing_tail_case():
    """Last bucket absorbs K >= K_MAX-1; exceedance beyond support is 0."""
    p = np.zeros(K_MAX)
    p[: K_MAX - 1] = 0.7 / (K_MAX - 1)
    p[K_MAX - 1] = 0.3  # absorbing bucket for K >= 23
    assert abs(exceedance(p, 23) - 0.3) <= 1e-12
    assert abs(exceedance(p, 22) - (p[22] + 0.3)) <= 1e-12
    assert exceedance(p, 24) == 0.0  # beyond support -> impossible
    # and the identity still holds at the absorbing threshold
    cdf = np.cumsum(p)
    assert abs(exceedance(p, 23) - (1.0 - cdf[22])) <= 1e-12


def test_brier_matches_independent_binary_score():
    """(P(K>=m) - 1{K>=m})^2 computed directly must equal the metric."""
    rng = np.random.default_rng(99)
    for _ in range(25):
        p = _random_pmf(rng)
        k_real = int(rng.integers(0, 40))
        mean_k = float(k_real) + 0.5
        met = corr.corrected_metrics_for(p, k_real, mean_k)
        for m in MILESTONES:
            p_ge = float(p[m:].sum())  # independent direct PMF tail
            expected = (p_ge - (1.0 if k_real >= m else 0.0)) ** 2
            assert abs(met[f"brier_ge{m}"] - expected) <= 1e-15
            # and the exceedance identity via the CDF, independently
            assert abs(exceedance(p, m)
                       - (1.0 - np.cumsum(p)[m - 1])) <= 1e-12
        # RPS/logscore/RMSE untouched by the correction
        assert met["rmse_mean_k"] == (mean_k - k_real) ** 2


def test_unchanged_metrics_and_changed_brier_vs_v1_report():
    v1_report = json.loads(
        (WORK / "report.json").read_text(encoding="ascii"))
    v2_report = json.loads(
        (WORK / "report_v2.json").read_text(encoding="ascii"))
    for variant in ("base", "sensa", "sensb"):
        for arm in ("h3", "l5"):
            for m in ("rps", "logscore", "rmse_mean_k"):
                assert v2_report["aggregate"][variant][arm][m] == \
                    v1_report["aggregate"][variant][arm][m]
            for key in ("rps", "logscore", "rmse_mean_k"):
                assert v2_report["bootstrap_results"][
                    f"{variant}_{arm}_{key}_ci95"] == \
                    v1_report["bootstrap_results"][
                        f"{variant}_{arm}_{key}_ci95"]
            for ms in MILESTONES:
                b_v1 = v1_report["aggregate"][variant][arm][f"brier_ge{ms}"]
                b_v2 = v2_report["aggregate"][variant][arm][f"brier_ge{ms}"]
                assert b_v1 > 100.0  # v1 bug: summed CDF values
                assert 0.0 < b_v2 < 1.0  # corrected: proper Brier
                assert abs(b_v1 - b_v2) > 100.0


def test_v2_aggregate_brier_equals_direct_recompute_from_parquet():
    v2_report = json.loads(
        (WORK / "report_v2.json").read_text(encoding="ascii"))
    met = pl.read_parquet(WORK / "data" / "start_metrics_v2.parquet")
    for variant in ("base", "sensa", "sensb"):
        for arm in ("h3", "l5"):
            for ms in MILESTONES:
                col = f"{variant}_{arm}_brier_ge{ms}"
                direct = float(met[col].mean())
                reported = v2_report["aggregate"][variant][arm][
                    f"brier_ge{ms}"]
                assert abs(direct - reported) <= 1e-12

