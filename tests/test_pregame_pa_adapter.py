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
    projected feature or probability (checked on the scored rows; the
    cold-start row stays excluded either way)."""
    cutoff = date(2025, 3, 15)
    proj = synth_projected(pa, cutoff, unseen_batter=777001)
    base, _ = ad.build_projected_pa_probs(proj, pa, models)
    mutated = pl.concat([
        pa,
        synth_pa_table(10, seed=99, day_offset=90),
    ])
    after, _ = ad.build_projected_pa_probs(proj, mutated, models)
    base_s = base.filter(pl.col("source_type") == ad.SOURCE_TYPE_ENTITY)
    after_s = after.filter(pl.col("source_type") == ad.SOURCE_TYPE_ENTITY)
    for c in ad.FEAT_H3 + ["p_h3_raw", "p_l5_raw"]:
        assert np.array_equal(base_s[c].to_numpy(), after_s[c].to_numpy()), c
    for c in ("source_type", "exclusion_reason"):
        assert (base[c].to_list() == after[c].to_list()), c


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
    """A (pitcher, batter) pair that never occurred in the PA table -- with
    BOTH entities carrying history -- is scored through its entity
    features; the probability equals the frozen coefficients applied to
    the asof-built features (the model consumes no player IDs)."""
    cutoff = date(2025, 3, 15)
    unseen_pair = (870001, 660005)
    pa2 = pa.filter(
        ~((pl.col("pitcher") == unseen_pair[0])
          & (pl.col("batter") == unseen_pair[1])))
    assert pa2.filter(
        (pl.col("pitcher") == unseen_pair[0])
        & (pl.col("batter") == unseen_pair[1])).height == 0
    proj = synth_projected(pa2, cutoff)
    # force slot 5 to the dropped batter: unseen pair, seen entities
    proj = proj.with_columns(pl.lit(unseen_pair[1]).alias("u_slot_5"))
    pf, summary = ad.build_projected_pa_probs(proj, pa2, models)
    assert summary["unseen_pairs"]["n_unseen_pairs"] == 1
    assert summary["unseen_pairs"]["handled_by"].startswith("feature-based")
    row_unseen = pf.filter(
        (pl.col("pitcher") == unseen_pair[0])
        & (pl.col("batter") == unseen_pair[1]))
    assert row_unseen.height == 1
    assert row_unseen["source_type"].to_list() == [ad.SOURCE_TYPE_ENTITY]
    assert np.isfinite(row_unseen["p_h3_raw"].to_numpy()).all()
    manual = ad.apply_h3_raw(row_unseen.select(ad.FEAT_H3),
                             models["block_2025H1"])
    assert np.allclose(row_unseen["p_h3_raw"].to_numpy(), manual, atol=1e-12)


def test_cold_start_slots_excluded_no_league_fallback(pa, models):
    """Cold-start slots (entity without PA-table history) are EXCLUDED
    from scoring with an explicit marker and reason -- never silently
    league-rate filled (owner rule). The frozen recipe declares no
    cold-start probability, so the PA probability stays null."""
    cutoff = date(2025, 3, 15)
    unseen_b = 777001
    proj = synth_projected(pa, cutoff, unseen_batter=unseen_b)
    pf, summary = ad.build_projected_pa_probs(proj, pa, models)
    assert summary["n_pa_rows_scored"] == 8
    assert summary["n_pa_rows_excluded_cold_start"] == 1
    cold = pf.filter(pl.col("batter") == unseen_b)
    assert cold.height == 1
    assert cold["source_type"].to_list() == [ad.SOURCE_TYPE_COLD_NO_PRIOR]
    assert cold["exclusion_reason"].to_list() == [ad.EXCLUSION_REASON_COLD]
    assert cold["p_h3_raw"].to_list() == [None]
    assert cold["p_l5_raw"].to_list() == [None]
    # scored slots are untouched by the cold row's league-derived features
    scored = pf.filter(pl.col("source_type") == ad.SOURCE_TYPE_ENTITY)
    assert scored.height == 8
    assert np.isfinite(scored["p_h3_raw"].to_numpy()).all()


def test_cold_start_ids_are_interchangeable(pa, models):
    """Two DIFFERENT never-seen batter IDs at the same slot against the
    same pitcher are both EXCLUDED with identical markers and identical
    (excluded) probabilities: there is no player-ID dependence and no
    league-rate fallback path."""
    cutoff = date(2025, 3, 15)
    proj_a = synth_projected(pa, cutoff, unseen_batter=777001)
    proj_b = synth_projected(pa, cutoff, unseen_batter=888001)
    pf_a, sum_a = ad.build_projected_pa_probs(proj_a, pa, models)
    pf_b, sum_b = ad.build_projected_pa_probs(proj_b, pa, models)
    u = pf_a.filter(pl.col("batter") == 777001)
    v = pf_b.filter(pl.col("batter") == 888001)
    assert u["source_type"].to_list() == [ad.SOURCE_TYPE_COLD_NO_PRIOR]
    assert v["source_type"].to_list() == [ad.SOURCE_TYPE_COLD_NO_PRIOR]
    assert u["exclusion_reason"].to_list() == [ad.EXCLUSION_REASON_COLD]
    assert v["exclusion_reason"].to_list() == [ad.EXCLUSION_REASON_COLD]
    assert u["p_h3_raw"].to_list() == [None]
    assert v["p_h3_raw"].to_list() == [None]
    # the scored 8 slots are identical across the two projections
    sa = pf_a.filter(pl.col("source_type") == ad.SOURCE_TYPE_ENTITY)
    sb = pf_b.filter(pl.col("source_type") == ad.SOURCE_TYPE_ENTITY)
    for c in ad.FEAT_H3 + ["p_h3_raw", "p_l5_raw"]:
        assert np.array_equal(sa[c].to_numpy(), sb[c].to_numpy()), c


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
    proj = synth_projected(pa, cutoff)
    bf = pl.DataFrame([{
        "game_pk": 999001, "side": "Bot", "pitcher": 870001,
        **{f"pmf37_{j}": v for j, v in enumerate(synth_bf37())},
    }])
    pf, summary = ad.build_projected_pa_probs(proj, pa, models,
                                              bf37_by_start=bf)
    assert summary["n_starts_pmf_computed"] == 1
    assert summary["n_starts_pmf_excluded_cold_slot"] == 0
    for tag in ("h3_raw", "l5_raw"):
        pmf = np.asarray(pf[f"pmf_{tag}"][0])
        assert pmf.shape == (24,)
        assert abs(pmf.sum() - 1.0) <= 1e-9
        assert (pmf >= 0).all()


def test_pmf_excluded_for_start_with_cold_slot(pa, models):
    """A start containing a cold-start slot is excluded from the count-PMF
    arms with an explicit reason; its rows carry null PMFs and never a
    league-rate-filled PMF."""
    cutoff = date(2025, 3, 15)
    proj = synth_projected(pa, cutoff, unseen_batter=777001)
    bf = pl.DataFrame([{
        "game_pk": 999001, "side": "Bot", "pitcher": 870001,
        **{f"pmf37_{j}": v for j, v in enumerate(synth_bf37())},
    }])
    pf, summary = ad.build_projected_pa_probs(proj, pa, models,
                                              bf37_by_start=bf)
    assert summary["n_starts_pmf_computed"] == 0
    assert summary["n_starts_pmf_excluded_cold_slot"] == 1
    assert pf["pmf_h3_raw"].null_count() == pf.height
    assert pf["pmf_l5_raw"].null_count() == pf.height


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


# ------------------------------------------------- checkpoint artifact
def test_missing_checkpoint_artifact_fails_loud(tmp_path):
    """The adapter loads ONLY the serialized checkpoint: a missing artifact
    fails loud with the named MISSING_CHECKPOINT_ARTIFACT error -- no
    league-rate fallback, no reconstruction fallback."""
    with pytest.raises(ad.AdapterError, match="MISSING_CHECKPOINT_ARTIFACT"):
        ad.load_serialized_checkpoint(tmp_path / "absent.json")


def _null_registration(monkeypatch, tmp_path):
    """Synthetic gate-DISABLED registration for artifact-format tests:
    these round-trip tests exercise the serialize/load format itself and
    must be independent of the COMMITTED registration (which now pins the
    real reconstructed checkpoint's canonical payload hash; a synthetic
    artifact would refuse to load against it)."""
    import json

    cfg = tmp_path / "freeze_pregame_pa_ext_v2_synth.json"
    cfg.write_text(json.dumps({
        "freeze_id": "pregame-pa-ext-v2-synth",
        "checkpoint_artifact": "checkpoints/h3_raw_checkpoint.json",
        "checkpoint_sha256_expected": None,
    }, indent=2), encoding="utf-8")
    monkeypatch.setattr(ad, "FREEZE_CONFIG_RELPATH", str(cfg))


def test_checkpoint_serialize_load_roundtrip(pa, models, tmp_path,
                                             monkeypatch):
    """serialize_checkpoint -> load_serialized_checkpoint reproduces the
    verified coefficients exactly and records the matching sha256 pin."""
    _null_registration(monkeypatch, tmp_path)
    verification = {"block_2025H1": {"n_rows": 10, "max_abs_diff": 0.0}}
    out = tmp_path / "h3_raw_checkpoint.json"
    ad.serialize_checkpoint(models, verification, out)
    loaded, meta = ad.load_serialized_checkpoint(out)
    assert meta["sha256"] == ad.checkpoint_sha256(
        ad.checkpoint_payload(models, verification))
    assert meta["verification"] == verification
    assert set(loaded) == set(models)
    for block in models:
        for key in ("mean", "scale", "coef", "intercept", "features"):
            assert loaded[block][key] == models[block][key], (block, key)


def test_checkpoint_hash_pin_rejects_tamper(pa, models, tmp_path):
    """Any byte-level tamper with the coefficients breaks the sha256 pin
    and fails loud with CHECKPOINT_HASH_MISMATCH."""
    out = tmp_path / "h3_raw_checkpoint.json"
    ad.serialize_checkpoint(models, None, out)
    import json
    doc = json.loads(out.read_text(encoding="utf-8"))
    doc["payload"]["blocks"]["block_2024H2"]["coef"][0] += 1e-12
    out.write_text(json.dumps(doc, indent=2, sort_keys=True),
                   encoding="utf-8")
    with pytest.raises(ad.AdapterError, match="CHECKPOINT_HASH_MISMATCH"):
        ad.load_serialized_checkpoint(out)


def test_checkpoint_roundtrip_via_build_checkpoint_module(models, tmp_path,
                                                          monkeypatch):
    """build_checkpoint.reconstruct's serialize/load round-trip helpers are
    importable and consistent with the adapter's artifact format (no lake
    access: only serialization is exercised)."""
    _null_registration(monkeypatch, tmp_path)
    sys.path.insert(0, str(HERE / "research" / "offseason_2026"))
    from pregame_pa_ext import build_checkpoint as bc  # noqa: E402
    out = tmp_path / "h3_raw_checkpoint.json"
    ad.serialize_checkpoint(models, None, out)
    models_loaded, meta = ad.load_serialized_checkpoint(out)
    assert bc.BLOCK_TRAIN_END["block_2024H2"] == (2024, 6, 30)
    assert meta["path"] == str(out)
    assert set(models_loaded) == set(models)
