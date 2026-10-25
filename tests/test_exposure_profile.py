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


def test_profile_pmf_mixes_over_bf_workload():
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


def test_incremental_mixture_equals_naive_reference():
    """The single-pass incremental mixture is EXACTLY the per-prefix
    PB mixture (random profile + spiky workload cross-check)."""
    rng = np.random.default_rng(77)
    q = rng.uniform(0.05, 0.45, 60)
    bf_ext = np.zeros(60)
    picks = rng.choice(60, size=12, replace=False)
    bf_ext[picks] = rng.uniform(0.05, 0.2, 12)
    bf_ext /= bf_ext.sum()
    a = ep.profile_count_pmf(q, bf_ext)
    b = ep.profile_count_pmf_naive(q, bf_ext)
    assert np.allclose(a, b, atol=1e-12)
    assert abs(float(a.sum()) - 1.0) < 1e-9


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


# ================================================== evaluation runner =====
def _runner_lake(rng_seed: int = 23, declining: bool = True):
    """Synthetic lake for the C-B1 runner: a training lineage (2023
    through 2024-06), an eligible-start ledger with 9 projected slots
    each, a uniform BF artifact, and realized K per start. When
    `declining`, lineage K rates fall by band (a real exposure signal);
    otherwise they are flat (the estimation stop should fire)."""
    rng = np.random.default_rng(rng_seed)
    import datetime as dt

    # -- ledger: 8 eligible starts, 9 slots each, mild slot profile
    led_rows = []
    for g in range(8):
        gid = 800000 + g
        for slot in range(1, 10):
            led_rows.append((gid, "Top" if g % 2 else "Bot", 700000 + g,
                             600 + slot, slot, date(2024, 8, 1),
                             None, 0.24 - 0.004 * slot))
    ledger = pl.DataFrame(
        led_rows,
        schema={"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
                "batter": pl.Int64, "slot": pl.Int8,
                "game_date": pl.Date, "exclusion_reason": pl.Utf8,
                "p_h3_raw": pl.Float64}, orient="row")

    # -- bf: uniform 37-bucket workload per start
    bf = pl.DataFrame([{"game_pk": 800000 + g,
                        "side": "Top" if g % 2 else "Bot",
                        "pitcher": 700000 + g,
                        **{f"pmf37_{j}": 1.0 / 37 for j in range(37)}}
                       for g in range(8)])

    # -- realized K per start
    realized = pl.DataFrame(
        [(800000 + g, "Top" if g % 2 else "Bot", 700000 + g,
          int(rng.integers(2, 7))) for g in range(8)],
        schema={"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
                "realized_k": pl.Int64}, orient="row")

    # -- lineage: 30 PAs per training start, band-structured truth
    true_rates = [0.30, 0.25, 0.20, 0.15, 0.10] if declining \
        else [0.22] * 5
    pa_rows = []
    pa_id = 0
    for gid in range(200):
        gd = date(2023, 4, 1) + dt.timedelta(days=gid // 2)
        if gd > date(2024, 6, 30):
            gd = date(2024, 6, 30)
        pitcher = 700000 + gid
        for k in range(30):
            pa_id += 1
            band = ep.band_for_bf(k + 1)
            y = int(rng.random() < true_rates[band])
            pa_rows.append((9000000 + gid, k + 1, 5000 + pa_id,
                            pitcher, gd, y))
    pa = pl.DataFrame(
        pa_rows,
        schema={"game_pk": pl.Int64, "at_bat_number": pl.Int64,
                "batter": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "y": pl.Int8}, orient="row")
    return pa, ledger, bf, realized


def test_frozen_prior_from_ledger_band_means():
    _, ledger, _, _ = _runner_lake()
    prior = ep.frozen_prior_from_ledger(ledger)
    assert prior.shape == (5,)
    # every start has the same slot profile 0.24 - 0.004*slot; bands
    # 0-3 each cycle slots 1..9 exactly once (9 BF positions), so their
    # prior equals the pooled mean; band 4 (BF 37-60, 24 positions)
    # covers slots 1..6 three times and slots 7..9 twice, weighting the
    # higher early-slot probabilities
    pooled = float(ledger["p_h3_raw"].mean())
    assert np.allclose(prior[:4], pooled, atol=1e-12)
    s = lambda j: 0.24 - 0.004 * j
    expected_b4 = (3 * sum(s(j) for j in range(1, 7))
                   + 2 * sum(s(j) for j in range(7, 10))) / 24
    assert prior[4] == pytest.approx(expected_b4, abs=1e-12)
    with pytest.raises(ValueError, match="no eligible starts"):
        ep.frozen_prior_from_ledger(
            ledger.with_columns(pl.lit("cold").alias("exclusion_reason")))


def test_runner_end_to_end_synthetic(tmp_path):
    """The C-B1 runner completes on synthetic input: paired count-RPS
    both arms, slate-date bootstrap CI, receipt chain, write-once
    outputs."""
    pa, ledger, bf, realized = _runner_lake()
    out = tmp_path / "cb1"
    res = ep.run_cb1_eval(pa, ledger, bf, realized, out)
    assert res["estimation_stop"] is False
    m = res["metrics"]
    assert m["n_starts"] == 8
    assert np.isfinite(m["count_rps_cb1_mean"])
    assert np.isfinite(m["count_rps_frozen_mean"])
    assert len(m["ci95"]) == 2
    assert m["decision"] in ("cb1_beats_baseline", "cb1_not_better")
    assert (out / "receipt_initial.json").exists()
    assert (out / "receipt_final.json").exists()
    assert (out / "cb1_eval_v1.parquet").exists()
    assert (out / "metrics.json").exists()
    fin = res["receipt_final"]
    assert fin["acceptance"]["receipt_chain"] == res["receipt_initial_sha256"]
    assert fin["acceptance"]["evaluation_run"] is True
    # Holm m=1: the single contrast's adjustment equals itself
    assert len(fin["metrics"]["holm"]) == 1


def test_runner_estimation_stop_path(tmp_path):
    """Card stop condition (a): a lineage whose per-band rates equal
    the prior exactly -> every band within tolerance -> receipt
    declares no exposure signal, evaluation NOT run, no eval parquet.
    The flat lineage's y is DETERMINISTIC (exactly the prior rate per
    band) so the stop fires without seed sensitivity."""
    pa, ledger, bf, realized = _runner_lake(declining=False)
    # deterministic flat rates: exactly the prior rate per band
    prior = ep.frozen_prior_from_ledger(ledger)
    banded2 = ep.assign_bf_bands(pa)
    y_map = {}
    for b in range(5):
        sub = banded2.filter(pl.col("band") == b).sort("game_pk",
                                                       "at_bat_number")
        n = sub.height
        k = round(float(prior[b]) * n)
        for i, key in enumerate(sub["batter"].to_list()):
            y_map[key] = 1 if i < k else 0
    pa = pa.with_columns(
        pl.col("batter").replace_strict(
            y_map, default=0, return_dtype=pl.Int8).alias("y"))
    out = tmp_path / "cb1_stop"
    res = ep.run_cb1_eval(pa, ledger, bf, realized, out)
    assert res["estimation_stop"] is True
    fin = res["receipt_final"]
    assert "ESTIMATION STOP" in fin["estimation_stop"]["status"]
    assert fin["acceptance"]["evaluation_run"] is False
    assert not (out / "cb1_eval_v1.parquet").exists()
    assert (out / "receipt_final.json").exists()


def test_runner_write_once_and_failure_paths(tmp_path):
    """Write-once violation, realized-count mismatch -> preserved
    failure record; receipts stay immutable."""
    pa, ledger, bf, realized = _runner_lake()
    out = tmp_path / "cb1"
    res = ep.run_cb1_eval(pa, ledger, bf, realized, out)
    initial_sha = res["receipt_initial_sha256"]
    # write-once: same directory refused
    with pytest.raises(ValueError, match="write-once violation"):
        ep.run_cb1_eval(pa, ledger, bf, realized, out)
    # failure: realized source missing rows for a start -> fail loud +
    # failure record in a NEW directory; original untouched
    out2 = tmp_path / "cb2"
    bad_realized = realized.filter(pl.col("game_pk") != 800000)
    with pytest.raises(ValueError, match="realized count mismatch"):
        ep.run_cb1_eval(pa, ledger, bf, bad_realized, out2)
    rec = (out2 / "failure_record.json").read_text(encoding="utf-8")
    assert "realized count mismatch" in rec
    # the first run's receipts are untouched by the failure
    fin = (out / "receipt_final.json").read_text(encoding="utf-8")
    assert res["receipt_initial_sha256"] in fin
    # initial receipt immutability
    import hashlib
    assert hashlib.sha256(
        (out / "receipt_initial.json").read_bytes()).hexdigest() \
        == initial_sha


def test_runner_block_isolation_confirm_never_fits(tmp_path):
    """Adding confirm-block lineage rows changes nothing: they are
    outside every training window and are never evaluated."""
    pa, ledger, bf, realized = _runner_lake()
    import datetime as dt
    confirm_rows = []
    for gid in range(4):
        for k in range(30):
            confirm_rows.append((9500000 + gid, k + 1, 7000 + gid * 30 + k,
                                 750000 + gid, date(2025, 8, 1),
                                 int(k % 3 == 0)))
    pa_confirm = pl.concat([pa, pl.DataFrame(
        confirm_rows,
        schema={"game_pk": pl.Int64, "at_bat_number": pl.Int64,
                "batter": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "y": pl.Int8}, orient="row")])
    out1, out2 = tmp_path / "r1", tmp_path / "r2"
    res1 = ep.run_cb1_eval(pa, ledger, bf, realized, out1)
    res2 = ep.run_cb1_eval(pa_confirm, ledger, bf, realized, out2)
    assert res1["metrics"]["blocks_fit"] == res2["metrics"]["blocks_fit"]
    assert res1["metrics"]["delta"] == res2["metrics"]["delta"]
    assert res1["metrics"]["n_starts"] == res2["metrics"]["n_starts"]


def test_runner_confirm_starts_excluded_not_fatal(tmp_path):
    """Regression (real-data defect, ee35359 follow-up): the preserved
    ledger carries confirm-block starts; the paired population is the
    dev starts only. Confirm starts must be EXCLUDED with a disclosed
    count, never scored and never fatal."""
    pa, ledger, bf, realized = _runner_lake()
    # add two confirm-block starts (2025-08): ledger slots + bf + realized
    import datetime as dt
    confirm_led = pl.DataFrame(
        [(900000, "Top", 800000, 9100 + s, s, date(2025, 8, 1), None,
          0.2) for s in range(1, 10)],
        schema=ledger.schema, orient="row")
    confirm_bf = pl.DataFrame([{
        "game_pk": 900000, "side": "Top", "pitcher": 800000,
        **{f"pmf37_{j}": 1.0 / 37 for j in range(37)}}])
    confirm_real = pl.DataFrame(
        [(900000, "Top", 800000, 4)],
        schema=realized.schema, orient="row")
    ledger2 = pl.concat([ledger, confirm_led])
    bf2 = pl.concat([bf, confirm_bf])
    realized2 = pl.concat([realized, confirm_real])
    out = tmp_path / "cb1"
    res = ep.run_cb1_eval(pa, ledger2, bf2, realized2, out)
    m = res["metrics"]
    assert m["n_starts"] == 8
    assert m["confirm_block_starts_excluded"] == 1
    assert m["starts_in_ledger_total"] == 9
    keys = pl.read_parquet(out / "cb1_eval_v1.parquet")
    assert 900000 not in keys["game_pk"].to_list()


def test_runner_prior_definition_recorded_in_receipt(tmp_path):
    """The receipt pins the prior definition, bands, shrinkage weight,
    and bootstrap config (pre-registration requirements)."""
    pa, ledger, bf, realized = _runner_lake()
    out = tmp_path / "cb1"
    res = ep.run_cb1_eval(pa, ledger, bf, realized, out)
    cfg = res["receipt_final"]["code_config"]
    assert cfg["shrinkage_n"] == ep.SHRINKAGE_N
    assert cfg["estimation_stop_tolerance"] == ep.ESTIMATION_TOLERANCE
    assert len(cfg["bands"]) == 5
    assert "cycled" in cfg["prior_definition"]
    assert cfg["bootstrap"] == {"n": 2000, "seed": 20261001}
