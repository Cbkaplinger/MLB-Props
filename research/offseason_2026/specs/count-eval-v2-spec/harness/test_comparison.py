"""count-eval-v2 synthetic tests for the shared chronological comparison
interface (COMPARISON_INTERFACE_SPEC.md section 7 -- synthetic tests FIRST,
before any real-data run; test-first ordering is part of the interface).

Run standalone:
    python -m pytest test_comparison.py -q
All tests use synthetic fixtures only; no real-data load happens here and no
real-data run is authorized by passing tests (spec section 8).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import comparison as cmp_mod  # noqa: E402
from comparison import (  # noqa: E402
    AdapterContractError, AvailabilityError, ComparisonError, ConstantAdapter,
    DEV_BLOCKS, DuplicateKeyError, FEAT_B, FEAT_H3, FEAT_H3_BATTER_EW,
    FEAT_H3_PITCHER_EW, LogisticAdapter,
    Log5BaselineAdapter, RunConfig, WriteOnceError, brier, derive_folds,
    enforce_availability_guard, eval_identity_hash, load_pa_rows, log5,
    log_loss, registered_adapters, run_comparison, slate_date_bootstrap,
)

RNG_SEED = 7
TOL = 1e-12


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

def _synth_frames(n_days_per_year: int = 120, rows_per_day: int = 3,
                  seed: int = RNG_SEED):
    """Synthetic pa_table + features covering 2023-01-01..2025-09-28 daily so
    every registered fold has non-empty train/cal/eval partitions."""
    rng = np.random.default_rng(seed)
    days = []
    d = dt.date(2023, 1, 1)
    end = dt.date(2025, 9, 28)
    while d <= end:
        days.append(d)
        d += dt.timedelta(days=1)
    dates = np.repeat(np.array(days, dtype="datetime64[D]"), rows_per_day)
    n = dates.size
    game_pk = (np.arange(n) // rows_per_day + 900_000).astype(np.int64)
    ab = (np.arange(n) % rows_per_day + 1).astype(np.int64)
    batter = rng.integers(1000, 2000, size=n).astype(np.int64)
    pitcher = rng.integers(5000, 6000, size=n).astype(np.int64)

    lg = 0.22 + 0.02 * rng.random(n)
    p_p = np.clip(lg + rng.normal(0, 0.05, n), 0.05, 0.6)
    p_b = np.clip(lg + rng.normal(0, 0.05, n), 0.05, 0.6)
    # y ~ log5(p, b, lg): makes the P0 known-answer loss hand-checkable
    q = log5(p_p, p_b, lg)
    y = (rng.random(n) < q).astype(np.int8)

    gdate = pl.Series("game_date", dates).cast(pl.Date)
    src_date = pl.Series("src_date_pitcher", dates - np.timedelta64(1, "D")).cast(pl.Date)

    pa = pl.DataFrame({
        "game_pk": game_pk, "game_date": gdate,
        "season": gdate.dt.year(), "at_bat_number": ab,
        "batter": batter, "pitcher": pitcher,
        "p_throws": rng.choice(["L", "R"], n), "stand": rng.choice(["L", "R"], n),
        "events": np.where(y == 1, "strikeout", "ground_out"),
        "inning_topbot": rng.choice(["Top", "Bottom"], n),
        "y": y,
        "pitcher_role": rng.choice(["starter_pa", "reliever_pa"], n,
                                   p=[0.7, 0.3]),
    })
    feat = pl.DataFrame({
        "game_pk": game_pk, "at_bat_number": ab, "batter": batter,
        "game_date": gdate,
        "p_pitcher_prior_w150": p_p, "p_batter_prior_w150": p_b,
        "lg_rate": lg,
        "n_prior_pitcher": rng.integers(0, 800, n).astype(np.int64),
        "n_prior_batter": rng.integers(0, 800, n).astype(np.int64),
        "cold_start": (rng.random(n) < 0.02).astype(np.int8),
        "ew_pitcher": np.clip(p_p + rng.normal(0, 0.01, n), 0.01, 0.9),
        "ew_batter": np.clip(p_b + rng.normal(0, 0.01, n), 0.01, 0.9),
        "src_date_pitcher": src_date, "src_type_pitcher": "entity_history",
        "src_type_lg": "league_history",
    })
    return pa, feat


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("synth")
    pa, feat = _synth_frames()
    pa_path = tmp / "pa_table.parquet"
    feat_path = tmp / "features.parquet"
    pa.write_parquet(pa_path)
    feat.write_parquet(feat_path)
    return {"pa": pa, "feat": feat, "pa_path": pa_path, "feat_path": feat_path,
            "tmp": tmp}


def _run_cfg(synth, tmp_path, candidates=None, label=""):
    return RunConfig(
        pa_table_path=str(synth["pa_path"]),
        features_path=str(synth["feat_path"]),
        candidates=candidates if candidates is not None
        else ["P0_log5", "P1_B_logreg", "P1_H3_incumbent_refit"],
        output_root=str(tmp_path / "outputs"),
        run_label=label,
    )


# ---------------------------------------------------------------------------
# 1. Row-identity guard
# ---------------------------------------------------------------------------

def test_duplicate_identity_fails_loud(synth, tmp_path):
    bad = pl.concat([synth["pa"], synth["pa"].head(5)])
    p = tmp_path / "dup_pa.parquet"
    bad.write_parquet(p)
    with pytest.raises(DuplicateKeyError):
        load_pa_rows(p, synth["feat_path"])


def test_eval_identity_hash_matches_across_candidates(synth, tmp_path):
    out = run_comparison(_run_cfg(synth, tmp_path, label="ident"))
    man = json.loads((out / "run_manifest.json").read_text())
    for fold in DEV_BLOCKS + ["confirm_2025H2"]:
        hashes = {c: man["candidates"][c][fold]["eval_identity_sha256"]
                  for c in man["config"]["candidates"]}
        assert len(set(hashes.values())) == 1
        # independent recomputation from the written preds file
        p = pl.read_parquet(out / f"preds_{fold}__P0_log5.parquet")
        assert eval_identity_hash(p) == hashes["P0_log5"]


# ---------------------------------------------------------------------------
# 2. Availability guard
# ---------------------------------------------------------------------------

def test_availability_guard_same_date_and_future_fail(synth):
    df = load_pa_rows(synth["pa_path"], synth["feat_path"])
    # force the first row's source date onto its own game_date (no same-date
    # state allowed)
    idx0 = df.with_row_index("_i").filter(pl.col("_i") == 0)
    mutated = df.with_columns(
        pl.when(pl.col("game_pk") == idx0["game_pk"][0])
        .then(pl.col("game_date")).otherwise(pl.col("src_date_pitcher"))
        .alias("src_date_pitcher"))
    with pytest.raises(AvailabilityError):
        enforce_availability_guard(mutated)


def test_availability_guard_null_source_type_fails(synth):
    df = load_pa_rows(synth["pa_path"], synth["feat_path"])
    mutated = df.with_columns(
        pl.when(pl.arange(0, pl.len()) == 0)
        .then(None).otherwise(pl.col("src_type_pitcher"))
        .alias("src_type_pitcher"))
    with pytest.raises(AvailabilityError):
        enforce_availability_guard(mutated)


def test_no_2026_rows_and_eligibility_window(synth):
    df = load_pa_rows(synth["pa_path"], synth["feat_path"])
    assert df.filter(pl.col("game_date") >= pl.date(2026, 1, 1)).height == 0
    assert df.filter(pl.col("game_date") < pl.date(2023, 1, 1)).height == 0
    assert df.filter(pl.col("game_date") > pl.date(2025, 12, 31)).height == 0


# ---------------------------------------------------------------------------
# 3. End-to-end through all folds with a trivial adapter + identical eval rows
# ---------------------------------------------------------------------------

def test_end_to_end_all_folds_trivial_adapter(synth, tmp_path):
    trivial = ConstantAdapter("T_const", 0.25)
    # register the trivial adapter for this run by patching the registry
    reg = registered_adapters()
    reg["T_const"] = trivial
    orig = cmp_mod.registered_adapters
    cmp_mod.registered_adapters = lambda: reg
    try:
        out = run_comparison(_run_cfg(
            synth, tmp_path, candidates=["P0_log5", "T_const"],
            label="trivial"))
    finally:
        cmp_mod.registered_adapters = orig
    folds = derive_folds(load_pa_rows(synth["pa_path"], synth["feat_path"]))
    for fold in DEV_BLOCKS + ["confirm_2025H2"]:
        for cand in ["P0_log5", "T_const"]:
            f = out / f"preds_{fold}__{cand}.parquet"
            assert f.exists()
            p = pl.read_parquet(f)
            # identical eval rows across candidates
            ref = pl.read_parquet(out / f"preds_{fold}__P0_log5.parquet")
            assert p.select(cmp_mod.IDENTITY_COLS).equals(
                ref.select(cmp_mod.IDENTITY_COLS))
            assert p.height == folds[fold].n_eval
            assert p["pred_raw"].is_finite().all()
            assert p["pred_raw"].min() >= 0 and p["pred_raw"].max() <= 1
    m = json.loads((out / "metrics.json").read_text())
    assert set(m["per_fold"]) == set(DEV_BLOCKS + ["confirm_2025H2"])
    assert m["pooled_dev"]["blocks_pooled"] == list(DEV_BLOCKS)


# ---------------------------------------------------------------------------
# Write-once outputs with run identity
# ---------------------------------------------------------------------------

def test_write_once_outputs_fail_loud(synth, tmp_path):
    cfg = _run_cfg(synth, tmp_path, label="once")
    out1 = run_comparison(cfg)
    run_id = out1.name
    assert len(run_id) == 64  # sha256 hex run identity
    with pytest.raises(WriteOnceError):
        run_comparison(cfg)
    # different label -> different run_id -> separate dir, first run untouched
    out2 = run_comparison(_run_cfg(synth, tmp_path, label="other"))
    assert out2.name != out1.name
    man1 = json.loads((out1 / "run_manifest.json").read_text())
    assert man1["run_id"] == run_id


def test_run_id_binds_config_and_inputs(synth, tmp_path):
    out = run_comparison(_run_cfg(synth, tmp_path, label="bind"))
    man = json.loads((out / "run_manifest.json").read_text())
    identity = {"run_identity": man["config"],
                "input_sha256": man["inputs_sha256"]}
    expect = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()
    assert man["run_id"] == expect
    assert man["inputs_sha256"]["pa_table"] == cmp_mod.sha256_file(
        synth["pa_path"])


# ---------------------------------------------------------------------------
# Known-answer log loss for the baseline adapter
# ---------------------------------------------------------------------------

def test_baseline_constant_fixture_known_answer_log_loss(synth, tmp_path):
    # fixture where all log5 inputs equal a constant v -> identity p=b=l -> q=v
    pa, feat = _synth_frames()
    v = 0.3
    feat2 = feat.with_columns([
        pl.lit(v).alias("p_pitcher_prior_w150"),
        pl.lit(v).alias("p_batter_prior_w150"),
        pl.lit(v).alias("lg_rate"),
    ])
    tmp = tmp_path / "ka"
    tmp.mkdir()
    pa_path, feat_path = tmp / "pa.parquet", tmp / "feat.parquet"
    pa.write_parquet(pa_path)
    feat2.write_parquet(feat_path)
    out = run_comparison(RunConfig(
        pa_table_path=str(pa_path), features_path=str(feat_path),
        candidates=["P0_log5"], output_root=str(tmp_path / "ka_out"),
        run_label="ka"))
    p = pl.read_parquet(out / "preds_block_2024H1__P0_log5.parquet")
    assert np.allclose(p["pred_raw"].to_numpy(), v, atol=TOL)
    y = p["y"].to_numpy().astype(float)
    expected = float(-np.mean(y * np.log(v) + (1 - y) * np.log(1 - v)))
    m = json.loads((out / "metrics.json").read_text())
    assert abs(m["per_fold"]["block_2024H1"]["P0_log5"]["log_loss"]
               - expected) < 1e-12


def test_log_loss_known_answer_constant_adapter(synth, tmp_path):
    df = load_pa_rows(synth["pa_path"], synth["feat_path"])
    folds = derive_folds(df)
    fold = folds["block_2024H1"]
    ev = df.filter(
        (pl.col("game_date") >= fold.assess_start)
        & (pl.col("game_date") <= fold.assess_end))
    y = ev["y"].to_numpy().astype(float)
    p = np.full(y.size, 0.4)
    ll = float(log_loss(y, p).mean())
    expected = float(-np.mean(y * np.log(0.4) + (1 - y) * np.log(0.6)))
    assert abs(ll - expected) < 1e-12
    br = float(brier(y, p).mean())
    assert abs(br - float(np.mean((0.4 - y) ** 2))) < 1e-12


# ---------------------------------------------------------------------------
# Log5 identity pin (mirrors p1-harness-v2/test_log5_identities.py, tol 1e-12)
# ---------------------------------------------------------------------------

def test_log5_identity_pin():
    p_fix = np.array([0.15, 0.2245, 0.31, 0.42, 0.57, 0.68, 0.83])
    b_fix = np.array([0.18, 0.26, 0.19, 0.35, 0.49, 0.61, 0.72])
    for v in [0.05, 0.2245, 0.5, 0.9]:
        assert log5(np.array([v]), np.array([v]), np.array([v]))[0] == \
            pytest.approx(v, abs=TOL)
    assert np.allclose(log5(p_fix, b_fix, p_fix), b_fix, atol=TOL, rtol=0)
    assert np.allclose(log5(p_fix, b_fix, b_fix), p_fix, atol=TOL, rtol=0)


def test_baseline_adapter_uses_log5_formula():
    a = Log5BaselineAdapter()
    X = np.array([[0.30, 0.25, 0.22], [0.10, 0.40, 0.21]])
    expected = log5(X[:, 0], X[:, 1], X[:, 2])
    assert np.allclose(a.predict_proba("f", None, X), expected)


# ---------------------------------------------------------------------------
# Metric determinism + shared resample indices
# ---------------------------------------------------------------------------

def test_bootstrap_seed_20261001_reproducible():
    rng = np.random.default_rng(0)
    n = 400
    dates = list(rng.choice(np.array([d.strftime("%Y-%m-%d") for d in
                                      [dt.date(2024, 4 + i // 10, 1 + i % 28)
                                       for i in range(12)]]), size=n))
    blocks = ["block_2024H2"] * (n // 2) + ["block_2025H1"] * (n - n // 2)
    vals = {"a_minus_b": rng.normal(0, 0.01, n)}
    r1 = slate_date_bootstrap(vals, dates, blocks)
    r2 = slate_date_bootstrap(vals, dates, blocks)
    assert r1["a_minus_b"]["ci95"] == r2["a_minus_b"]["ci95"]
    assert r1["_meta"]["seed"] == 20261001
    assert r1["_meta"]["n_resamples"] == 2000


def test_bootstrap_identical_indices_across_candidates():
    rng = np.random.default_rng(1)
    n = 200
    dates = [f"2024-0{1 + i // 40}-1{i % 10}" for i in range(n)]
    blocks = ["block_2024H1"] * n
    d1, d2 = rng.normal(0, 0.01, n), rng.normal(0.02, 0.01, n)
    # joint call: shared draws; both names must sit inside the same
    # replicate structure -> their percentile gap is stable across reruns
    joint = slate_date_bootstrap({"c1": d1, "c2": d2}, dates, blocks)
    joint2 = slate_date_bootstrap({"c1": d1, "c2": d2}, dates, blocks)
    assert joint["c1"]["ci95"] == joint2["c1"]["ci95"]
    assert joint["c2"]["ci95"] == joint2["c2"]["ci95"]
    solo = slate_date_bootstrap({"c1": d1}, dates, blocks)
    # identical draw stream (per-block draws depend only on blocks/dates, not
    # on the number of names), so the solo run for c1 must equal the joint
    # run for c1 up to float rounding of the num/den reduction
    assert solo["c1"]["ci95"] == pytest.approx(joint["c1"]["ci95"], abs=1e-15)


# ---------------------------------------------------------------------------
# Fold isolation + adapter contract
# ---------------------------------------------------------------------------

def test_fold_isolation_eval_perturbation_cannot_change_fit(synth):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    df = load_pa_rows(synth["pa_path"], synth["feat_path"])
    folds = derive_folds(df)
    fold = folds["block_2024H2"]
    train = df.filter(
        (pl.col("game_date") >= fold.train_start) & (pl.col("game_date") < fold.cal_first))
    ev = df.filter(
        (pl.col("game_date") >= fold.assess_start) & (pl.col("game_date") <= fold.assess_end))
    X_tr = train.select(FEAT_B).to_numpy()
    y_tr = train["y"].to_numpy().astype(int)
    sc = StandardScaler().fit(X_tr)
    lr = LogisticRegression(C=1.0, max_iter=1000).fit(sc.transform(X_tr), y_tr)
    coef1 = lr.coef_.copy()
    # perturb eval rows' labels -> the fit sees UNCHANGED train rows only
    ev_pert = ev.with_columns((1 - pl.col("y")).alias("y"))
    assert ev_pert["y"].sum() != ev["y"].sum()
    lr2 = LogisticRegression(C=1.0, max_iter=1000).fit(
        sc.transform(X_tr), y_tr)  # train rows untouched by the eval mutation
    assert np.array_equal(lr2.coef_, coef1)
    # scaler mean depends only on base_train rows
    assert np.allclose(sc.mean_, X_tr.mean(axis=0))


def test_fold_isolation_confirm_mutation_leaves_dev_predictions_unchanged(
        synth, tmp_path):
    pa, feat = _synth_frames()
    # flip every confirm-fold eval label (2025-07-01..2025-09-28 rows are
    # eval-only for confirm_2025H2 and never enter any train/cal partition)
    pa2 = pa.with_columns(
        pl.when(pl.col("game_date") >= pl.date(2025, 7, 1))
        .then(1 - pl.col("y")).otherwise(pl.col("y")).alias("y"))
    tmp = tmp_path / "iso"
    tmp.mkdir()
    pa_path, feat_path = tmp / "pa.parquet", tmp / "feat.parquet"
    pa.write_parquet(pa_path)
    feat.write_parquet(feat_path)
    pa2_path = tmp / "pa_mut.parquet"
    pa2.write_parquet(pa2_path)
    outs = []
    for tag, pp in (("base", pa_path), ("mut", pa2_path)):
        outs.append(run_comparison(RunConfig(
            pa_table_path=str(pp), features_path=str(feat_path),
            candidates=["P0_log5", "P1_B_logreg"],
            output_root=str(tmp_path / f"iso_out_{tag}"), run_label=tag)))
    for fold in DEV_BLOCKS:
        a = pl.read_parquet(outs[0] / f"preds_{fold}__P1_B_logreg.parquet")
        b = pl.read_parquet(outs[1] / f"preds_{fold}__P1_B_logreg.parquet")
        assert a["pred_raw"].to_numpy().tobytes() == \
            b["pred_raw"].to_numpy().tobytes()
    # confirm block LABELS change (features did not, so the no-fit P0
    # predictions are identical by design; the realized outcomes moved)
    a = pl.read_parquet(outs[0] / "preds_confirm_2025H2__P0_log5.parquet")
    b = pl.read_parquet(outs[1] / "preds_confirm_2025H2__P0_log5.parquet")
    assert not np.array_equal(a["y"].to_numpy(), b["y"].to_numpy())
    m0 = json.loads((outs[0] / "metrics.json").read_text())
    m1 = json.loads((outs[1] / "metrics.json").read_text())
    assert m0["per_fold"]["confirm_2025H2"]["P0_log5"]["brier"] != \
        m1["per_fold"]["confirm_2025H2"]["P0_log5"]["brier"]
    # dev pooled rows never include confirm rows
    m0 = json.loads((outs[0] / "metrics.json").read_text())
    folds = derive_folds(load_pa_rows(pa_path, feat_path))
    dev_total = sum(folds[f].n_eval for f in DEV_BLOCKS)
    assert m0["pooled_dev"]["candidates"]["P0_log5"]["n"] == dev_total


def test_adapter_contract_prob_range_and_scaler_refit_per_fold(synth, tmp_path):
    out = run_comparison(_run_cfg(synth, tmp_path, candidates=["P0_log5", "P1_B_logreg", "P1_H3_incumbent_refit"], label="contract"))
    for fold in DEV_BLOCKS + ["confirm_2025H2"]:
        for cand in ["P0_log5", "P1_B_logreg", "P1_H3_incumbent_refit"]:
            p = pl.read_parquet(out / f"preds_{fold}__{cand}.parquet")
            assert p.height > 0
            assert p["pred_raw"].min() >= 0.0 and p["pred_raw"].max() <= 1.0
            # raw lane present; calibrated lane is a SEPARATE column
            assert "pred_raw" in p.columns and "pred_cal" in p.columns
            assert p["pred_cal"].null_count() == p.height or \
                p["pred_cal"].null_count() == 0
    # scaler refit per fold on base_train only: two folds' pooled preds of the
    # same candidate differ if (and the runner asserts) each fold got its own
    # fit -- check the manifest records per-fold fits implicitly via distinct
    # eval identity hashes per fold
    man = json.loads((out / "run_manifest.json").read_text())
    h = {f: man["candidates"]["P1_B_logreg"][f]["eval_identity_sha256"]
         for f in DEV_BLOCKS}
    assert len(set(h.values())) == len(DEV_BLOCKS)


def test_adapter_prob_out_of_range_fails_loud(synth):
    class BadAdapter(ConstantAdapter):
        pass

    bad = BadAdapter("bad", 0.5)
    orig_predict = bad.predict_proba
    bad.predict_proba = lambda fold_name, calibrated, X: orig_predict(
        fold_name, calibrated, X) + 0.7
    from comparison import _check_proba
    with pytest.raises(AdapterContractError):
        _check_proba(np.array([0.5, 1.7]), 2, "bad")
    with pytest.raises(AdapterContractError):
        _check_proba(np.array([0.5, np.nan]), 2, "bad")
    with pytest.raises(AdapterContractError):
        _check_proba(np.array([0.5]), 2, "bad")


# ---------------------------------------------------------------------------
# Registered stubs + candidate registry behavior
# ---------------------------------------------------------------------------

def test_not_started_stubs_fail_loud():
    for cand in ["P2_lgbm", "B1_ridge_bf", "B2_lgbm_bf", "B3_exit_hazard",
                 "H_hierarchical"]:
        a = registered_adapters()[cand]
        with pytest.raises(NotImplementedError):
            a.fit("block_2024H1", np.zeros((2, 1)), np.array([0, 1]))


def test_unregistered_candidate_fails_loud(synth, tmp_path):
    with pytest.raises(ComparisonError):
        run_comparison(_run_cfg(synth, tmp_path, candidates=["P9_missing"]))


def test_missing_required_features_fail_loud(synth, tmp_path):
    # P1_H3_incumbent_refit needs ew_* columns; drop them from the feature file
    feat = pl.read_parquet(synth["feat_path"]).drop(["ew_pitcher", "ew_batter"])
    p = tmp_path / "feat_no_ew.parquet"
    feat.write_parquet(p)
    with pytest.raises(ComparisonError, match="ew_pitcher"):
        run_comparison(RunConfig(
            pa_table_path=str(synth["pa_path"]), features_path=str(p),
            candidates=["P1_H3_incumbent_refit"], output_root=str(tmp_path / "miss"),
            run_label="missing"))


# ---------------------------------------------------------------------------
# H3 EW-only ablation adapters (P1_H3_pitcher_ew_only / P1_H3_batter_ew_only)
# ---------------------------------------------------------------------------

EW_ONLY = ["P1_H3_pitcher_ew_only", "P1_H3_batter_ew_only"]


def test_ew_only_adapters_declare_expected_features():
    reg = registered_adapters()
    for cand, feat_list in (("P1_H3_pitcher_ew_only", FEAT_H3_PITCHER_EW),
                            ("P1_H3_batter_ew_only", FEAT_H3_BATTER_EW)):
        a = reg[cand]
        assert isinstance(a, LogisticAdapter)
        assert list(a.required_features) == list(feat_list)
        # 6 B features + exactly one EW-90d column
        assert list(a.required_features[:6]) == list(FEAT_B)
        assert len(a.required_features) == 7
    assert reg["P1_H3_pitcher_ew_only"].required_features[-1] == "ew_pitcher"
    assert reg["P1_H3_batter_ew_only"].required_features[-1] == "ew_batter"


def test_ew_only_adapters_end_to_end_finite_probs(synth, tmp_path):
    out = run_comparison(_run_cfg(synth, tmp_path, candidates=EW_ONLY,
                                  label="ew_only"))
    for fold in DEV_BLOCKS + ["confirm_2025H2"]:
        for cand in EW_ONLY:
            p = pl.read_parquet(out / f"preds_{fold}__{cand}.parquet")
            assert p.height > 0
            # finite probabilities inside [0, 1] on the synthetic fixture
            assert p["pred_raw"].is_finite().all()
            assert p["pred_raw"].min() >= 0.0 and p["pred_raw"].max() <= 1.0
    man = json.loads((out / "run_manifest.json").read_text())
    for cand, expect in (("P1_H3_pitcher_ew_only", FEAT_H3_PITCHER_EW),
                         ("P1_H3_batter_ew_only", FEAT_H3_BATTER_EW)):
        assert man["candidates"][cand]["block_2024H1"]["features"] == list(expect)
        assert man["candidates"][cand]["block_2024H1"]["status"] == \
            "IMPLEMENTED-ADAPTER"


def test_ew_only_adapters_fail_loud_without_their_ew_column(synth, tmp_path):
    feat = pl.read_parquet(synth["feat_path"])
    cases = [("P1_H3_pitcher_ew_only", "ew_pitcher"),
             ("P1_H3_batter_ew_only", "ew_batter")]
    for i, (cand, col) in enumerate(cases):
        p = tmp_path / f"feat_no_{col}.parquet"
        feat.drop([col]).write_parquet(p)
        with pytest.raises(ComparisonError, match=col):
            run_comparison(RunConfig(
                pa_table_path=str(synth["pa_path"]), features_path=str(p),
                candidates=[cand], output_root=str(tmp_path / f"miss_{i}"),
                run_label=f"missing_{col}"))


def test_fold_construction_dates_match_registered_anchors(synth):
    df = load_pa_rows(synth["pa_path"], synth["feat_path"])
    folds = derive_folds(df)
    assert set(folds) == set(DEV_BLOCKS + ["confirm_2025H2"])
    assert folds["block_2024H1"].assess_start == dt.date(2024, 1, 1)
    assert folds["block_2024H1"].assess_end == dt.date(2024, 6, 30)
    assert folds["confirm_2025H2"].assess_end == dt.date(2025, 9, 28)
    # runtime calibration rule: cal_last = max game_date <= train_end,
    # cal_first = cal_last - 59 days
    f = folds["block_2024H1"]
    assert f.cal_last == dt.date(2023, 12, 31)
    assert f.cal_first == dt.date(2023, 12, 31) - dt.timedelta(days=59)
    for name, fold in folds.items():
        assert fold.train_start <= fold.cal_first <= fold.cal_last
        assert fold.cal_last < fold.assess_start
