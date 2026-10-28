"""Synthetic tests for the minimal baseline benchmark arms
(baseline_ladder.py). SYNTHETIC ONLY: no real artifacts, no outcome
scoring on registered data. Verifies the registered contract:
training-only estimation, cold-start fallback, identical support/tail
conventions, and the registered paired contrast machinery."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

import kcount_combiner as kc  # noqa: E402
from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import baseline_ladder as bl  # noqa: E402


def _train_rows():
    """Synthetic training-window outcome rows (the declared estimation
    window): 6 starts with distinct K/BF outcomes."""
    rows = [(9000001, "Top", 700001, 6, 22), (9000002, "Bot", 700001, 3, 19),
            (9000003, "Top", 700002, 8, 25), (9000003, "Bot", 700002, 5, 21),
            (9000004, "Top", 700003, 1, 15), (9000005, "Bot", 700003, 2, 17)]
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "realized_k": pl.Int64, "realized_bf": pl.Int64}, orient="row")


def _bf37_fixture():
    v = np.full(37, 0.0)
    v[:35] = 0.02
    v[35] = 0.20
    v[36] = 0.10
    return v


def _bf_lookup():
    return {(9001001, "Top", 700001): _bf37_fixture(),
            (9001002, "Bot", 700002): _bf37_fixture()}


# ------------------------------------------------------------ support/tails
def test_baseline_empirical_k_pmf_support_and_tail():
    """Registered contract: 24 buckets, values >= 23 accumulate into
    bucket 23, normalized."""
    pmf = bl.empirical_k_pmf([0, 1, 2, 23, 30, 5])
    assert pmf.shape == (24,)
    assert pmf.sum() == pytest.approx(1.0, abs=1e-12)
    assert pmf[23] == pytest.approx(2.0 / 6.0, abs=1e-12)
    assert pmf[0] == pytest.approx(1.0 / 6.0, abs=1e-12)


def test_baseline_empirical_pmf_is_independent_of_evaluation_rows():
    """Time boundary: the estimation function is pure over its injected
    training values -- evaluation outcomes can never alter it."""
    train = bl.empirical_k_pmf([5, 5, 6])
    again = bl.empirical_k_pmf([5, 5, 6])
    assert np.array_equal(train, again)


def test_baseline_bf37_support():
    bf = bl.empirical_bf37([20, 22, 40, 25, 19])
    assert bf.shape == (37,)
    assert bf.sum() == pytest.approx(1.0, abs=1e-12)
    assert bf[36] == pytest.approx(1.0 / 5.0, abs=1e-12)  # N >= 37 bucket
    with pytest.raises(bl.BaselineError, match="empty training"):
        bl.empirical_bf37([])


# --------------------------------------------------------- shrinkage reuse
def test_baseline_shrunk_rate_matches_registered_form():
    """Arm S uses the registered w150 shrinkage form -- identical
    arithmetic to the frozen attach machinery ((k + W*lg)/(n + W))."""
    rates = bl.shrunk_pitcher_rates(_train_rows())
    lg = rates["population_rate"]
    assert lg == pytest.approx(25.0 / 119.0, abs=1e-12)
    # P1: k=3+6=9, n=22+19=41
    expected = (9 + 150 * lg) / (41 + 150)
    assert rates["rates"][700001] == pytest.approx(expected, abs=1e-15)


def test_baseline_cold_start_population_fallback():
    rates = bl.shrunk_pitcher_rates(_train_rows())
    assert 999999 not in rates["rates"]
    # declared fallback: population rate at lookup time
    p_bar = rates["rates"].get(999999, rates["population_rate"])
    assert p_bar == rates["population_rate"]


# --------------------------------------------- support conventions parity
def test_baseline_pitcher_arm_matches_independent_mixture():
    """Arm S PMFs share the registered support/tail conventions: compare
    against an independent explicit-binomial mixture (no shared helper)."""
    from math import exp, lgamma
    model = {"coef": None}
    bf37 = _bf37_fixture()
    bf_ext = ad.bf_pmf_from_37(bf37)
    p_bar = 0.27
    pmf = bl.pitcher_arm_pmf(p_bar, bf37)
    # independent computation: explicit loops + math.exp sigmoid-free binom
    out = np.zeros(24)
    for n_idx, pn in enumerate(bf_ext):
        n = n_idx + 1
        for k in range(24):
            if k > n:
                continue
            log_coef = (lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1))
            out[k] += pn * exp(log_coef + k * np.log(p_bar)
                               + (n - k) * np.log1p(-p_bar))
    tail = max(0.0, 1.0 - out.sum())
    out[23] += tail
    assert np.abs(pmf - out).max() == pytest.approx(0.0, abs=1e-12)
    assert pmf.sum() == pytest.approx(1.0, abs=1e-9)
    ad.check_pmf(pmf, "pitcher_arm")
    assert model is not None


# ------------------------------------------------------------- build arms
def test_baseline_build_arms_training_only_and_cold_start():
    train = (_train_rows()
             .with_columns(pl.lit("block_2024H2").alias("block"))
             .with_columns(pl.lit(date(2024, 9, 15)).alias("game_date")))
    starts = pl.DataFrame(
        [(9001001, "Top", 700001), (9001002, "Bot", 999999)],
        schema={"game_pk": pl.Int64, "side": pl.Utf8,
                "pitcher": pl.Int64}, orient="row")
    arms = bl.build_arms(train, starts, _bf37_fixture_lookup())
    assert arms["settings"]["train_block"] == "block_2024H2"
    assert arms["settings"]["cold_start_rule"] == "population_rate_fallback"
    # cold pitcher 999999 receives the population rate: its arm-S PMF
    # equals the pitcher arm built from the population rate
    pop_rate = arms["settings"]["population_rate"]
    cold_pmf = arms["pitcher"][(9001002, "Bot", 999999)]
    ref = bl.pitcher_arm_pmf(pop_rate, _bf37_fixture())
    assert float(np.abs(cold_pmf - ref).max()) == pytest.approx(
        0.0, abs=1e-15)
    assert cold_pmf.shape == (24,)
    # identical keys across arms (population contract)
    assert set(arms["population"]) == set(arms["pitcher"])
    # capped-mean helper is labeled separately from uncapped E[K]
    mk = bl.mean_k_capped(cold_pmf)
    assert 0.0 <= mk <= 23.0


def _bf37_fixture_lookup():
    bf = _bf37_fixture()
    return {
        (9001001, "Top", 700001): bf.copy(),
        (9001002, "Bot", 999999): bf.copy(),
    }


# ------------------------------------------------- registered paired test
def test_baseline_paired_contrast_registered_machinery():
    scores_a = {(1, "Top", 700001): 1.30, (2, "Bot", 700002): 1.25}
    scores_b = {(1, "Top", 700001): 1.35, (2, "Bot", 700002): 1.29}
    dates = {(1, "Top", 700001): "2025-04-15",
             (2, "Bot", 700002): "2025-04-15"}
    blocks = {(1, "Top", 700001): "block_2025H1",
              (2, "Bot", 700002): "block_2025H1"}
    out = bl.paired_contrast(scores_a, scores_b, dates, blocks, n_boot=50)
    assert out["n_starts"] == 2
    assert out["delta_a_minus_b"] == pytest.approx(-0.045, abs=1e-12)
    assert out["primary_pair"] == "S_vs_F"
    assert len(out["ci95"]) == 2
    # determinism under the fixed seed
    again = bl.paired_contrast(scores_a, scores_b, dates, blocks,
                               n_boot=50, seed=20261001)
    assert again["ci95"] == out["ci95"]


def test_baseline_unequal_key_sets_fail_loud():
    """Equal-key contract: no silent intersection. Missing keys must be
    reported per side and the contrast must refuse to run."""
    scores_a = {(1, "Top", 700001): 1.30, (2, "Bot", 700002): 1.25,
                (3, "Top", 700003): 1.40}
    scores_b = {(1, "Top", 700001): 1.35, (2, "Bot", 700002): 1.29}
    dates = {k: "2025-04-15" for k in scores_a}
    blocks = {k: "block_2025H1" for k in scores_a}
    with pytest.raises(bl.BaselineError, match="unequal scored key sets"):
        bl.paired_contrast(scores_a, scores_b, dates, blocks, n_boot=10)
    # both directions of missing keys must be reported
    with pytest.raises(bl.BaselineError,
                       match=r"missing_in_b.*missing_in_a") as ei:
        bl.paired_contrast(scores_a, scores_b, dates, blocks, n_boot=10)
    assert "(2, 'x', 1)" not in str(ei.value)  # sanity: no fabricated keys


def test_baseline_metadata_misalignment_fails(tmp_path):
    """Dates and blocks must be aligned by the same scored keys:
    a missing date or mismatched block metadata fails loud instead of
    being silently reindexed."""
    scores_a = {(1, "Top", 700001): 1.30, (2, "Bot", 700002): 1.25}
    scores_b = dict(scores_a)
    dates = {(1, "Top", 700001): "2025-04-15"}  # missing key 2
    blocks = {(1, "Top", 700001): "block_2025H1",
              (2, "Bot", 700002): "block_2025H1"}
    with pytest.raises(bl.BaselineError, match="date metadata misaligned"):
        bl.paired_contrast(scores_a, scores_b, dates, blocks, n_boot=10)
    blocks_bad = {(1, "Top", 700001): "block_2025H1"}  # missing key 2
    with pytest.raises(bl.BaselineError, match="block metadata"):
        bl.paired_contrast(scores_a, scores_b,
                           {(1, "Top", 700001): "2025-04-15",
                            (2, "Bot", 700002): "2025-04-15"},
                           blocks_bad, n_boot=10)


def test_baseline_training_window_guard_at_execution_boundary():
    """Invalid training-window inputs fail at build_arms (the execution
    boundary): evaluation-block rows and a missing block column are
    refused before any estimation."""
    starts = pl.DataFrame(
        [(9001001, "Top", 700001), (9001002, "Bot", 999999)],
        schema={"game_pk": pl.Int64, "side": pl.Utf8,
                "pitcher": pl.Int64}, orient="row")
    # guard fires on evaluation-block rows passed as training input
    with pytest.raises(bl.BaselineError, match="training window violated"):
        bl.build_arms(
            _train_rows().with_columns(
                pl.lit("block_2025H1").alias("block")),
            starts, _bf37_fixture_lookup())
    # guard requires the block column to exist at all
    with pytest.raises(bl.BaselineError, match="block' column"):
        bl.build_arms(_train_rows(), starts, _bf37_fixture_lookup())
    # valid training rows (declared block + date-verified) pass the guard
    ok = (_train_rows()
          .with_columns(pl.lit("block_2024H2").alias("block"))
          .with_columns(pl.lit(date(2024, 9, 15)).alias("game_date")))
    bl.assert_train_window(ok)


def test_baseline_training_window_date_boundary_guard(tmp_path):
    """Training rows dated after the 2025-06-30 dev boundary are refused
    even when correctly block-labeled (double boundary check)."""
    rows = _train_rows().with_columns(
        pl.lit("block_2024H2").alias("block"),
        pl.lit(date(2026, 1, 5)).alias("game_date"))
    with pytest.raises(bl.BaselineError,
                       match="after the 2025-06-30 dev boundary"):
        bl.assert_train_window(rows)
    ok = rows.with_columns(pl.lit(date(2024, 9, 15)).alias("game_date"))
    bl.assert_train_window(ok)  # valid: no raise


def test_baseline_training_window_rejects_missing_or_null_dates():
    """Undateable training rows cannot be verified against the window:
    a missing game_date column and null game_date values both fail
    loud (the guard must never skip date verification)."""
    labeled = _train_rows().with_columns(pl.lit("block_2024H2")
                                         .alias("block"))
    with pytest.raises(bl.BaselineError,
                       match="missing required 'game_date'"):
        bl.assert_train_window(labeled)
    with_nulls = labeled.with_columns(
        pl.when(pl.col("pitcher") == 700001).then(None)
        .otherwise(pl.lit(date(2024, 9, 15))).alias("game_date"))
    with pytest.raises(bl.BaselineError, match="null game_date"):
        bl.assert_train_window(with_nulls)


def test_baseline_training_window_lower_bound():
    """Rows dated before the registered projection-window start
    (2024-07-01) are refused: no permitted outcomes exist earlier, and
    block_2024H1 is out of scope by construction."""
    early = _train_rows().with_columns(
        pl.lit("block_2024H2").alias("block"),
        pl.lit(date(2024, 5, 2)).alias("game_date"))
    with pytest.raises(bl.BaselineError,
                       match="before the registered projection-window"):
        bl.assert_train_window(early)
    ok = early.with_columns(pl.lit(date(2024, 7, 1)).alias("game_date"))
    bl.assert_train_window(ok)  # lower bound inclusive: no raise
    upper = ok.with_columns(pl.lit(date(2024, 12, 31)).alias("game_date"))
    bl.assert_train_window(upper)  # upper bound inclusive: no raise


def test_baseline_training_window_rejects_mislabeled_early_2025():
    """Early-2025 rows mislabeled block_2024H2 must be refused: the
    derived block (via the registered ad.add_block rule) contradicts
    the label (block/date consistency)."""
    mislabeled = _train_rows().with_columns(
        pl.lit("block_2024H2").alias("block"),
        pl.lit(date(2025, 4, 15)).alias("game_date"))  # derived: 2025H1
    with pytest.raises(bl.BaselineError,
                       match="training block/date inconsistent"):
        bl.assert_train_window(mislabeled)
    # a correctly labeled early-2025 row would be EVALUATION data, so a
    # block_2025H1 label also fails the training-window restriction
    eval_rows = mislabeled.with_columns(pl.lit("block_2025H1")
                                        .alias("block"))
    with pytest.raises(bl.BaselineError, match="estimation is restricted"):
        bl.assert_train_window(eval_rows)
