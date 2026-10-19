"""Synthetic tests for the pregame-pa-ext-v2 projected per-PA adapter.

No real data, no real scoring, no private-lake reads: every test runs the
adapter's pure functions over synthetic frames only. Real-lineage helpers
(verify_checkpoint, run_real) are never invoked here.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import pregame_pa_ext.adapter as ad  # noqa: E402


# --------------------------------------------------------------- fixtures
def synth_pa_table(n_days: int = 40, seed: int = 7,
                   day_offset: int = 0) -> pl.DataFrame:
    """Synthetic PA table: 3 pitchers x 6 batters, one game per day,
    12 PAs per game, y ~ Bernoulli(p_entity)."""
    rng = np.random.default_rng(seed)
    pitchers = [870001, 870002, 870003]
    batters = [660001, 660002, 660003, 660004, 660005, 660006,
               660007, 660008, 660009]
    p_k = {870001: 0.25, 870002: 0.20, 870003: 0.30}
    b_k = {b: 0.20 + 0.01 * i for i, b in enumerate(batters)}
    rows = []
    for d in range(n_days):
        gd = date(2025, 1, 1) + timedelta(days=d + day_offset)
        pk = pitchers[d % 3]
        game_pk = 900000 + d + 1000 * day_offset
        for slot in range(9):
            bt = batters[slot % len(batters)]
            for _ in range(2):
                p = 0.5 * p_k[pk] + 0.5 * b_k[bt]
                rows.append({
                    "game_pk": game_pk, "at_bat_number": len(rows) + 1,
                    "batter": bt, "pitcher": pk, "game_date": gd,
                    "y": int(rng.random() < p),
                })
    return pl.DataFrame(rows)


def synth_projected(pa: pl.DataFrame, game_date, game_pk: int = 999001,
                    pitcher: int = 870001, unseen_batter: int | None = None,
                    ) -> pl.DataFrame:
    """One projected start with 9 covered slots; optional unseen batter in
    slot 9 (never occurs in the PA table)."""
    batters = sorted(pa["batter"].unique().to_list())
    slots = {}
    for i in range(9):
        bt = batters[i % len(batters)]
        if i == 8 and unseen_batter is not None:
            bt = unseen_batter
        slots[f"u_slot_{i + 1}"] = bt
    return pl.DataFrame([{
        "game_pk": game_pk, "side": "Bot", "pitcher": pitcher,
        "game_date": game_date, "opp_team": "OPP",
        "n_prior_team_games": 10, "n_pool_distinct": 9,
        "nine_distinct": len(set(slots.values())),
        **slots,
        **{f"sup_slot_{i + 1}": 9 - (i % 3) for i in range(9)},
        **{f"how_slot_{i + 1}": "greedy" for i in range(9)},
        "n_fallback_slots": 0, "n_distinct_ids": len(set(slots.values())),
    }])


def synth_models(pa: pl.DataFrame) -> dict:
    """Frozen-recipe checkpoint fit on synthetic training rows
    (StandardScaler + LogisticRegression(C=1.0, max_iter=1000)); the same
    coefficients serve all three blocks so single-block scoring covers the
    block-routing logic."""
    p_daily = ad.entity_daily_state(pa, "pitcher")
    b_daily = ad.entity_daily_state(pa, "batter")
    lg = ad.league_daily_state(pa)
    rows = pa.select(
        "game_pk", "at_bat_number", "batter", "pitcher", "game_date",
    ).sort("game_date")
    feat = ad.attach_prior_features(rows, p_daily, b_daily, lg)
    feat = feat.join(pa.select("game_pk", "at_bat_number", "batter", "y"),
                     on=["game_pk", "at_bat_number", "batter"], how="inner")
    # day-1 league state is 0/0; the frozen fit windows never include it
    feat = feat.filter(pl.col("lg_rate").is_finite())
    model = ad.fit_models_from_frames(feat, feat)
    return {"block_2024H2": model, "block_2025H1": model,
            "confirm_2025H2": model}


def synth_bf37(h: float = 0.06) -> np.ndarray:
    pmf37 = np.empty(37)
    surv = 1.0
    for n in range(36):
        pmf37[n] = surv * h
        surv *= 1 - h
    pmf37[36] = surv
    return pmf37


@pytest.fixture(scope="module")
def pa() -> pl.DataFrame:
    return synth_pa_table()


@pytest.fixture(scope="module")
def models(pa) -> dict:
    return synth_models(pa)


# ------------------------------------------------------------ cutoff gate
def test_cutoff_enforcement_strictly_before(pa, models):
    """Source dates must be strictly < forecast cutoff; the same-day PA
    rows of the forecasted game are excluded by construction."""
    cutoff = date(2025, 3, 15)
    proj = synth_projected(pa, cutoff, unseen_batter=777001)
    pf, _ = ad.build_projected_pa_probs(proj, pa, models)
    for col in ad.SRC_DATE_COLS + ["lg_src_date"]:
        assert pf.filter(pl.col(col) >= pl.col("game_date")).height == 0
        assert pf.filter(pl.col(col).is_null()).height == 0
    # the forecasted game_pk is absent from the PA table -> nothing from it
    # can leak into the source dates
    assert pa.filter(pl.col("game_pk") == 999001).height == 0


def test_cutoff_gate_fails_loud_on_future_source(pa):
    """A manually injected source date >= game_date trips the gate."""
    cutoff = date(2025, 3, 15)
    proj = synth_projected(pa, cutoff)
    long, _ = ad.projected_long(proj)
    p_daily = ad.entity_daily_state(pa, "pitcher")
    b_daily = ad.entity_daily_state(pa, "batter")
    lg = ad.league_daily_state(pa)
    pf = ad.attach_prior_features(long, p_daily, b_daily, lg)
    bad = pf.with_columns(pl.date(2025, 3, 20).alias("src_date_pitcher"))
    with pytest.raises(ad.AdapterError, match="cutoff gate"):
        ad.assert_cutoff(bad)


def test_no_current_or_future_mutation(pa, models):
    """Adding PA rows ON or AFTER the forecast date must not change any
    projected feature or probability."""
    cutoff = date(2025, 3, 15)
    proj = synth_projected(pa, cutoff, unseen_batter=777001)
    base, _ = ad.build_projected_pa_probs(proj, pa, models)
    mutated = pl.concat([
        pa,
        synth_pa_table(10, seed=99, day_offset=90),
    ])
    after, _ = ad.build_projected_pa_probs(proj, mutated, models)
    for c in ad.FEAT_H3 + ["p_h3_raw", "p_l5_raw"]:
        assert np.array_equal(base[c].to_numpy(), after[c].to_numpy()), c


# ------------------------------------------------------------ shape gates
def test_nine_distinct_batters_per_start(pa, models):
    cutoff = date(2025, 3, 15)
    proj = synth_projected(pa, cutoff)
    long, n_uncovered = ad.projected_long(proj)
    assert n_uncovered == 0
    per_start = long.group_by("game_pk", "side", "pitcher").agg(
        n=pl.len(), n_batt=pl.col("batter").n_unique())
    assert (per_start["n"] == 9).all()
    assert (per_start["n_batt"] == 9).all()


def test_identity_gate_rejects_duplicate_keys(pa, models):
    cutoff = date(2025, 3, 15)
    proj = synth_projected(pa, cutoff)
    pf, _ = ad.build_projected_pa_probs(proj, pa, models)
    ad.assert_identity(pf)
    with pytest.raises(ad.AdapterError, match="identity gate"):
        ad.assert_identity(pl.concat([pf, pf]))
    with pytest.raises(ad.AdapterError, match="identity gate"):
        ad.assert_identity(pf.with_columns(pl.lit(None).alias("batter")))


# ---------------------------------------------------------- unseen pairs
def test_unseen_pairs_scored_via_features(pa, models):
    """A (pitcher, batter) pair that never occurred in the PA table is
    scored through its entity features; the probability equals the frozen
    coefficients applied to the asof-built features (the model consumes no
    player IDs)."""
    cutoff = date(2025, 3, 15)
    unseen_b = 777001
    proj = synth_projected(pa, cutoff, unseen_batter=unseen_b)
    pf, summary = ad.build_projected_pa_probs(proj, pa, models)
    assert summary["unseen_pairs"]["n_unseen_pairs"] == 1
    assert summary["unseen_pairs"]["handled_by"].startswith("feature-based")
    row_unseen = pf.filter(pl.col("batter") == unseen_b)
    assert row_unseen.height == 1
    assert np.isfinite(row_unseen["p_h3_raw"].to_numpy()).all()
    manual = ad.apply_h3_raw(row_unseen.select(ad.FEAT_H3),
                             models["block_2025H1"])
    assert np.allclose(row_unseen["p_h3_raw"].to_numpy(), manual, atol=1e-12)


def test_unseen_batter_ids_are_interchangeable(pa, models):
    """Two DIFFERENT never-seen batter IDs at the same slot against the
    same pitcher must produce identical probabilities: the frozen
    checkpoint scores features only (cold-start league fallback), proving
    there is no player-ID memorization."""
    cutoff = date(2025, 3, 15)
    proj_a = synth_projected(pa, cutoff, unseen_batter=777001)
    proj_b = synth_projected(pa, cutoff, unseen_batter=888001)
    pf_a, sum_a = ad.build_projected_pa_probs(proj_a, pa, models)
    pf_b, sum_b = ad.build_projected_pa_probs(proj_b, pa, models)
    assert sum_a["unseen_pairs"]["n_unseen_pairs"] == 1
    assert sum_b["unseen_pairs"]["n_unseen_pairs"] == 1
    u = pf_a.filter(pl.col("batter") == 777001)
    v = pf_b.filter(pl.col("batter") == 888001)
    # both are cold-start: features derive from the league fallback
    assert u["src_type_batter"].to_list() == [ad.SOURCE_TYPE_COLD]
    assert v["src_type_batter"].to_list() == [ad.SOURCE_TYPE_COLD]
    assert u["cold_start"].to_list() == [1]
    for c in ad.FEAT_H3:
        assert np.array_equal(u[c].to_numpy(), v[c].to_numpy()), c
    assert np.array_equal(u["p_h3_raw"].to_numpy(), v["p_h3_raw"].to_numpy())
    assert np.array_equal(u["p_l5_raw"].to_numpy(), v["p_l5_raw"].to_numpy())


# ------------------------------------------------------------ PMF arms
def test_count_pmf_both_arms_valid_and_distinct():
    p9_h3 = np.linspace(0.18, 0.30, 9)
    p9_l5 = np.full(9, 0.24)
    bf37 = synth_bf37()
    arms = ad.start_count_pmfs(p9_h3, p9_l5, bf37)
    for tag in ("h3_raw", "l5_raw"):
        pmf = arms[f"pmf_{tag}"]
        assert pmf.shape == (24,)
        assert abs(pmf.sum() - 1.0) <= 1e-9
        assert (pmf >= 0).all()
        assert (np.diff(np.cumsum(pmf)) >= -1e-12).all()
        expected_mean = float(
            (ad.bf_pmf_from_37(bf37) * ad.N_ARR[:, 0]
             * ad.cycled_cond_mean(p9_h3 if tag == "h3_raw" else p9_l5)
             ).sum())
        assert abs(arms[f"mean_k_{tag}"] - expected_mean) < 1e-12


def test_pmf_h3_arm_matches_manual_cycled_prefix_mean():
    """H3-raw arm = mixture over Binom(k; n, pbar_n) with pbar_n the
    cycled prefix mean of the 9 projected per-PA probs."""
    p9 = np.linspace(0.20, 0.28, 9)
    bf_ext = ad.bf_pmf_from_37(synth_bf37())
    pbar = ad.cycled_cond_mean(p9)
    with np.errstate(divide="ignore"):
        logp = np.log(pbar)
        log1mp = np.log1p(-pbar)
    from math import lgamma
    manual = np.zeros(24)
    for n in range(1, 61):
        for k in range(24):
            if k > n:
                continue
            bc = lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1)
            manual[k] += bf_ext[n - 1] * np.exp(
                bc + k * logp[n - 1] + (n - k) * log1mp[n - 1])
    manual[23] += 1.0 - manual.sum()
    arms = ad.start_count_pmfs(p9, p9, synth_bf37())
    assert np.allclose(arms["pmf_h3_raw"], manual, atol=1e-10)


def test_pmf_differs_when_per_pa_probs_differ():
    p9_a = np.full(9, 0.20)
    p9_b = np.linspace(0.10, 0.35, 9)
    bf37 = synth_bf37()
    arms_a = ad.start_count_pmfs(p9_a, p9_a, bf37)
    arms_b = ad.start_count_pmfs(p9_b, p9_b, bf37)
    assert not np.allclose(arms_a["pmf_h3_raw"], arms_b["pmf_h3_raw"])
    # log5 arm is a pass-through when inputs equal the target probs
    assert np.allclose(arms_a["pmf_h3_raw"], arms_a["pmf_l5_raw"])


def test_full_pipeline_attaches_valid_pmfs(pa, models):
    cutoff = date(2025, 3, 15)
    proj = synth_projected(pa, cutoff, unseen_batter=777001)
    bf = pl.DataFrame([{
        "game_pk": 999001, "side": "Bot", "pitcher": 870001,
        **{f"pmf37_{j}": v for j, v in enumerate(synth_bf37())},
    }])
    pf, _ = ad.build_projected_pa_probs(proj, pa, models, bf37_by_start=bf)
    for tag in ("h3_raw", "l5_raw"):
        pmf = np.asarray(pf[f"pmf_{tag}"][0])
        assert pmf.shape == (24,)
        assert abs(pmf.sum() - 1.0) <= 1e-9
        assert (pmf >= 0).all()


# ----------------------------------------------------- fail-loud guards
def test_fail_loud_on_missing_ew_columns(pa, models):
    cutoff = date(2025, 3, 15)
    proj = synth_projected(pa, cutoff)
    pf, _ = ad.build_projected_pa_probs(proj, pa, models)
    with pytest.raises(ad.AdapterError, match="missing required feature"):
        ad.require_feature_columns(pf.drop("ew_pitcher"))
    with pytest.raises(ad.AdapterError, match="missing required feature"):
        ad.require_feature_columns(pf.drop("ew_batter"))
    with pytest.raises(ad.AdapterError, match="missing required feature"):
        ad.apply_h3_raw(pf.drop("ew_pitcher"), models["block_2025H1"])


def test_write_once(pa, models, tmp_path):
    cutoff = date(2025, 3, 15)
    proj = synth_projected(pa, cutoff)
    pf, _ = ad.build_projected_pa_probs(proj, pa, models)
    out = tmp_path / "out.parquet"
    ad.write_once(pf, out)
    assert out.exists()
    with pytest.raises(ad.AdapterError, match="write-once violation"):
        ad.write_once(pf, out)


def test_no_real_data_read(tmp_path, monkeypatch):
    """The lake loaders fail loud when pointed at an empty directory; the
    injected-frame pipeline itself never reads from disk."""
    monkeypatch.setattr(ad, "PREGAME_STATE_DIR", tmp_path)
    monkeypatch.setattr(ad, "OVERNIGHT_P2_DIR", tmp_path)
    with pytest.raises(ad.AdapterError):
        ad.load_projected_lineups(tmp_path)
    with pytest.raises(ad.AdapterError):
        ad.load_pa_table(tmp_path)
