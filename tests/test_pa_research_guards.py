"""Phase 7.5: eight permanent regression guards (positive + negative fixtures).

Each guard maps to a historical failure mode. Run only this file:
  python -m pytest tests/test_pa_research_guards.py -q
"""
import sys
from pathlib import Path
import numpy as np
import polars as pl
import pytest

from conftest import artifact_path  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research/offseason_2026"))
from contracts.pa_contracts import (  # noqa: E402
    assert_single_season, assert_unique_keys, align_predictions,
    aggregate_oracle_xk, assert_temporal_boundary, population_reconcile,
    predict_pa_probabilities)

# ---------- fixtures ----------
def pa_frame(seasons=(2024,), n=5):
    return pl.DataFrame({
        "game_pk": [1] * n, "at_bat_number": list(range(1, n + 1)), "pitcher": [100] * n,
        "season": list(seasons) * (n // len(seasons)) + list(seasons)[: n % len(seasons)],
        "game_date": ["2024-05-01"] * n, "batter": list(range(200, 200 + n)),
        "f1": [0.1] * n, "f2": [0.2] * n})


# G1 season isolation (historical: Phase 7 mixed-season frame)
def test_g1_season_isolation_pass_and_fail():
    assert_single_season(pa_frame((2024,)), 2024)
    with pytest.raises(ValueError, match="SEASON_ISOLATION_VIOLATION"):
        assert_single_season(pa_frame((2023, 2024)), 2024)


# G2 join key/order preservation (historical: Phase 7 join reorder misalignment)
def test_g2_join_alignment_pass_and_fail():
    pf = pa_frame()
    preds = pl.DataFrame({
        "game_pk": [1] * 5, "at_bat_number": [5, 3, 1, 4, 2], "pitcher": [100] * 5,
        "p_k": [0.1, 0.2, 0.3, 0.4, 0.5]})
    out = align_predictions(pf, preds, ["p_k"])
    assert out["p_k"].to_list() == [0.3, 0.5, 0.2, 0.4, 0.1]  # key-mapped (abn1->0.3, abn2->0.5, ...), order preserved
    dup = pl.concat([preds, preds.head(1)])
    with pytest.raises(ValueError, match="DUPLICATE_KEY_VIOLATION"):
        align_predictions(pf, dup, ["p_k"])
    missing = preds.head(4)
    with pytest.raises(ValueError, match="MISSING_PREDICTION_KEYS"):
        align_predictions(pf, missing, ["p_k"])
    extra = pl.concat([preds, pl.DataFrame({"game_pk": [2], "at_bat_number": [1],
                                            "pitcher": [100], "p_k": [0.9]})])
    with pytest.raises(ValueError, match="EXTRA_PREDICTION_KEYS"):
        align_predictions(pf, extra, ["p_k"])


# G3 independent aggregation checksum (independent reference implementation)
def test_g3_aggregation_checksum():
    df = pl.DataFrame({
        "game_pk": [1, 1, 1, 2, 2], "at_bat_number": [1, 2, 3, 1, 2],
        "pitcher": [7, 7, 7, 8, 8], "game_date": ["2024-05-01"] * 5,
        "p_k": [0.2, 0.3, 0.4, 0.5, 0.1]})
    manifest = {"official_bf": {(1, 7): 3, (2, 8): 2}}
    agg = aggregate_oracle_xk(df, manifest)
    # independent reference: plain dict loop
    ref = {}
    for gp, abn, p, pit in zip(df["game_pk"], df["at_bat_number"], df["p_k"], df["pitcher"]):
        ref.setdefault((gp, pit), 0.0)
        ref[(gp, pit)] += p
    for r in agg.iter_rows(named=True):
        assert abs(r["oracle_xK"] - ref[(r["game_pk"], r["pitcher"])]) < 1e-12
    with pytest.raises(NotImplementedError, match="POISSON_BINOMIAL"):
        aggregate_oracle_xk(df, manifest, mode="POISSON_BINOMIAL")


# G4 population reconciliation (historical: funnel/manifest mismatches)
def test_g4_population_reconcile_pass_and_fail():
    population_reconcile({"e1": 55815, "e2": 50252}, {"e1": 55815, "e2": 50252})
    with pytest.raises(ValueError, match="POPULATION_MISMATCH"):
        population_reconcile({"e1": 55814, "e2": 50252}, {"e1": 55815, "e2": 50252})


# G5 P3 reproduction (registered tolerance vs stored baseline)
def test_g5_p3_reproduction_against_canonical_counts():
    pa = pl.read_parquet(REPO / "research/offseason_2026/datasets/pa_table_2023_2024.parquet")
    d24 = pa.filter(pl.col("season") == 2024)
    pg = pl.read_parquet(artifact_path("data/processed/pitcher_games.parquet"))
    prior23 = pg.filter(pl.col("season") == 2023).group_by("pitcher").agg(
        pl.col("K").sum().alias("K_prior"), pl.col("PA").sum().alias("PA_prior"))
    pg24 = pg.filter(pl.col("season") == 2024).sort(["pitcher", "game_date", "game_pk"]).with_columns(
        (pl.col("K").cum_sum().over(["pitcher"]) - pl.col("K")).alias("K_curr"),
        (pl.col("PA").cum_sum().over(["pitcher"]) - pl.col("PA")).alias("PA_curr"))
    pg24 = pg24.with_columns(pl.col(["K_curr", "PA_curr"]).first().over(["pitcher", "game_date"]))
    d = d24.join(prior23, on="pitcher", how="left").join(
        pg24.select(["game_pk", "pitcher", "K_curr", "PA_curr"]), on=["game_pk", "pitcher"], how="left")
    LG, EPS = 0.223813, 1e-6
    clip = lambda a: np.clip(a, EPS, 1 - EPS)
    odds = lambda a: (lambda c: c / (1 - c))(clip(a))
    Kp = d["K_prior"].fill_null(0).to_numpy(); Np = d["PA_prior"].fill_null(0).to_numpy()
    Kc = d["K_curr"].fill_null(0).to_numpy(); Nc = d["PA_curr"].fill_null(0).to_numpy()
    p_p3 = np.where(Np + Nc > 0, (Kp + Kc + 100 * LG) / (Np + Nc + 100), LG)
    pb = clip(d["b_k_rate_std_shrunk"].to_numpy())
    om = odds(p_p3) * odds(pb) / odds(LG)
    p_l5 = clip(om / (1 + om))
    stored = pl.read_parquet(REPO / "research/offseason_2026/experiments/pitcher_prior/pa_predictions.parquet")
    # duplicate column names exist in this artifact; pull P3_l5 positionally via row-order-safe select
    p3col = [c for c in stored.columns if c == "P3_l5"]
    stored_cols = stored.select([pl.nth(i) for i, c in enumerate(stored.columns) if c == "P3_l5"]).to_series()
    j = d.select(["game_pk", "at_bat_number"]).with_columns(
        pl.Series("recomputed", p_l5)).join(
        stored.select(["game_pk", "at_bat_number"]).with_columns(
            pl.Series("stored", stored_cols)), on=["game_pk", "at_bat_number"], how="inner")
    assert j.height == d.height
    assert float((j["recomputed"] - j["stored"]).abs().max()) < 1e-9


# G6 identical-arm keys (compare keys+labels, not row counts)
def test_g6_identical_arm_keys():
    a = pa_frame(); b = pa_frame()
    assert a.select(["game_pk", "at_bat_number"]).equals(b.select(["game_pk", "at_bat_number"]))
    b_minus = b.head(4)
    with pytest.raises(AssertionError):
        assert a.select(["game_pk", "at_bat_number"]).equals(b_minus.select(["game_pk", "at_bat_number"]))


# G7 temporal boundaries (historical: same-game information entering features)
def test_g7_temporal_boundary_pass_and_fail():
    import datetime as dt
    ts = [dt.datetime(2024, 4, 30, 23, 0)] * 3
    assert_temporal_boundary(ts, dt.datetime(2024, 5, 1, 8, 0), "unit")
    bad = ts + [dt.datetime(2024, 5, 1, 9, 0)]
    with pytest.raises(ValueError, match="TEMPORAL_BOUNDARY_VIOLATION"):
        assert_temporal_boundary(bad, dt.datetime(2024, 5, 1, 8, 0), "unit")


# G8 duplicate-key rejection
def test_g8_duplicate_key_rejection():
    df = pl.concat([pa_frame(), pa_frame().head(1)])
    with pytest.raises(ValueError, match="DUPLICATE_KEY_VIOLATION"):
        assert_unique_keys(df, ["game_pk", "at_bat_number", "pitcher"])
    assert_unique_keys(pa_frame(), ["game_pk", "at_bat_number", "pitcher"])


# contract: predict_pa_probabilities end-to-end on a synthetic bundle
def test_contract_predict_roundtrip():
    bundle = {
        "model_id": "L3_dev", "model_version": "phase7", "intercept": -1.0,
        "coefficients": {"__BASELINE_LOGIT__": 0.9, "f1": 0.1, "f2": -0.2},
        "baseline_column": "logit_p3",
        "feature_manifest": {"feature_order": ["f1", "f2"], "allow_extra_columns": True},
        "feature_manifest_hash": "test",
        "preprocessing": {"f1": {"mean": 0.0, "std": 1.0, "fill": 0.0},
                           "f2": {"mean": 0.0, "std": 1.0, "fill": 0.0}},
    }
    df = pa_frame().with_columns(pl.Series("logit_p3", [-1.0] * 5))
    out = predict_pa_probabilities(df, bundle)
    assert out["p_k"].null_count() == 0
    assert out.height == 5
    bad = df.drop("f1")
    with pytest.raises(ValueError, match="FEATURE_SCHEMA_VIOLATION"):
        predict_pa_probabilities(bad, bundle)
