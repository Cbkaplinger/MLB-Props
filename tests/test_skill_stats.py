"""Unit tests for skill_stats: z-test, BCa bootstrap, stake-weighted CLV, rolling SE."""

from __future__ import annotations

import math

import pytest

from Python.skill_stats import (
    bootstrap_bca_ci,
    rolling_stat_with_se,
    stake_weighted_bootstrap_ci,
    two_proportion_z_test,
)


# --- two_proportion_z_test -------------------------------------------------


def test_z_test_detects_large_difference() -> None:
    # 53.8% (28/52) vs 39.0% (55/141) — the headline CLV split from the ledger.
    r = two_proportion_z_test(28, 52, 55, 141)
    assert r["p_a"] == pytest.approx(28 / 52, abs=1e-6)
    assert r["p_b"] == pytest.approx(55 / 141, abs=1e-6)
    assert r["diff"] == pytest.approx(28 / 52 - 55 / 141, abs=1e-6)
    # Direction: A (53.8%) > B (39.0%), so z positive.
    assert r["z"] > 0
    # At n=52/141 and this effect size, p is in the ~0.05-0.10 range. Two-sided.
    assert 0.03 < r["p_two_sided"] < 0.12
    # Sanity: a bigger gap should produce a smaller p.
    r_bigger = two_proportion_z_test(40, 52, 30, 141)
    assert r_bigger["p_two_sided"] < r["p_two_sided"]


def test_z_test_equal_proportions_gives_high_p() -> None:
    # Same rate, different n: z=0, p=1.
    r = two_proportion_z_test(10, 20, 50, 100)
    assert r["z"] == pytest.approx(0.0, abs=1e-9)
    assert r["p_two_sided"] == pytest.approx(1.0, abs=1e-6)
    assert r["diff"] == pytest.approx(0.0, abs=1e-9)


def test_z_test_rejects_validations() -> None:
    with pytest.raises(ValueError):
        two_proportion_z_test(-1, 10, 5, 10)
    with pytest.raises(ValueError):
        two_proportion_z_test(5, 0, 5, 10)
    with pytest.raises(ValueError):
        two_proportion_z_test(11, 10, 5, 10)


# --- bootstrap_bca_ci ------------------------------------------------------


def test_bca_centered_on_mean_for_normal() -> None:
    vals = [0.0, 0.01, -0.01, 0.02, -0.02, 0.005, -0.005, 0.015, -0.015, 0.003,
            -0.003, 0.007, -0.007, 0.011, -0.011, 0.009, -0.009, 0.012, -0.012, 0.004]
    mean, lo, hi = bootstrap_bca_ci(vals, n_boot=2000, seed=42)
    assert mean == pytest.approx(sum(vals) / len(vals))
    # BCa is bias-corrected but not strictly symmetric; the mean need not sit
    # exactly between lo and hi. The contract is just lo <= mean <= hi (with
    # some tolerance for the bias-correction pull).
    assert lo <= mean + 0.005 and hi >= mean - 0.005
    # Symmetric noise around zero -> CI should be reasonably tight.
    assert hi - lo < 0.02


def test_bca_excludes_zero_when_strongly_positive() -> None:
    vals = [0.02, 0.03, 0.025, 0.015, 0.035, 0.02, 0.028, 0.022, 0.018, 0.033,
            0.026, 0.024, 0.021, 0.029, 0.023, 0.027, 0.019, 0.031, 0.017, 0.032]
    mean, lo, hi = bootstrap_bca_ci(vals, n_boot=2000, seed=1)
    assert mean > 0.02
    # All values positive -> CI should not cross zero (BCa tightens this).
    assert lo > 0.0


def test_bca_constant_values_returns_degenerate_ci() -> None:
    vals = [0.5] * 30
    mean, lo, hi = bootstrap_bca_ci(vals, n_boot=500, seed=0)
    assert mean == pytest.approx(0.5)
    # Constant -> every bootstrap draw is 0.5, so the CI is the point.
    assert lo == pytest.approx(0.5)
    assert hi == pytest.approx(0.5)


def test_bca_custom_statistic_uses_callable() -> None:
    vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    # Median of an even-length list: our simple lambda picks the upper middle.
    median = lambda xs: sorted(xs)[len(xs) // 2]
    mean, lo, hi = bootstrap_bca_ci(vals, n_boot=1000, seed=2, statistic=median)
    assert mean == pytest.approx(6.0)
    assert lo <= mean <= hi


def test_bca_rejects_small_n_boot() -> None:
    with pytest.raises(ValueError):
        bootstrap_bca_ci([1.0, 2.0], n_boot=5)
    with pytest.raises(ValueError):
        bootstrap_bca_ci([], n_boot=500)


# --- stake_weighted_bootstrap_ci ------------------------------------------


def test_stake_weighted_equal_weights_match_plain_mean() -> None:
    vals = [0.01, -0.005, 0.02, 0.0, -0.01, 0.015]
    weights = [1.0] * len(vals)
    mean, lo, hi = stake_weighted_bootstrap_ci(vals, weights, n_boot=1000, seed=3)
    assert mean == pytest.approx(sum(vals) / len(vals))
    # Same BCa caveat — bias-correction can pull the interval tight around
    # the point estimate without strict lo < mean < hi ordering.
    assert lo <= mean + 0.002 and hi >= mean - 0.002


def test_stake_weighted_pulls_toward_heavy_bet() -> None:
    # One big-weight bet strongly positive -> weighted mean > simple mean.
    vals = [0.05, -0.02, 0.01, -0.03]
    weights = [10.0, 1.0, 1.0, 1.0]
    mean, lo, hi = stake_weighted_bootstrap_ci(vals, weights, n_boot=1000, seed=4)
    simple = sum(vals) / len(vals)
    assert mean > simple
    assert mean == pytest.approx(
        (0.05 * 10 + (-0.02) * 1 + 0.01 * 1 + (-0.03) * 1) / 13.0
    )


def test_stake_weighted_validations() -> None:
    with pytest.raises(ValueError):
        stake_weighted_bootstrap_ci([1.0, 2.0], [1.0], n_boot=100)
    with pytest.raises(ValueError):
        stake_weighted_bootstrap_ci([1.0, 2.0], [-1.0, 1.0], n_boot=100)
    with pytest.raises(ValueError):
        stake_weighted_bootstrap_ci([1.0, 2.0], [0.0, 0.0], n_boot=100)


# --- rolling_stat_with_se --------------------------------------------------


def test_rolling_se_brackets_mean() -> None:
    vals = [0.01, -0.01, 0.02, -0.02, 0.0, 0.03, -0.01, 0.02, 0.0, -0.005]
    rows = rolling_stat_with_se(vals, window=5)
    assert len(rows) == len(vals)
    # First row has n=1 -> no SE band.
    assert rows[0]["se"] is None
    assert rows[0]["mean"] == vals[0]
    # Fifth row has full window of 5 -> band present.
    last = rows[4]
    assert last["n"] == 5
    assert last["se"] is not None
    assert last["lo"] < last["mean"] < last["hi"]
    # Band width is se_scale * SE on each side: hi-mean == mean-lo == 2*SE.
    se = last["se"]
    assert last["hi"] - last["mean"] == pytest.approx(2.0 * se)
    assert last["mean"] - last["lo"] == pytest.approx(2.0 * se)


def test_rolling_se_validations() -> None:
    with pytest.raises(ValueError):
        rolling_stat_with_se([1.0, 2.0], window=1)


def test_rolling_se_increasing_window_then_stable() -> None:
    vals = [0.0] * 35
    rows = rolling_stat_with_se(vals, window=30)
    # First 29 rows have n growing 1..29, then rows 29+ all have n=30.
    assert rows[0]["n"] == 1
    assert rows[29]["n"] == 30
    assert rows[34]["n"] == 30
    # Zero variance -> SE is 0, band collapses to mean.
    assert rows[29]["se"] == 0.0
    assert rows[29]["lo"] == rows[29]["hi"] == 0.0
