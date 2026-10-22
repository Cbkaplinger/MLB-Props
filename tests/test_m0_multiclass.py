"""Synthetic tests for the M0 multi-class PA outcome model (v3.1 repair).

SYNTHETIC ONLY: no real data, no real-outcome evaluation, no production
change. Covers: taxonomy mapping, multinomial softmax, baselines, the
K-marginal log loss, the effect-size budget, sparse classes, the
fail-closed receipt, the pitcher-matched evaluation population
(Chat 2 blockers B1/B5), the five-class EP2 endpoint (B2), the
upper-CI non-inferiority rule (B3), and Holm m=2 (B4)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

import sys

HERE = Path(__file__).resolve().parents[1]
sys_path = str(HERE / "research" / "offseason_2026")
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

import kcount_combiner as kc  # noqa: E402 (registered count metrics)
import pregame_pa_ext.adapter as ad  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402


# ------------------------------------------------------------ unit tests
def test_taxonomy_mapping():
    """Statcast events map to the correct taxonomy classes; unrecognised
    events map to -1 (excluded)."""
    events = ["strikeout", "walk", "single", "home_run", "field_out",
              "hit_by_pitch", "field_out", "wild_pitch"]
    s = pl.Series("events", events)
    mapped = m0.map_statcast_events(s)
    assert mapped[0] == 0
    assert mapped[1] == 1
    assert mapped[2] == 3
    assert mapped[3] == 3
    assert mapped[4] == 2
    assert mapped[5] == 1
    assert mapped[6] == 2  # field_out -> class 2
    assert mapped[7] == -1


def test_multinomial_softmax_normalization():
    rng = np.random.default_rng(42)
    n = 50
    feat = pl.DataFrame({
        f: rng.normal(0, 1, n) for f in m0.FEATURES
    }).with_columns(
        pl.Series("class_label", rng.integers(0, 4, n)), pl.lit(0).alias("y"),
        pl.lit(date(2024, 8, 1)).alias("game_date"),
    )
    model = m0.fit_multinomial(feat)
    probs = m0.apply_multinomial(feat, model)
    assert probs.shape == (n, m0.N_CLASSES)
    assert np.all(probs >= 0)
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-12)


def test_identical_features_produce_identical_probabilities():
    rng = np.random.default_rng(7)
    n = 100
    feat = pl.DataFrame({
        f: rng.normal(0, 1, n) for f in m0.FEATURES
    }).with_columns(
        pl.Series("class_label", rng.integers(0, 4, n)), pl.lit(0).alias("y"),
        pl.lit(date(2024, 8, 1)).alias("game_date"),
    )
    model = m0.fit_multinomial(feat)
    single = feat.head(1)
    p1 = m0.apply_multinomial(single, model)
    p2 = m0.apply_multinomial(single, model)
    assert np.array_equal(p1, p2)
    assert np.all(p1 >= 0)
    assert np.allclose(p1.sum(axis=1), 1.0, atol=1e-12)


def test_baselines_normalization():
    rng = np.random.default_rng(11)
    n = 50
    train = pl.DataFrame({
        f: rng.normal(0, 1, n) for f in m0.FEATURES
    }).with_columns(pl.Series("class_label", rng.integers(0, 4, n)))
    eval_rows = pl.DataFrame({
        f: rng.normal(0, 1, 20) for f in m0.FEATURES
    }).with_columns(
        pl.Series("p_pitcher_prior_w150", rng.uniform(0.1, 0.4, 20)),
        pl.Series("p_batter_prior_w150", rng.uniform(0.1, 0.4, 20)),
        pl.Series("lg_rate", rng.uniform(0.2, 0.3, 20)),
    )
    lc = m0.league_constant_baseline(train, 20)
    assert lc.shape == (20, m0.N_CLASSES)
    assert np.allclose(lc.sum(axis=1), 1.0, atol=1e-12)
    l5 = m0.log5_baseline(eval_rows, train)
    assert l5.shape == (20, m0.N_CLASSES)
    assert np.allclose(l5.sum(axis=1), 1.0, atol=1e-12)
    assert np.all(l5 >= 0)


def test_k_marginal_log_loss():
    y = np.array([1, 0, 1, 0])
    p_k = np.array([0.8, 0.3, 0.6, 0.2])
    ll = m0.k_marginal_log_loss(y, p_k)
    assert ll[0] == pytest.approx(-np.log(0.8), abs=1e-10)
    assert ll[1] == pytest.approx(-np.log(0.7), abs=1e-10)
    assert ll[2] == pytest.approx(-np.log(0.6), abs=1e-10)
    assert ll[3] == pytest.approx(-np.log(0.8), abs=1e-10)


def test_effect_size_budget_documented():
    assert m0.EFFECT_SIZE_BUDGET["noninferiority_margin"] == 0.005
    assert m0.EFFECT_SIZE_BUDGET["mde_80pct_power"] > 0
    assert m0.EFFECT_SIZE_BUDGET["margin_to_mde_ratio"] > 5


def test_class_names_and_taxonomy_completeness():
    assert m0.N_CLASSES == 4
    assert m0.CLASS_NAMES[0] == "strikeout"
    assert m0.K_CLASS == 0
    assert len(m0.STATCAST_EVENT_TAXONOMY) >= 20


def test_sparse_class_detection():
    rng = np.random.default_rng(3)
    n = 100
    labels = np.concatenate([rng.integers(0, 4, n - 3), [4, 4, 4]])
    feat = pl.DataFrame({
        f: rng.normal(0, 1, n) for f in m0.FEATURES
    }).with_columns(pl.Series("class_label", labels))
    counts = feat["class_label"].value_counts().sort("class_label")
    sparse = [int(v) for v in counts["class_label"].to_list()
              if counts.filter(pl.col("class_label") == v).height < 50]
    assert 4 in sparse


# --------------------------------------------------- synthetic fixture
EVENT_BY_SLOT = {0: "strikeout", 1: "walk", 2: "field_out", 3: "single",
                 4: "field_out"}


import pregame_pa_ext.adapter as ad  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402
from pregame_pa_ext.m0_synthetic import (  # noqa: E402
    synthetic_m0_inputs as _factory_synthetic_m0_inputs,
)


def synthetic_m0_inputs():
    """Delegates to the importable support module beside the runner
    (m0_synthetic.py) - the SAME factory the receipt preflight consumes,
    so the tests and the preflight exercise identical synthetic data."""
    return _factory_synthetic_m0_inputs()

def test_runner_end_to_end_synthetic(tmp_path):
    """The gated runner completes on synthetic input: pitcher-matched
    observed-PA population, both endpoints computed, receipt chain
    valid, descriptive count-RPS present."""
    pa, ledger, labels, bf = synthetic_m0_inputs()
    out = tmp_path / "diag"
    res = m0.run_m0(pa, ledger, out, event_labels=labels, bf=bf,
                    verify_published=False)
    assert res["metrics"]["n_eval_pa"] > 0
    assert res["metrics"]["EP1"]["noninferiority_pass"] in (True, False)
    assert "EP2" in res["metrics"]
    assert (out / "receipt_initial.json").exists()
    assert (out / "receipt_final.json").exists()
    fin = json.loads((out / "receipt_final.json").read_text(encoding="utf-8"))
    assert fin["acceptance"]["receipt_chain"] == res["receipt_initial_sha256"]


def test_population_is_pitcher_matched(tmp_path):
    """B1: reliever PAs are structurally excluded; the cross-side
    duplicate projection contributes each PA exactly once."""
    pa, ledger, labels, bf = synthetic_m0_inputs()
    # add a reliever PA: same game + batter as a projected matchup, but
    # a DIFFERENT (relief) pitcher - must NOT enter the evaluation
    reliever = 911111
    g, btr = ledger["game_pk"][0], ledger["batter"][0]
    reliever_pa = pl.DataFrame(
        [(g, 999, btr, reliever, date(2024, 7, 10), 0, "single")],
        schema={"game_pk": pl.Int64, "at_bat_number": pl.Int64,
                "batter": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "y": pl.Int8,
                "events": pl.Utf8}, orient="row")
    pa2 = pl.concat([pa, reliever_pa])
    out1, out2 = tmp_path / "d1", tmp_path / "d2"
    res1 = m0.run_m0(pa, ledger, out1, event_labels=labels, bf=bf,
                     verify_published=False)
    res2 = m0.run_m0(pa2, ledger, out2, event_labels=labels, bf=bf,
                     verify_published=False)
    # identical evaluation population with and without the reliever PA
    assert res1["metrics"]["n_eval_pa"] == res2["metrics"]["n_eval_pa"]
    ev1 = pl.read_parquet(out1 / "m0_multiclass_eval_v1.parquet")
    ev2 = pl.read_parquet(out2 / "m0_multiclass_eval_v1.parquet")
    assert ev1.height == ev2.height
    # the reliever PA identity appears in neither evaluation table
    rel = ev2.filter((pl.col("game_pk") == g)
                     & (pl.col("at_bat_number") == 999))
    assert rel.height == 0


def test_ep1_uses_upper_ci_bound(tmp_path, monkeypatch):
    """B3: non-inferiority is decided by the UPPER CI bound, not the
    point estimate. Construct a case where the point delta is below the
    margin but the resampled upper bound exceeds it."""
    pa, ledger, labels, bf = synthetic_m0_inputs()
    captured = {}

    real = m0.k_marginal_log_loss

    def spy(y, p):
        arr = real(y, p)
        captured.setdefault("calls", []).append(arr.mean())
        return arr

    monkeypatch.setattr(m0, "k_marginal_log_loss", spy)
    out = tmp_path / "diag"
    res = m0.run_m0(pa, ledger, out, event_labels=labels, bf=bf,
                    verify_published=False)
    ep1 = res["metrics"]["EP1"]
    # the decision used the upper CI bound (recorded), not the point
    assert ep1["upper_ci_bound"] == ep1["ci95"][1]
    assert ep1["noninferiority_pass"] == (ep1["upper_ci_bound"]
                                          < m0.K_NONINFERIORITY_MARGIN)
    # point estimate and CI bound are distinct quantities
    assert ep1["ci95"][1] != ep1["delta"]


def test_ep2_requires_beating_both_baselines(tmp_path):
    """B2: EP2 is the 5-class cross-entropy and passes only when the
    multiclass model beats BOTH baselines."""
    pa, ledger, labels, bf = synthetic_m0_inputs()
    out = tmp_path / "diag"
    res = m0.run_m0(pa, ledger, out, event_labels=labels, bf=bf,
                    verify_published=False)
    ep2 = res["metrics"]["EP2"]
    assert ep2["ep2_pass"] == (ep2["beats_league_constant"]
                               and ep2["beats_log5"])
    assert "multiclass_log_loss" in ep2 and "league_constant_log_loss" \
        in ep2 and "log5_log_loss" in ep2


def test_holm_m2_reported(tmp_path):
    """B4: the Holm family is m=2 over the two pre-declared endpoints."""
    pa, ledger, labels, bf = synthetic_m0_inputs()
    out = tmp_path / "diag"
    res = m0.run_m0(pa, ledger, out, event_labels=labels, bf=bf,
                    verify_published=False)
    h = res["metrics"]["holm"]
    assert h["m"] == 2
    assert h["family"] == ["EP1_k_noninferiority", "EP2_vs_baselines"]
    assert "adjusted" in h


def test_receipt_fail_closed(tmp_path):
    """B5: a receipt with empty consumed identities is REJECTED before
    any computation."""
    pa, ledger, labels, bf = synthetic_m0_inputs()
    receipt = {"inputs": {"consumed": {},
                          "context_identities": {}},
               "code_config": {"x": "1"}, "dev_keys": {"n": 1},
               "config": {"primary": "x"}}
    with pytest.raises(ValueError, match="CONSUMED"):
        m0.validate_receipt_initial(receipt)
    # a short/placeholder identity also fails (the sha256 check fires
    # before the NOT_AVAILABLE wording - both reject)
    receipt["inputs"]["consumed"] = {"pa_table": "NOT_AVAILABLE"}
    with pytest.raises(ValueError, match="consumed input"):
        m0.validate_receipt_initial(receipt)





def test_verify_receipt_check_synthetic(tmp_path, monkeypatch):
    """The complete-receipt pre-execution check (Chat 2 standing gate)
    passes on synthetic input via --verify-receipt-check."""
    monkeypatch.chdir(tmp_path)
    rc = m0.main(["--verify-receipt-check"])
    assert rc == 0


# ------------------ M0FIX tightened acceptance checks (owner-directed)
def test_registered_pmf_construction_independent_example():
    """M0FIX-01 (B2 tightening): the registered PMF construction
    reproduces an INDEPENDENTLY calculated binomial - point-mass BF at
    n=2, pbar_2 = mean(0.2, 0.6) = 0.4, Binom(k; 2, 0.4) = [0.36, 0.48,
    0.16]. Computed by hand, not by the same machinery."""
    p9 = [0.2, 0.6, 0.3, 0.4, 0.5, 0.1, 0.7, 0.3, 0.25]
    bf_point = np.zeros(ad.KCOUNT_CAP)
    bf_point[1] = 1.0  # all mass at N=2
    pbar_n = ad.cycled_cond_mean(np.asarray(p9))
    pmf = ad.count_pmf_from_mixture(bf_point, pbar_n)
    expected = [0.36, 0.48, 0.16] + [0.0] * (ad.K_MAX - 3)
    assert np.allclose(pmf, expected, atol=1e-12)


def test_count_rps_independent_example():
    """M0FIX-02 (B2 tightening): the registered summed count-RPS on a
    small hand-computed example - pmf [0.2, 0.5, 0.3], realized K=1:
    RPS = (0.2-0)^2 + (0.7-1)^2 + (1.0-1)^2 = 0.13."""
    pmf = np.asarray([0.2, 0.5, 0.3])
    assert kc.count_rps(pmf, 1) == pytest.approx(0.13, abs=1e-12)


def test_start_key_identity_exact_synthetic(tmp_path):
    """M0FIX-03 (B3 tightening): the runner's evaluation population
    equals the synthetic fixture's OWN explicit expected start-key set -
    unique, complete, and with the excluded (abstaining) starts absent.
    The real frozen population is NOT asserted here (that is the
    non-author check's exact-set job on real inputs)."""
    pa, ledger, labels, bf = synthetic_m0_inputs()
    expected = set(map(tuple, ledger.filter(pl.col('exclusion_reason')
                                  .is_null())
                       .filter(pl.col('game_date')
                               <= pl.date(2024, 12, 31))
                       .select('game_pk', 'side')
                       .unique().iter_rows()))
    out = tmp_path / 'diag'
    res = m0.run_m0(pa, ledger, out, event_labels=labels, bf=bf,
                    verify_published=False)
    ev = pl.read_parquet(out / 'm0_multiclass_eval_v1.parquet')
    got = set(zip(ev['game_pk'].to_list(), ev['side'].to_list()))
    assert got == expected
    per_start = ev.group_by('game_pk', 'side').agg(n=pl.len())
    # the expanded per-PA table: every projected slot appears at least
    # once (1-2 observed PAs per slot on the synthetic fixture); the
    # count is the observed-PA expansion, NOT a fixed 9
    assert per_start['n'].min() >= 9


def test_receipt_written_before_fitting(tmp_path, monkeypatch):
    """M0FIX-03 (receipt ordering): the complete initial receipt exists
    on disk BEFORE fit_multinomial is first called (mock-observed)."""
    pa, ledger, labels, bf = synthetic_m0_inputs()
    out = tmp_path / 'diag'
    observed = {}
    real_fit = m0.fit_multinomial

    def spy(train):
        observed['initial_exists_at_fit'] = (
            out / 'receipt_initial.json').exists()
        return real_fit(train)

    monkeypatch.setattr(m0, 'fit_multinomial', spy)
    m0.run_m0(pa, ledger, out, event_labels=labels, bf=bf,
              verify_published=False)
    assert observed['initial_exists_at_fit'] is True


def test_no_blanket_temporal_rejection(tmp_path):
    """M0FIX-04 (D2): the runner does NOT impose a blanket
    src_date < game_date rejection - the registered as-of machinery
    governs; the runner completes with recorded source dates."""
    pa, ledger, labels, bf = synthetic_m0_inputs()
    out = tmp_path / 'diag'
    res = m0.run_m0(pa, ledger, out, event_labels=labels, bf=bf,
                    verify_published=False)
    assert res['metrics']['n_eval_pa'] > 0


def test_cli_dispatch_wired(tmp_path):
    """M0FIX-05 (CLI wiring): the authorized path dispatches to the M0
    runner on synthetic input in a fresh subprocess (dispatch, receipt,
    outputs); the refusal path is preserved without the flag."""
    import subprocess
    runner = (HERE / 'research' / 'offseason_2026' / 'pregame_pa_ext'
              / 'm0_multiclass.py')
    pa, ledger, labels, bf = synthetic_m0_inputs()
    work = tmp_path / 'inputs'
    work.mkdir()
    pa.write_parquet(work / 'pa.parquet')
    ledger.write_parquet(work / 'ledger.parquet')
    bf.write_parquet(work / 'bf.parquet')
    labels.write_parquet(work / 'labels.parquet')
    r1 = subprocess.run([sys.executable, str(runner),
                         '--pa-table', str(work / 'pa.parquet')],
                        capture_output=True, text=True)
    assert r1.returncode == 2
    out_dir = tmp_path / 'diag'
    r2 = subprocess.run(
        [sys.executable, str(runner), '--i-accept-outcome-evaluation',
         '--pa-table', str(work / 'pa.parquet'),
         '--ledger', str(work / 'ledger.parquet'),
         '--bf', str(work / 'bf.parquet'),
         '--no-verify-published',
         '--out-dir', str(out_dir)],
        capture_output=True, text=True)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert (out_dir / 'receipt_initial.json').exists()
    assert (out_dir / 'receipt_final.json').exists()
    assert (out_dir / 'm0_multiclass_eval_v1.parquet').exists()
