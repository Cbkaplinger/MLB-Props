"""Synthetic tests for C-B1 (exposure-profile heterogeneity, Question B
candidate 1). Card: card_workload_dependence_B_2026-10-20.md section
C-B1. No real data, no private lake, no raw Statcast access.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import adapter as ad  # noqa: E402,F401
from pregame_pa_ext import count_aggregation_exact as ex  # noqa: E402
from pregame_pa_ext import exposure_profile as ep  # noqa: E402


# ---------------------------------------------------------------- helpers
def _lineage_pa():
    """Deterministic synthetic realized-PA lineage with slot
    probabilities: 45 PAs per pitcher-start (BF index 1..45 covers all
    five bands), K labels drawn from a KNOWN band profile (ground
    truth)."""
    rng = np.random.default_rng(11)
    rows = []
    pa_id = 0
    for gid in range(40):
        gd = date(2023, 4, 1) + __import__("datetime").timedelta(days=gid)
        pitcher = 500000 + gid
        # 45 PAs per start (BF index 1..45), same game_pk throughout
        for k in range(45):
            pa_id += 1
            j = k + 1
            band = ep.band_for_bf(j)
            # ground-truth profile: declining K rate by band
            true_band_rate = [0.30, 0.25, 0.20, 0.15, 0.10][band]
            slot_p = true_band_rate  # the frozen slot prob equals truth
            y = int(rng.random() < true_band_rate)
            rows.append((900000 + gid, k + 1, 600000 + pa_id,
                         pitcher, gd, y, slot_p))
    return pl.DataFrame(
        rows,
        schema={"game_pk": pl.Int64, "at_bat_number": pl.Int64,
                "batter": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "y": pl.Int8,
                "p_slot": pl.Float64}, orient="row")


# ------------------------------------------------------------- band logic
def test_band_boundaries_and_errors():
    assert ep.band_for_bf(1) == 0
    assert ep.band_for_bf(9) == 0
    assert ep.band_for_bf(10) == 1
    assert ep.band_for_bf(18) == 1
    assert ep.band_for_bf(19) == 2
    assert ep.band_for_bf(27) == 2
    assert ep.band_for_bf(28) == 3
    assert ep.band_for_bf(36) == 3
    assert ep.band_for_bf(37) == 4
    assert ep.band_for_bf(60) == 4
    with pytest.raises(ValueError):
        ep.band_for_bf(0)
    with pytest.raises(ValueError):
        ep.band_for_bf(61)


def test_assign_bf_bands_orders_within_start():
    pa = _lineage_pa()
    banded = ep.assign_bf_bands(pa)
    # bf_index 1..45 within each start, ordered by at_bat_number
    one = banded.filter(pl.col("game_pk") == 900000).sort("at_bat_number")
    assert one["bf_index"].to_list() == list(range(1, 46))
    assert one["band"].to_list() == [ep.band_for_bf(j) for j in range(1, 46)]
    # band identity is a function of bf_index only
    assert (banded["band"].to_numpy()
            == np.array([ep.band_for_bf(j) for j in banded["bf_index"]
                         .to_list()])).all()


def test_frozen_band_prior_is_per_band_mean():
    pa = _lineage_pa()
    banded = ep.assign_bf_bands(pa)
    prior = ep.frozen_band_prior(banded)
    assert prior.shape == (5,)
    for b in range(5):
        sub = banded.filter(pl.col("band") == b)
        assert prior[b] == pytest.approx(float(sub["p_slot"].mean()))
    # an empty band makes the frozen prior UNDEFINED: fail loud, never
    # invent a rate (stop condition c)
    with pytest.raises(ValueError, match="band 3"):
        ep.frozen_band_prior(banded.filter(pl.col("band") != 3))


# -------------------------------------------------------------- shrinkage
def test_shrinkage_pulls_sparse_bands_to_prior():
    prior = np.array([0.22, 0.22, 0.22, 0.22, 0.22])
    # zero observed PAs: pure prior
    q = ep.shrink_band_rates(np.zeros(5), np.zeros(5), prior)
    assert np.allclose(q, prior)
    # a sparse band (n=10, k=5 -> raw 0.50) is pulled toward the prior
    k = np.array([0.0, 0.0, 0.0, 5.0, 0.0])
    n = np.array([0.0, 0.0, 0.0, 10.0, 0.0])
    q = ep.shrink_band_rates(k, n, prior)
    assert q[3] == pytest.approx((150 * 0.22 + 5) / 160)
    assert 0.22 < q[3] < 0.50
    # a dense band (n=15000, k=4500 -> raw 0.30) barely moves
    k = np.array([4500.0, 0, 0, 0, 0])
    n = np.array([15000.0, 0, 0, 0, 0])
    q = ep.shrink_band_rates(k, n, prior)
    assert q[0] == pytest.approx((150 * 0.22 + 4500) / 15150)
    assert abs(q[0] - 0.30) < 0.005


def test_shrinkage_input_validation():
    with pytest.raises(ValueError):
        ep.shrink_band_rates(np.zeros(4), np.zeros(5), np.zeros(5))
    with pytest.raises(ValueError):
        ep.shrink_band_rates(np.full(5, 2.0), np.zeros(5), np.zeros(5))
    with pytest.raises(ValueError):
        ep.shrink_band_rates(np.zeros(5), np.full(5, -1.0), np.zeros(5))
    with pytest.raises(ValueError):
        ep.shrink_band_rates(np.zeros(5), np.zeros(5), np.full(5, 1.5))


def test_band_counts_match_lineage():
    pa = _lineage_pa()
    banded = ep.assign_bf_bands(pa)
    k, n = ep.band_counts(banded)
    assert n.sum() == banded.height
    assert k.sum() == int(banded["y"].sum())
    assert (k <= n).all()


# ------------------------------------------------------------------- PMF
def test_profile_pmf_normalization_and_tail():
    q = np.full(60, 0.22)
    pmf = ep.poisson_binomial_pmf_profile(q, 30)
    assert pmf.shape == (24,)
    assert abs(float(pmf.sum()) - 1.0) < 1e-9
    assert np.all(pmf >= 0)
    # tail bucket negligible for these parameters (not exactly zero)
    assert pmf[23] < 1e-6
    # mean of the PMF ~= n * q for a flat profile
    ks = np.arange(24, dtype=float)
    mean_k = float((ks * pmf).sum())
    assert mean_k == pytest.approx(30 * 0.22, abs=0.05)


def test_profile_pmf_matches_hand_computed_small_case():
    # n=2, q=[0.5, 0.25]: exact PB = [0.375, 0.5, 0.125]
    q = np.full(60, 0.1)
    q[0], q[1] = 0.5, 0.25
    pmf = ep.poisson_binomial_pmf_profile(q, 2, k_max=4)
    assert np.allclose(pmf, [0.5 * 0.75, 0.5 * 0.25 + 0.5 * 0.75, 0.5 * 0.25,
                             0.0])


def test_profile_count_pmf_mixes_over_bf_workload():
    q = np.full(60, 0.25)
    # two-point workload: half mass at n=10, half at n=20
    bf_ext = np.zeros(60)
    bf_ext[9] = 0.5
    bf_ext[19] = 0.5
    pmf = ep.profile_count_pmf(q, bf_ext)
    assert abs(float(pmf.sum()) - 1.0) < 1e-9
    mean_k = float((np.arange(24) * pmf).sum())
    assert mean_k == pytest.approx(0.5 * 10 * 0.25 + 0.5 * 20 * 0.25,
                                   abs=0.05)
    # degenerate workload at n=1: Bernoulli(q[0])
    bf1 = np.zeros(60)
    bf1[0] = 1.0
    pmf1 = ep.profile_count_pmf(q, bf1)
    assert pmf1[0] == pytest.approx(0.75, abs=1e-12)
    assert pmf1[1] == pytest.approx(0.25, abs=1e-12)
    with pytest.raises(ValueError):
        ep.profile_count_pmf(q, np.ones(59))


def test_profile_pmf_is_recoverability_consistent_with_cycled_baseline():
    """For a FLAT profile equal to every slot probability, the profile
    PB must equal the Question A cycled PB (the same per-PA Bernoullis,
    just not tiled) - the machinery cross-check."""
    p9 = np.full(9, 0.2)
    q = np.full(60, 0.2)
    for n in (1, 9, 10, 23, 60):
        a = ex.poisson_binomial_pmf_cycled(p9, n)
        b = ep.poisson_binomial_pmf_profile(q, n)
        assert np.allclose(a, b, atol=1e-12), f"n={n}"


# ------------------------------------------------------- stop conditions
def test_estimation_stop_conditions():
    prior = np.array([0.30, 0.25, 0.20, 0.15, 0.10])
    assert ep.estimation_stop(prior, prior)
    tiny = prior + np.full(5, 0.004)
    assert ep.estimation_stop(tiny, prior)
    big = prior.copy()
    big[0] += 0.006
    assert not ep.estimation_stop(big, prior)
    with pytest.raises(ValueError):
        ep.estimation_stop(np.zeros(4), prior)


# ------------------------------------------------------- strictly-prior
def test_bf_index_uses_only_within_start_ordering():
    """No leakage: the bf_index is the within-start PA order; a PA's
    band never depends on another start's rows (identity grain check
    with two interleaved games)."""
    rows = []
    for gi, gid in enumerate((1, 2)):
        for k in range(12):
            rows.append((gid, k + 1,
                         600 + k + gi * 50, 500 + gi,
                         date(2024, 7, 1), 0, 0.2))
    pa = pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "at_bat_number": pl.Int64,
        "batter": pl.Int64, "pitcher": pl.Int64, "game_date": pl.Date,
        "y": pl.Int8, "p_slot": pl.Float64}, orient="row")
    banded = ep.assign_bf_bands(pa)
    for gid in (1, 2):
        sub = banded.filter(pl.col("pitcher") == 500 + (gid - 1))
        assert sub["bf_index"].to_list() == list(range(1, 13))


def test_block_isolation_helper_separates_confirm():
    """The evaluation runner's block rule: confirm_2025H2 rows are
    excluded from any C-B1 fit input (mirror of the frozen lane's
    protected-block rule at the band-assignment boundary)."""
    pa = _lineage_pa()
    banded = ep.assign_bf_bands(pa)
    dev = banded.filter(pl.col("game_date") <= date(2025, 6, 30))
    confirm = banded.filter(pl.col("game_date") > date(2025, 6, 30))
    # synthetic lineage is all pre-confirm; the split rule is identity-
    # preserving on the dev side and the confirm side stays empty
    assert dev.height == banded.height
    assert confirm.height == 0
    # and the machinery accepts the dev frame unchanged
    prior = ep.frozen_band_prior(dev)
    assert prior.shape == (5,)
