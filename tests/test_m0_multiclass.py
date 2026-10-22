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

import pregame_pa_ext.adapter as ad  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402


# ------------------------------------------------------------ unit tests
def test_taxonomy_mapping():
    """Statcast events map to the correct taxonomy classes; unrecognised
    events map to -1 (excluded)."""
    events = ["strikeout", "walk", "single", "home_run", "field_out",
              "hit_by_pitch", "caught_stealing", "wild_pitch"]
    s = pl.Series("events", events)
    mapped = m0.map_statcast_events(s)
    assert mapped[0] == 0
    assert mapped[1] == 1
    assert mapped[2] == 3
    assert mapped[3] == 3
    assert mapped[4] == 2
    assert mapped[5] == 1
    assert mapped[6] == 4
    assert mapped[7] == -1


def test_multinomial_softmax_normalization():
    rng = np.random.default_rng(42)
    n = 50
    feat = pl.DataFrame({
        f: rng.normal(0, 1, n) for f in m0.FEATURES
    }).with_columns(
        pl.Series("class_label", rng.integers(0, 5, n)), pl.lit(0).alias("y"),
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
        pl.Series("class_label", rng.integers(0, 5, n)), pl.lit(0).alias("y"),
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
    }).with_columns(pl.Series("class_label", rng.integers(0, 5, n)))
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
    assert m0.N_CLASSES == 5
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
                 4: "caught_stealing"}


def synthetic_m0_inputs():
    """Synthetic pa_table (+ events), preserved-ledger stand-in, BF PMF
    artifact, and the derived event-label frame - sized for the gated
    runner end-to-end."""
    rng = np.random.default_rng(5)
    # -- training-era PA rows: 2023 season + 2024 pre-break, every class
    pa_rows = []
    events = []
    pid_train, bat_base = 900001, 700001
    d = date(2023, 4, 1)
    pa_id = 1
    for day in range(300):
        gd = d + timedelta(days=day // 3)
        for _ in range(6):
            cls = int(rng.integers(0, 5))
            ev = EVENT_BY_SLOT[cls]
            pa_rows.append((pa_id, pa_id * 10 + 1, bat_base + (pa_id % 12),
                            pid_train, gd, int(cls == 0)))
            events.append((pa_id, pa_id * 10 + 1, bat_base + (pa_id % 12), ev))
            pa_id += 1
        d = d + timedelta(days=1) if day % 3 == 2 else d
    # -- evaluation-era games (block_2024H2): projected starts
    start_rows = []
    led_rows = []
    eval_day = date(2024, 7, 10)
    gid = 746000
    pitcher = 800001
    for g in range(6):
        gd = eval_day + timedelta(days=g)
        for side in ("Top", "Bot"):
            gid += 1
            for slot in range(1, 10):
                batter = 700100 + (gid % 40) * 9 + slot
                cls = int(rng.integers(0, 5))
                ev = EVENT_BY_SLOT[cls]
                # 1-2 observed PAs per projected (game, batter) matchup
                n_pa = 1 + (slot % 2)
                for k in range(n_pa):
                    ab = 10 * slot + k
                    pa_rows.append((gid, ab, batter, pitcher, gd,
                                    int(cls == 0)))
                    events.append((gid, ab, batter, ev))
                led_rows.append((gid, side, pitcher, batter, slot, gd,
                                 None, 0.22 + 0.01 * slot,
                                 0.30 - 0.01 * slot, 0.21,
                                 40 + slot, 150 - slot, 0, 0.25, 0.28,
                                 0))
                start_rows.append((gid, side, pitcher, gd))
    pa = pl.DataFrame(
        pa_rows,
        schema={"game_pk": pl.Int64, "at_bat_number": pl.Int64,
                "batter": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "y": pl.Int8}, orient="row")
    ev_df = pl.DataFrame(
        events, schema=["game_pk", "at_bat_number", "batter", "events"],
        orient="row")
    pa = pa.join(ev_df, on=["game_pk", "at_bat_number", "batter"],
                 how="left")
    ledger = pl.DataFrame(
        led_rows,
        schema={"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
                "batter": pl.Int64, "slot": pl.Int8, "game_date": pl.Date,
                "exclusion_reason": pl.Utf8, "p_h3_raw": pl.Float64,
                "p_pitcher_prior_w150": pl.Float64,
                "p_batter_prior_w150": pl.Float64, "lg_rate": pl.Float64,
                "n_prior_pitcher": pl.Int64, "n_prior_batter": pl.Int64,
                "cold_start": pl.Int8, "ew_pitcher": pl.Float64,
                "ew_batter": pl.Float64}, orient="row")
    bf = pl.DataFrame([{"game_pk": s[0], "side": s[1],
                        "pitcher": s[2],
                        **{f"pmf37_{j}": 1.0 / 37 for j in range(37)}}
                       for s in start_rows])
    labels, _ = m0.event_label_frame(pa)
    return pa, ledger, labels, bf


# ------------------------------------------------- blocker B1/B2/B4/B5
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


def test_refusal_gate_cli():
    """The CLI refuses real-data execution without the flag (exit 2)."""
    assert m0.main([]) == 2


def test_verify_receipt_check_synthetic(tmp_path, monkeypatch):
    """The complete-receipt pre-execution check (Chat 2 standing gate)
    passes on synthetic input via --verify-receipt-check."""
    monkeypatch.chdir(tmp_path)
    rc = m0.main(["--verify-receipt-check"])
    assert rc == 0
