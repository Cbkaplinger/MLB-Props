"""pregame-pa-ext-v1 tests: registered checks (a)-(f), synthetic + real.

(a) mutating the current-game outcomes of a target start cannot change its
    projected PA probabilities;
(b) appending future games cannot change them;
(c) cutoff enforcement: every feature source date strictly < the start's
    forecast cutoff;
(d) 9 distinct projected batters per start where coverage allows;
(e) PMF normalization + nonnegativity (payload PMFs reproduce from stored
    per-PA probs + the shared BF PMF);
(f) key uniqueness across the 7,194 starts.

Real-lineage tests use the read-only sources (pa_table, accepted
unique-batter v2 lineups, bf_forecasts cohort, the frozen payload, and the
verified model artifacts) through the SAME code path as the build.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

WORK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORK / "scripts"))
import paext_core as core  # noqa: E402

RNG_SEED = 20261014


def _rand_pmf37(rng: np.random.Generator) -> np.ndarray:
    p = rng.dirichlet(np.full(37, 0.7))
    return p / p.sum()


# =====================================================================
# synthetic lineage
# =====================================================================
@pytest.fixture(scope="module")
def syn():
    rng = np.random.default_rng(RNG_SEED)
    P1, P2 = 1001, 1002
    B = {i: 2000 + i for i in range(1, 10)}  # B1..B9

    def game(gk, d, pitcher, batters, n_pa=3, y=None):
        rows = []
        for k, b in enumerate(batters):
            for j in range(n_pa):
                rows.append({
                    "game_pk": gk, "game_date": d, "season": d.year,
                    "at_bat_number": 10 * k + j, "batter": b,
                    "pitcher": pitcher, "p_throws": "R", "stand": "R",
                    "inning_topbot": "Top", "pitcher_role": "starter_pa",
                    "y": int(rng.integers(0, 2)) if y is None else y,
                })
        return rows

    pa_rows = []
    # 2022 warm-up (state only, never fitted)
    pa_rows += game(1, date(2022, 9, 1), P1, [B[i] for i in range(1, 7)])
    pa_rows += game(2, date(2022, 9, 2), P2, [B[i] for i in range(1, 7)])
    # 2024 prior games (block_2024H2 window)
    pa_rows += game(10, date(2024, 7, 10), P1, [B[i] for i in range(1, 7)])
    pa_rows += game(11, date(2024, 7, 12), P2, [B[i] for i in range(3, 10)])
    # the TARGET starts' own (current-game) PAs - present in pa, but the
    # projected probabilities must never read them
    pa_rows += game(20, date(2024, 7, 20), P1,
                    [B[i] for i in range(1, 10)])
    pa_rows += game(21, date(2024, 7, 20), P2,
                    [B[i] for i in range(1, 10)])
    pa = pl.DataFrame(pa_rows).with_columns(
        pl.col("y").cast(pl.Int8))

    proj = pl.DataFrame({
        "game_pk": [20, 21],
        "side": ["Top", "Bot"],
        "pitcher": [P1, P2],
        "game_date": [date(2024, 7, 20), date(2024, 7, 20)],
        "opp_team": ["A", "B"], "n_prior_team_games": [2, 2],
        "n_pool_distinct": [9, 9], "nine_distinct": [0, 1],
        **{f"u_slot_{i}": [B[i], B[i]] for i in range(1, 9)},
        "u_slot_9": [None, B[9]],
        **{f"sup_slot_{i}": [0, 0] for i in range(1, 10)},
        **{f"how_slot_{i}": ["greedy", "greedy"] for i in range(1, 10)},
        "n_fallback_slots": [1, 0], "n_distinct_ids": [8, 9],
    })

    pmfs = [_rand_pmf37(rng) for _ in range(2)]
    fc = pl.DataFrame({
        "game_pk": [20, 21], "side": ["Top", "Bot"],
        "pitcher": [P1, P2],
        "game_date": [date(2024, 7, 20), date(2024, 7, 20)],
        "prior_n": [2, 2], "prior_mean": [0.2, 0.2], "lg_mean": [0.22, 0.22],
        "prior_mean_shrunk_w50": [0.21, 0.21], "cold_start": [0, 0],
        "realized_bf": [21, 19],
        **{f"pmf37_{j}": [pmfs[r][j] for r in range(2)]
           for j in range(37)},
    })

    p_daily = core.v1.entity_daily_state(pa, "pitcher")
    b_daily = core.v1.entity_daily_state(pa, "batter")
    lg = core.v1.league_daily_state(pa)
    feat = core.realized_row_features(pa, p_daily, b_daily, lg).join(
        pa.select("game_pk", "at_bat_number", "batter", "y"),
        on=["game_pk", "at_bat_number", "batter"], how="inner")
    # eligible-frame rule: rows on the first league day have no prior
    # league support (lg_rate NaN from 0/0 under the v1 daily-state
    # machinery) and are excluded from fitting, exactly as features_v3
    # excludes them (its league_daily guards with when(lg_n_prior > 0))
    feat = feat.filter(pl.col("lg_rate").is_finite())
    model = core.fit_models_from_frames(feat, feat)
    models = {"block_2024H2": model}
    return {"pa": pa, "proj": proj, "fc": fc,
            "p_daily": p_daily, "b_daily": b_daily, "lg": lg,
            "models": models, "B": B}


def _syn_start_probs(syn, pa_override: pl.DataFrame | None = None,
                     start_gk: int = 20):
    pa = pa_override if pa_override is not None else syn["pa"]
    p_daily = core.v1.entity_daily_state(pa, "pitcher")
    b_daily = core.v1.entity_daily_state(pa, "batter")
    lg = core.v1.league_daily_state(pa)
    proj = syn["proj"].filter(pl.col("game_pk") == start_gk)
    long = core.projected_long(proj)
    pf = core.attach_prior_features(long, p_daily, b_daily, lg)
    pf = core.add_block(pf)
    core.assert_cutoff(pf)
    pf = core.arm_probs(pf, syn["models"])
    return pf.sort("slot")


def test_syn_fallback_fill_and_cutoff(syn):
    pf = _syn_start_probs(syn)
    fb = pf.filter(pl.col("slot") == 9)
    assert fb.height == 1
    assert fb["slot_uncovered"][0] is True
    assert fb["src_type_batter"][0] == core.SOURCE_TYPE_FALLBACK
    # league-rate fill: n_prior_batter = 0 and both batter rates = lg_rate
    assert fb["n_prior_batter"][0] == 0
    assert fb["p_batter_prior_w150"][0] == pytest.approx(
        fb["lg_rate"][0], abs=0.0)
    assert fb["ew_batter"][0] == pytest.approx(fb["lg_rate"][0], abs=0.0)
    assert fb["cold_start"][0] == 1
    # covered slots never carry the fallback marker
    assert pf.filter(pl.col("slot") != 9)[
        "src_type_batter"].unique().to_list() == [core.SOURCE_TYPE_ENTITY]
    stats = core.assert_cutoff(pf)
    assert stats["min_source_lag_days"] >= 1


def test_syn_current_game_mutation_invariance(syn):
    """(a) synthetic: flipping the target game's own outcomes cannot move
    its projected PA probabilities."""
    base = _syn_start_probs(syn)
    mut = syn["pa"].with_columns(
        pl.when(pl.col("game_pk") == 20)
        .then(1 - pl.col("y")).otherwise(pl.col("y")).alias("y")
    )
    after = _syn_start_probs(syn, pa_override=mut)
    for col in ("p_h3_raw", "p_h3_cal", "p_l5_raw", "p_l5_cal"):
        assert np.array_equal(
            base[col].to_numpy(), after[col].to_numpy()), col
    # features themselves are unchanged, not just the clipped outputs
    for col in ("p_pitcher_prior_w150", "p_batter_prior_w150", "ew_pitcher",
                "ew_batter", "lg_rate", "n_prior_pitcher", "n_prior_batter"):
        assert base[col].to_numpy().tolist() == \
            after[col].to_numpy().tolist(), col


def test_syn_future_append_invariance(syn):
    """(b) synthetic: appending future games (after the target cutoff)
    cannot move the projected PA probabilities."""
    base = _syn_start_probs(syn)
    B = syn["B"]
    extra = pl.DataFrame([{
        "game_pk": 900, "game_date": date(2024, 7, 25), "season": 2024,
        "at_bat_number": j, "batter": b, "pitcher": 1001,
        "p_throws": "R", "stand": "R", "inning_topbot": "Top",
        "pitcher_role": "starter_pa", "y": 1,
    } for j, b in enumerate([B[1], B[2], B[3]])]).with_columns(
        pl.col("y").cast(pl.Int8))
    after = _syn_start_probs(
        syn, pa_override=pl.concat([syn["pa"], extra], how="vertical"))
    for col in ("p_h3_raw", "p_h3_cal", "p_l5_raw", "p_l5_cal"):
        assert np.array_equal(
            base[col].to_numpy(), after[col].to_numpy()), col


def test_syn_pmf_normalization_and_keys(syn):
    """(e)+(f) synthetic: PMF normalization/nonneg and start-key uniqueness."""
    rng = np.random.default_rng(7)
    fc = syn["fc"]
    long = core.projected_long(syn["proj"])
    dup = long.group_by("game_pk", "side", "pitcher", "slot").agg(
        n=pl.len()).filter(pl.col("n") > 1).height
    assert dup == 0
    for s in fc.to_dicts():
        bf37 = np.array([s[f"pmf37_{j}"] for j in range(37)])
        for p9 in (rng.uniform(0.1, 0.4, 9), np.full(9, 0.22)):
            pk, mean_k, bf_ext, pbar = core.start_count_pmf(p9, bf37)
            assert pk.shape == (core.K_MAX,)
            assert float(pk.min()) >= 0.0
            assert abs(float(pk.sum()) - 1.0) <= 1e-9
            assert 0.0 < mean_k < 60.0
            assert abs(float(bf_ext.sum()) - 1.0) <= 1e-9
            assert np.all(np.diff(np.cumsum(pk)) >= -1e-12)


# =====================================================================
# real lineage
# =====================================================================
def _real_available() -> bool:
    return (
        (core.P2_DATA / "pa_table.parquet").exists()
        and (core.BFW / "bf_forecasts.parquet").exists()
        and (core.PREGAME_STATE / "data" /
             "projected_lineups_variant_v2.parquet").exists()
    )


@pytest.fixture(scope="module")
def real():
    if not _real_available():
        pytest.skip("real-lineage sources not available")
    pa = pl.read_parquet(core.P2_DATA / "pa_table.parquet")
    proj_u = pl.read_parquet(
        core.PREGAME_STATE / "data" /
        "projected_lineups_variant_v2.parquet")
    fc = (
        pl.read_parquet(core.BFW / "bf_forecasts.parquet")
        .filter(
            (pl.col("game_date") >= core.WINDOW[0])
            & (pl.col("game_date") <= core.WINDOW[1]))
        .select("game_pk", "side", "pitcher", "game_date")
    )
    payload = None
    if core.PAYLOAD.exists():
        payload = pl.read_parquet(core.PAYLOAD)
    models = None
    if all((WORK / "artifacts" / f"h3_models_{b}.joblib").exists()
           for b in core.BLOCKS):
        import joblib
        models = {}
        for b in core.BLOCKS:
            d = joblib.load(WORK / "artifacts" / f"h3_models_{b}.joblib")
            models[b] = (d["scaler"], d["logistic"], d["h3_calibrator"],
                         d["l5_calibrator"])
    else:
        feat = pl.read_parquet(core.P2_DATA / "features_v3.parquet")
        models, _ = core.fit_models_verified(feat, pa)
    p_daily = core.v1.entity_daily_state(pa, "pitcher")
    b_daily = core.v1.entity_daily_state(pa, "batter")
    lg = core.v1.league_daily_state(pa)
    return {"pa": pa, "proj_u": proj_u, "fc": fc, "payload": payload,
            "models": models, "p_daily": p_daily, "b_daily": b_daily,
            "lg": lg}


@pytest.mark.skipif(not _real_available(), reason="real sources missing")
class TestRealLineage:
    def test_cutoff_enforcement(self, real):
        """(c) real: feature source dates strictly < forecast cutoff."""
        proj_u = real["proj_u"]
        step = max(1, proj_u.height // 120)
        sl = proj_u.gather(list(range(0, proj_u.height, step)))
        long = core.projected_long(sl)
        pf = core.attach_prior_features(
            long, real["p_daily"], real["b_daily"], real["lg"])
        pf = core.add_block(pf)
        stats = core.assert_cutoff(pf)
        assert stats["min_source_lag_days"] >= 1
        assert pf["src_type_batter"].is_in([
            core.SOURCE_TYPE_ENTITY, core.SOURCE_TYPE_COLD,
            core.SOURCE_TYPE_FALLBACK]).all()

    def test_current_game_mutation_invariance(self, real):
        """(a) real: flipping the target game's own realized outcomes in
        pa_table cannot move its projected PA probabilities."""
        payload = real["payload"]
        assert payload is not None, "run scripts/build_pa_ext.py first"
        s0 = payload.sort("game_date", "game_pk", "side").head(1).to_dicts()[0]
        gk, side, pitcher = s0["game_pk"], s0["side"], s0["pitcher"]
        mut = real["pa"].with_columns(
            pl.when(pl.col("game_pk") == gk)
            .then(1 - pl.col("y")).otherwise(pl.col("y")).alias("y")
        )
        p_daily = core.v1.entity_daily_state(mut, "pitcher")
        b_daily = core.v1.entity_daily_state(mut, "batter")
        lg = core.v1.league_daily_state(mut)
        proj = real["proj_u"].filter(
            (pl.col("game_pk") == gk) & (pl.col("side") == side)
            & (pl.col("pitcher") == pitcher))
        pf = core.arm_probs(
            core.add_block(core.attach_prior_features(
                core.projected_long(proj), p_daily, b_daily, lg)),
            real["models"]).sort("slot")
        for tag in ("h3_raw", "h3_cal", "l5_raw", "l5_cal"):
            got = pf[f"p_{tag}"].to_numpy()
            want = np.array([s0[f"p_{tag}_{i}"]
                             for i in range(1, 10)])
            assert float(np.abs(got - want).max()) <= 1e-12, tag

    def test_future_append_invariance(self, real):
        """(b) real: appending synthetic future games (after the cohort
        end) cannot move the projected PA probabilities."""
        payload = real["payload"]
        assert payload is not None, "run scripts/build_pa_ext.py first"
        s0 = payload.sort("game_date", "game_pk", "side").head(1).to_dicts()[0]
        gk, side, pitcher = s0["game_pk"], s0["side"], s0["pitcher"]
        batters = [s0[f"batter_slot_{i}"] for i in range(1, 10)]
        extra = pl.DataFrame([{
            "game_pk": 999_000_001, "game_date": date(2026, 4, 1),
            "season": 2026, "at_bat_number": 10 * j, "batter": b,
            "pitcher": pitcher, "p_throws": "R", "stand": "R",
            "inning_topbot": "Top", "pitcher_role": "starter_pa", "y": 1,
        } for j, b in enumerate(batters)]).with_columns(
            pl.col("season").cast(pl.Int32), pl.col("y").cast(pl.Int8))
        extra = extra.select(list(real["pa"].columns))
        pa2 = pl.concat([real["pa"], extra], how="vertical")
        p_daily = core.v1.entity_daily_state(pa2, "pitcher")
        b_daily = core.v1.entity_daily_state(pa2, "batter")
        lg = core.v1.league_daily_state(pa2)
        proj = real["proj_u"].filter(
            (pl.col("game_pk") == gk) & (pl.col("side") == side)
            & (pl.col("pitcher") == pitcher))
        pf = core.arm_probs(
            core.add_block(core.attach_prior_features(
                core.projected_long(proj), p_daily, b_daily, lg)),
            real["models"]).sort("slot")
        for tag in ("h3_raw", "h3_cal", "l5_raw", "l5_cal"):
            got = pf[f"p_{tag}"].to_numpy()
            want = np.array([s0[f"p_{tag}_{i}"]
                             for i in range(1, 10)])
            assert float(np.abs(got - want).max()) <= 1e-12, tag

    def test_nine_distinct_and_fallback(self, real):
        """(d) real: nine distinct projected batters wherever coverage
        allows (accepted v2: everywhere); fallback count recorded."""
        payload = real["payload"]
        assert payload is not None, "run scripts/build_pa_ext.py first"
        assert payload.height == core.EXPECTED_N_STARTS
        bcols = [f"batter_slot_{i}" for i in range(1, 10)]
        nd = np.array([len(set(r)) for r in
                       payload.select(bcols).to_numpy()])
        coverage_allows = (real["proj_u"]["nine_distinct"] == 1).to_numpy()
        assert (nd[coverage_allows] == 9).all()
        # this card's league-rate fill triggers only on NULL slots: 0 here.
        # The 52 v2 'n_fallback_slots_lineup' slots are the accepted
        # registration's team-usage fallback, which still assign a real
        # batter (never null) and are reported, not asserted zero.
        assert int(payload["n_fallback_slots"].sum()) == 0
        assert int(payload["n_fallback_slots_lineup"].sum()) == 52
        assert (payload["n_fallback_slots_lineup"] >=
                payload["n_fallback_slots"]).all()
        # no slot source type may claim the fallback on this population
        stypes = payload.select(
            [f"slot_src_type_{i}" for i in range(1, 10)]).to_numpy()
        assert core.SOURCE_TYPE_FALLBACK not in set(stypes.ravel().tolist())

    def test_pmf_normalization_and_recompute(self, real):
        """(e) real: payload PMFs normalized/nonneg and reproducible from
        the stored per-PA probs + the shared BF PMF."""
        payload = real["payload"]
        assert payload is not None, "run scripts/build_pa_ext.py first"
        for tag in ("h3_raw", "l5_raw"):
            pmf = payload.select(core.PMF_COLS[tag]).to_numpy()
            assert float(pmf.min()) >= 0.0
            assert float(np.abs(pmf.sum(axis=1) - 1.0).max()) <= 1e-9
        bf37 = payload.select(core.PMF37_COLS).to_numpy()
        for tag in ("h3_raw", "l5_raw"):
            p9 = payload.select(
                [f"p_{tag}_{i}" for i in range(1, 10)]).to_numpy()
            for r in range(0, payload.height, 501):
                pk, mean_k, _, _ = core.start_count_pmf(p9[r], bf37[r])
                stored = np.array([
                    payload[core.PMF_COLS[tag][k]][r]
                    for k in range(core.K_MAX)])
                assert np.array_equal(pk, stored), (tag, r)
                assert mean_k == payload[f"mean_k_{tag}"][r]

    def test_key_uniqueness(self, real):
        """(f) real: unique start keys across the 7,194 starts."""
        payload = real["payload"]
        assert payload is not None, "run scripts/build_pa_ext.py first"
        assert payload.height == core.EXPECTED_N_STARTS
        dup = payload.group_by("game_pk", "side", "pitcher").agg(
            n=pl.len()).filter(pl.col("n") > 1).height
        assert dup == 0
        keys_payload = set(zip(
            payload["game_pk"].to_list(), payload["side"].to_list(),
            payload["pitcher"].to_list()))
        keys_fc = set(zip(
            real["fc"]["game_pk"].to_list(), real["fc"]["side"].to_list(),
            real["fc"]["pitcher"].to_list()))
        assert keys_payload == keys_fc
        # forecast cutoff recorded per start and equal to the slate date
        assert (payload["forecast_cutoff"] ==
                payload["game_date"]).all()
        assert (payload["max_src_date"] <
                payload["forecast_cutoff"]).all()
