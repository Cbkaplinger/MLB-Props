"""End-to-end synthetic tests for the bf37 wiring in pregame-pa-ext-v2.

Wires the registered BF PMF artifact (bf-workload-v1
``data/bf_forecasts.parquet`` shape: start grain (game_pk, side, pitcher)
+ ``pmf37_0..36``) through ``run_real`` -- the actual execution entry
point -- against a fully synthetic private-lake stand-in (tmp_path
directories + monkeypatched module constants). No real data, no real
scoring, no private-lake reads.

Asserts the command produces the REGISTERED count-PMF / evaluation
artifacts (per-start combined count PMFs ``pmf_h3_raw`` / ``pmf_l5_raw``
over 24 buckets, 0..23, tail absorbed at k>=23), not only PA-probability
rows, plus the fail-loud negative guards (missing BF coverage, duplicate
start keys, sha-pin mismatch, invalid distribution, conversion failure).
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

PMF37_COLS = [f"pmf37_{j}" for j in range(37)]
CUTOFF = date(2025, 3, 15)


# --------------------------------------------------------------- fixtures
def synth_pa_table(n_days: int = 40, seed: int = 7,
                   day_offset: int = 0) -> pl.DataFrame:
    """Synthetic PA table: 3 pitchers x 9 batters, one game per day,
    18 PAs per game, y ~ Bernoulli(p_entity)."""
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
                    pitcher: int = 870001) -> pl.DataFrame:
    """One projected start with 9 covered slots (all batters seen in the
    PA table; no cold-start slots)."""
    batters = sorted(pa["batter"].unique().to_list())
    slots = {f"u_slot_{i + 1}": batters[i % len(batters)] for i in range(9)}
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
    """Frozen-recipe checkpoint fit on synthetic training rows (same
    coefficients for all three blocks so block routing is covered)."""
    p_daily = ad.entity_daily_state(pa, "pitcher")
    b_daily = ad.entity_daily_state(pa, "batter")
    lg = ad.league_daily_state(pa)
    rows = pa.select(
        "game_pk", "at_bat_number", "batter", "pitcher", "game_date",
    ).sort("game_date")
    feat = ad.attach_prior_features(rows, p_daily, b_daily, lg)
    feat = feat.join(pa.select("game_pk", "at_bat_number", "batter", "y"),
                     on=["game_pk", "at_bat_number", "batter"], how="inner")
    feat = feat.filter(pl.col("lg_rate").is_finite())
    model = ad.fit_models_from_frames(feat, feat)
    return {"block_2024H2": model, "block_2025H1": model,
            "confirm_2025H2": model}


def synth_bf37(h: float = 0.06) -> np.ndarray:
    """Constant-hazard 37-category BF PMF (index 36 = overflow mass)."""
    pmf37 = np.empty(37)
    surv = 1.0
    for n in range(36):
        pmf37[n] = surv * h
        surv *= 1 - h
    pmf37[36] = surv
    return pmf37


def bf_row(game_pk: int, side: str, pitcher: int, pmf37: np.ndarray,
           game_date=CUTOFF) -> dict:
    return {
        "game_pk": game_pk, "side": side, "pitcher": pitcher,
        "game_date": game_date,
        **{f"pmf37_{j}": float(v) for j, v in enumerate(pmf37)},
    }


def synth_lake(tmp_path: Path, pa: pl.DataFrame, proj: pl.DataFrame,
               bf: pl.DataFrame) -> dict:
    """Write a fully synthetic private-lake stand-in under tmp_path and
    return the directory dict."""
    ps = tmp_path / "pregame-state-v1"
    op2 = tmp_path / "overnight-p2"
    bfw = tmp_path / "bf-workload-v1"
    out = tmp_path / "pregame-pa-ext-v2"
    for d in (ps / "data", op2 / "data", bfw / "data", out / "checkpoints"):
        d.mkdir(parents=True, exist_ok=True)
    proj.write_parquet(ps / "data" / "projected_lineups_variant_v2.parquet")
    pa.write_parquet(op2 / "data" / "pa_table.parquet")
    bf_path = bfw / "data" / "bf_forecasts.parquet"
    bf.write_parquet(bf_path)
    ck = out / "checkpoints" / "h3_raw_checkpoint.json"
    return {
        "pregame_state_dir": ps,
        "overnight_p2_dir": op2,
        "bf_workload_dir": bfw,
        "out_dir": out,
        "bf_path": bf_path,
        "checkpoint_path": ck,
    }


def wire_lake(monkeypatch, dirs: dict, models: dict,
              registered_sha: str) -> None:
    verification = {"block_2025H1": {"n_rows": 10, "max_abs_diff": 0.0}}
    ad.serialize_checkpoint(models, verification, dirs["checkpoint_path"])
    monkeypatch.setattr(ad, "PREGAME_STATE_DIR", dirs["pregame_state_dir"])
    monkeypatch.setattr(ad, "OVERNIGHT_P2_DIR", dirs["overnight_p2_dir"])
    monkeypatch.setattr(ad, "PAEXT_OUT_DIR", dirs["out_dir"])
    monkeypatch.setattr(ad, "BF_WORKLOAD_DIR", dirs["bf_workload_dir"])
    monkeypatch.setattr(ad, "CHECKPOINT_PATH", dirs["checkpoint_path"])
    monkeypatch.setattr(ad, "REGISTERED_BF_FORECASTS_SHA256",
                        registered_sha)


def sha_of(path: Path) -> str:
    return ad.sha256_file(path)


@pytest.fixture(scope="module")
def pa_mod() -> pl.DataFrame:
    return synth_pa_table()


@pytest.fixture(scope="module")
def models_mod(pa_mod) -> dict:
    return synth_models(pa_mod)


# -------------------------------------------------- validator unit tests
def test_validator_attaches_pmfs_and_meta(pa_mod, models_mod):
    proj = synth_projected(pa_mod, CUTOFF)
    long, _ = ad.projected_long(proj)
    p_daily = ad.entity_daily_state(pa_mod, "pitcher")
    b_daily = ad.entity_daily_state(pa_mod, "batter")
    lg = ad.league_daily_state(pa_mod)
    pf = ad.attach_prior_features(long, p_daily, b_daily, lg)
    pf = ad.add_block(pf)
    starts = pf.sort("slot").group_by(
        "game_pk", "side", "pitcher").agg(
        pl.col("game_date").first().alias("game_date"),
        pl.col("p_pitcher_prior_w150").sort_by("slot").alias("p9"),
    )
    bf = pl.DataFrame([bf_row(999001, "Bot", 870001, synth_bf37())])
    j, meta = ad.validate_bf37_by_start(bf, starts)
    assert j.height == starts.height == 1
    assert meta["n_scored_starts"] == 1
    assert meta["n_starts_bf_matched"] == 1
    assert "bf_pmf_from_37" in meta["bf_extension"]
    assert meta["kcount_cap"] == 60
    assert PMF37_COLS[0] in j.columns and PMF37_COLS[-1] in j.columns


def test_validator_rejects_duplicate_start_keys(pa_mod, models_mod):
    proj = synth_projected(pa_mod, CUTOFF)
    starts = proj.select("game_pk", "side", "pitcher", "game_date")
    row = bf_row(999001, "Bot", 870001, synth_bf37())
    bf = pl.DataFrame([row, row])
    with pytest.raises(ad.AdapterError, match="BF_PMF_DUPLICATE_START_KEYS"):
        ad.validate_bf37_by_start(bf, starts)


def test_validator_rejects_duplicate_game_pitcher_grain(pa_mod):
    starts = pl.DataFrame([{
        "game_pk": 999001, "side": "Bot", "pitcher": 870001,
        "game_date": CUTOFF,
    }])
    pmf = synth_bf37()
    # same (game_pk, pitcher) under two sides: violates the registered
    # (game_pk, pitcher) grain even though (game_pk, side, pitcher) is unique
    bf = pl.DataFrame([
        bf_row(999001, "Bot", 870001, pmf),
        bf_row(999001, "Top", 870001, pmf),
    ])
    with pytest.raises(ad.AdapterError, match="BF_PMF_DUPLICATE_START_KEYS"):
        ad.validate_bf37_by_start(bf, starts)


def test_validator_rejects_missing_coverage(pa_mod):
    proj = pl.concat([
        synth_projected(pa_mod, CUTOFF, game_pk=999001),
        synth_projected(pa_mod, CUTOFF, game_pk=999002, pitcher=870002),
    ])
    starts = proj.select("game_pk", "side", "pitcher", "game_date")
    bf = pl.DataFrame([bf_row(999001, "Bot", 870001, synth_bf37())])
    with pytest.raises(ad.AdapterError, match="BF_PMF_COVERAGE_MISSING"):
        ad.validate_bf37_by_start(bf, starts)


def test_validator_rejects_nonnormalized_pmf(pa_mod):
    starts = pl.DataFrame([{
        "game_pk": 999001, "side": "Bot", "pitcher": 870001,
        "game_date": CUTOFF,
    }])
    bad = synth_bf37() * 0.5
    bf = pl.DataFrame([bf_row(999001, "Bot", 870001, bad)])
    with pytest.raises(ad.AdapterError, match="BF_PMF_DISTRIBUTION_INVALID"):
        ad.validate_bf37_by_start(bf, starts)


def test_validator_rejects_conversion_failure(pa_mod):
    """A pmf37 the registered conversion cannot extend (mass only at BF=1
    and the overflow bucket leaves the geometric tail with zero hazard)
    fails loud as BF_PMF_CONVERSION_FAILED."""
    starts = pl.DataFrame([{
        "game_pk": 999001, "side": "Bot", "pitcher": 870001,
        "game_date": CUTOFF,
    }])
    pmf = np.zeros(37)
    pmf[0] = 0.5
    pmf[36] = 0.5
    bf = pl.DataFrame([bf_row(999001, "Bot", 870001, pmf)])
    with pytest.raises(ad.AdapterError, match="BF_PMF_CONVERSION_FAILED"):
        ad.validate_bf37_by_start(bf, starts)


def test_validator_rejects_date_mismatch(pa_mod):
    starts = pl.DataFrame([{
        "game_pk": 999001, "side": "Bot", "pitcher": 870001,
        "game_date": CUTOFF,
    }])
    bf = pl.DataFrame([bf_row(999001, "Bot", 870001, synth_bf37(),
                              game_date=date(2025, 3, 14))])
    with pytest.raises(ad.AdapterError, match="BF_PMF_DATE_MISMATCH"):
        ad.validate_bf37_by_start(bf, starts)


def test_load_bf_forecasts_missing_artifact(tmp_path):
    with pytest.raises(ad.AdapterError, match="BF_PMF_ARTIFACT_MISSING"):
        ad.load_bf_forecasts(tmp_path)


def test_load_bf_forecasts_sha_pin(tmp_path, monkeypatch):
    d = tmp_path / "bf-workload-v1"
    (d / "data").mkdir(parents=True)
    bf = pl.DataFrame([bf_row(1, "Bot", 2, synth_bf37())])
    bf.write_parquet(d / "data" / "bf_forecasts.parquet")
    # a pin that does not match the file bytes fails loud
    monkeypatch.setattr(ad, "REGISTERED_BF_FORECASTS_SHA256", "f" * 64)
    with pytest.raises(ad.AdapterError, match="BF_PMF_SHA_MISMATCH"):
        ad.load_bf_forecasts(d)
    # the matching pin loads and records provenance
    monkeypatch.setattr(ad, "REGISTERED_BF_FORECASTS_SHA256",
                        sha_of(d / "data" / "bf_forecasts.parquet"))
    loaded, meta = ad.load_bf_forecasts(d)
    assert loaded.height == 1
    assert meta["sha256"] == meta["registered_sha256"]
    assert "bf-workload-v1/data/bf_forecasts.parquet" in meta["artifact"]


# -------------------------------------------------- end-to-end via run_real
def _two_start_e2e_setup(tmp_path, monkeypatch, pa, models,
                         bf=None, drop_second_bf_row=False):
    proj = pl.concat([
        synth_projected(pa, CUTOFF, game_pk=999001, pitcher=870001),
        synth_projected(pa, CUTOFF, game_pk=999002, pitcher=870002),
    ])
    if bf is None:
        bf = pl.DataFrame([
            bf_row(999001, "Bot", 870001, synth_bf37(0.06)),
            bf_row(999002, "Bot", 870002, synth_bf37(0.08)),
        ])
    if drop_second_bf_row:
        bf = bf.filter(pl.col("game_pk") == 999001)
    dirs = synth_lake(tmp_path, pa, proj, bf)
    wire_lake(monkeypatch, dirs, models, sha_of(dirs["bf_path"]))
    return dirs


def test_run_real_produces_registered_count_pmf_artifacts(
        tmp_path, monkeypatch, pa_mod, models_mod):
    """Through the actual execution entry point: run_real() on synthetic
    lake inputs produces the write-once output carrying the REGISTERED
    count-PMF / evaluation artifacts (24-bucket combined count PMFs per
    start for both RAW arms + mean-K), not only PA-probability rows."""
    dirs = _two_start_e2e_setup(tmp_path, monkeypatch, pa_mod, models_mod)
    summary = ad.run_real()
    # provenance: input sha256 + source identity, wired end to end
    assert summary["bf37_artifact"]["sha256"] == sha_of(dirs["bf_path"])
    assert summary["bf37_artifact"]["registered_sha256"] == \
        summary["bf37_artifact"]["sha256"]
    assert summary["bf37_artifact"]["artifact"] == \
        "bf-workload-v1/data/bf_forecasts.parquet"
    assert summary["bf37"]["n_scored_starts"] == 2
    assert summary["bf37"]["n_starts_bf_matched"] == 2
    assert summary["n_starts_pmf_computed"] == 2
    assert summary["n_starts_pmf_excluded_cold_slot"] == 0
    # registered artifacts present in the written output
    out = Path(summary["output"])
    assert out.exists()
    df = pl.read_parquet(out)
    for col in ("pmf_h3_raw", "pmf_l5_raw", "mean_k_h3_raw",
                "mean_k_l5_raw"):
        assert col in df.columns, col
    assert df.height == 18  # 2 starts x 9 slots
    scored = df.filter(pl.col("exclusion_reason").is_null())
    assert scored.height == df.height
    per_start = scored.group_by("game_pk", "side", "pitcher").agg(
        n=pl.len())
    assert (per_start["n"] == 9).all()
    for tag in ("h3_raw", "l5_raw"):
        for pmf in scored[f"pmf_{tag}"]:
            arr = np.asarray(pmf, dtype=np.float64)
            assert arr.shape == (24,)
            assert abs(arr.sum() - 1.0) <= 1e-9
            assert (arr >= 0).all()
        assert np.isfinite(scored[f"mean_k_{tag}"].to_numpy()).all()
    # the two starts carry DIFFERENT combined count PMFs (per-start
    # combination, not a shared/global distribution)
    a = np.asarray(scored.filter(pl.col("game_pk") == 999001)[
        "pmf_h3_raw"][0])
    b = np.asarray(scored.filter(pl.col("game_pk") == 999002)[
        "pmf_h3_raw"][0])
    assert not np.allclose(a, b)
    # combined count PMFs reproduce the registered conversion + mixture
    # for one start from its stored inputs
    row = scored.filter(pl.col("game_pk") == 999001).sort("slot")
    arms = ad.start_count_pmfs(
        np.asarray(row["p_h3_raw"].to_numpy()),
        np.asarray(row["p_l5_raw"].to_numpy()),
        synth_bf37(0.06))
    assert np.allclose(a, arms["pmf_h3_raw"], atol=1e-12)


def test_run_real_fails_loud_on_missing_bf_coverage(
        tmp_path, monkeypatch, pa_mod, models_mod):
    """A projected start without a BF PMF row stops the run: no invented
    replacement distribution."""
    dirs = _two_start_e2e_setup(tmp_path, monkeypatch, pa_mod, models_mod,
                                drop_second_bf_row=True)
    with pytest.raises(ad.AdapterError, match="BF_PMF_COVERAGE_MISSING"):
        ad.run_real()


def test_run_real_fails_loud_on_duplicate_start_keys(
        tmp_path, monkeypatch, pa_mod, models_mod):
    proj = pl.concat([
        synth_projected(pa_mod, CUTOFF, game_pk=999001, pitcher=870001),
        synth_projected(pa_mod, CUTOFF, game_pk=999002, pitcher=870002),
    ])
    row = bf_row(999001, "Bot", 870001, synth_bf37())
    bf = pl.DataFrame([row, row,
                       bf_row(999002, "Bot", 870002, synth_bf37(0.08))])
    dirs = synth_lake(tmp_path, pa_mod, proj, bf)
    wire_lake(monkeypatch, dirs, models_mod, sha_of(dirs["bf_path"]))
    with pytest.raises(ad.AdapterError, match="BF_PMF_DUPLICATE_START_KEYS"):
        ad.run_real()


def test_run_real_fails_loud_on_sha_mismatch(
        tmp_path, monkeypatch, pa_mod, models_mod):
    dirs = _two_start_e2e_setup(tmp_path, monkeypatch, pa_mod, models_mod)
    # pin a DIFFERENT artifact than the one on disk
    monkeypatch.setattr(ad, "REGISTERED_BF_FORECASTS_SHA256", "a" * 64)
    with pytest.raises(ad.AdapterError, match="BF_PMF_SHA_MISMATCH"):
        ad.run_real()


def test_run_real_fails_loud_on_missing_checkpoint(
        tmp_path, monkeypatch, pa_mod, models_mod):
    dirs = _two_start_e2e_setup(tmp_path, monkeypatch, pa_mod, models_mod)
    monkeypatch.setattr(ad, "CHECKPOINT_PATH",
                        dirs["out_dir"] / "checkpoints" / "absent.json")
    with pytest.raises(ad.AdapterError, match="MISSING_CHECKPOINT_ARTIFACT"):
        ad.run_real()
