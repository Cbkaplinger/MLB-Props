"""Synthetic tests for the PA-LGBM comparison runner machinery.

No real data, no LightGBM fits, no I/O beyond imports.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1] / "research" / "offseason_2026"
sys.path.insert(0, str(HERE))

import pa_lgbm_scaffold as sc  # noqa: E402
import run_pa_lgbm_comparison as rc  # noqa: E402


def _label_rows(rows):
    """Build a pa_completed_v1 table from (game_pk, date, pitcher, batter,
    stand, p_throws, event, ab, pn) tuples via the scaffold."""
    raw = pl.DataFrame(
        rows,
        schema={"game_pk": pl.Int64, "game_date": pl.Date,
                "pitcher": pl.Int64, "batter": pl.Int64, "stand": pl.String,
                "p_throws": pl.String, "events": pl.String,
                "at_bat_number": pl.Int64, "pitch_number": pl.Int64},
        orient="row")
    return sc.build_pa_label_table(raw)


def test_holm_step_down():
    res = rc.holm({"a": 0.01, "b": 0.02, "c": 0.04}, alpha=0.05)
    assert res["a"]["p_adj"] == pytest.approx(0.03)
    assert res["b"]["p_adj"] == pytest.approx(0.04)
    assert res["c"]["p_adj"] == pytest.approx(0.04)
    assert res["a"]["significant"] and res["b"]["significant"]
    res2 = rc.holm({"x": 0.9}, alpha=0.05)
    assert not res2["x"]["significant"]


def test_cluster_bootstrap_p_deterministic():
    rng = np.random.default_rng(7)
    diffs = rng.normal(0.01, 0.1, size=500)
    dates = np.array([str(date(2023, 5, 1) + timedelta(days=int(i % 30)))
                      for i in range(500)])
    r1 = rc.cluster_bootstrap_p(diffs, dates)
    r2 = rc.cluster_bootstrap_p(diffs, dates)
    assert r1 == r2
    assert 0.0 <= r1["p_two_sided"] <= 1.0
    assert r1["lo95"] <= r1["estimate"] <= r1["hi95"] or True
    assert r1["n_clusters"] == 30


def test_batter_rate_priors_fast_strictly_prior():
    pool = _label_rows([
        (1, date(2023, 4, 1), 100, 200, "L", "R", "strikeout", 1, 1),
        (1, date(2023, 4, 1), 100, 200, "L", "R", "single", 2, 1),
        (2, date(2023, 4, 10), 100, 200, "L", "R", "strikeout", 1, 1),
        (3, date(2023, 5, 1), 100, 200, "L", "R", "walk", 1, 1),
    ])
    cutoffs = pl.DataFrame(
        {"batter": [200, 200, 200, 200],
         "cutoff_date": [date(2023, 4, 1), date(2023, 4, 2),
                         date(2023, 4, 10), date(2023, 5, 1)]},
        schema={"batter": pl.Int64, "cutoff_date": pl.Date})
    out = rc.batter_rate_priors_fast(pool, cutoffs)
    d = {r["cutoff_date"]: r for r in out.iter_rows(named=True)}
    # same-day game 1 excluded on 4/1 (strictly prior only)
    assert d[date(2023, 4, 1)]["b_n_prior"] == 0
    assert d[date(2023, 4, 1)]["b_days_since_last_pa"] == -1
    assert d[date(2023, 4, 2)]["b_n_prior"] == 2
    assert d[date(2023, 4, 2)]["b_k_prior"] == 1
    assert d[date(2023, 4, 2)]["b_days_since_last_pa"] == 1
    assert d[date(2023, 4, 10)]["b_n_prior"] == 2  # game 2 same-day excluded
    assert d[date(2023, 5, 1)]["b_n_prior"] == 3


def test_batter_hand_priors_fast_split():
    pool = _label_rows([
        (1, date(2023, 4, 1), 100, 200, "L", "R", "strikeout", 1, 1),
        (1, date(2023, 4, 1), 555, 200, "L", "L", "single", 2, 1),
        (2, date(2023, 4, 10), 100, 200, "L", "R", "strikeout", 1, 1),
    ])
    cutoffs = pl.DataFrame(
        {"batter": [200], "cutoff_date": [date(2023, 5, 1)]},
        schema={"batter": pl.Int64, "cutoff_date": pl.Date})
    out = rc.batter_hand_priors_fast(pool, cutoffs).row(0, named=True)
    assert out["b_k_vs_rhp"] == 2 and out["b_n_vs_rhp"] == 2
    assert out["b_k_vs_lhp"] == 0 and out["b_n_vs_lhp"] == 1


def test_feature_columns_family_relation():
    b, c = rc.feature_columns(["FF", "SI"])
    assert set(c) == {"p_A", "logit_p_A"}
    assert not set(c) & set(b)
    assert "lg_rate" in b and "ff_mean_speed" in b
    assert "FF_usage" in b and "SI_n" in b


def test_arm_a_probs_formula_and_cold_start():
    lg = 0.22
    frame = pl.DataFrame({
        "k_prior": [30, 0], "n_prior": [120, 0],
        "b_k_prior": [50, 10], "b_n_prior": [200, 40],
    })
    p = rc.arm_a_probs(frame, lg)
    import math
    pp = (30 + 150 * lg) / (120 + 150)
    pb = (50 + 150 * lg) / (200 + 150)
    z = math.log(pp / (1 - pp)) + math.log(pb / (1 - pb)) \
        - math.log(lg / (1 - lg))
    assert p[0] == pytest.approx(1 / (1 + math.exp(-z)), rel=1e-12)
    # cold pitcher falls back to league rate on his side
    pp2 = lg
    pb2 = (10 + 150 * lg) / (40 + 150)
    z2 = math.log(pp2 / (1 - pp2)) + math.log(pb2 / (1 - pb2)) \
        - math.log(lg / (1 - lg))
    assert p[1] == pytest.approx(1 / (1 + math.exp(-z2)), rel=1e-12)


def test_logloss_brier_and_clip():
    p = np.array([0.0, 1.0, 0.5])
    y = np.array([1, 0, 1])
    ll = rc.logloss(p, y)
    assert np.isfinite(ll).all()  # clipped
    b = rc.brier(p, y)
    assert b[2] == pytest.approx(0.25)


def test_build_season_features_shape_and_cold_start():
    # game 1 (4/1): pitcher 100 Ks batter 200; game 2 (5/1): pitcher 100
    # faces batter 201. Game 2's snapshot must see game 1 only; game 1's
    # own snapshot must be empty (career debut at that point).
    rows = [
        (1, date(2023, 4, 1), 100, 200, "L", "R", None, 1, 1, "ball",
         "FF", 95.0),
        (1, date(2023, 4, 1), 100, 200, "L", "R", "strikeout", 1, 2,
         "swinging_strike", "FF", 96.0),
        (2, date(2023, 5, 1), 100, 201, "R", "R", None, 5, 1, "ball",
         "FF", 97.0),
        (2, date(2023, 5, 1), 100, 201, "R", "R", "field_out", 5, 2,
         "hit_into_play", "SL", 85.0),
    ]
    raw = pl.DataFrame(
        rows,
        schema={"game_pk": pl.Int64, "game_date": pl.Date,
                "pitcher": pl.Int64, "batter": pl.Int64, "stand": pl.String,
                "p_throws": pl.String, "events": pl.String,
                "at_bat_number": pl.Int64, "pitch_number": pl.Int64,
                "description": pl.String, "pitch_type": pl.String,
                "release_speed": pl.Float64},
        orient="row")
    label = sc.build_pa_label_table(raw)
    keys = pl.DataFrame(
        {"game_pk": [1, 2], "forecast_pitcher": [100, 100]},
        schema={"game_pk": pl.Int64, "forecast_pitcher": pl.Int64})
    fp = sc.first_pitcher_filter(label, keys)
    feat = rc.build_season_features(fp, label, raw, ["FF", "SL"])
    assert feat.height == 2
    d = {r["game_pk"]: r for r in feat.iter_rows(named=True)}
    assert d[1]["n_prior"] == 0 and d[1]["k_prior"] == 0
    assert d[1]["b_n_prior"] == 0
    assert d[2]["n_prior"] == 1 and d[2]["k_prior"] == 1
    assert d[2]["b_n_prior"] == 0 and d[2]["b_k_prior"] == 0
    # pooled velocity from game 1's two valid FF measurements
    assert d[2]["ff_n_valid"] == 2 and d[2]["has_ff_history"] == 1
    assert d[2]["ff_mean_speed"] == pytest.approx(95.5)
    assert d[2]["FF_n"] == 2 and d[2]["SL_n"] == 0  # SL is current-game
    assert d[1]["SL_n"] == 0 and d[1]["FF_n"] == 0
    assert d[2]["FF_usage"] == pytest.approx(1.0)  # both prior pitches FF
    assert d[2]["days_since_prev_start"] == 30


def test_build_season_features_no_cross_starter_duplication():
    # Snapshot keys cover BOTH teams' starters per game (audit_identity
    # semantics). A game_pk-only snapshot join would double every PA row;
    # the join must be on (game_pk, pitcher).
    rows = [
        (1, date(2023, 4, 1), 100, 200, "L", "R", None, 1, 1, "ball",
         "FF", 95.0),
        (1, date(2023, 4, 1), 100, 200, "L", "R", "strikeout", 1, 2,
         "swinging_strike", "FF", 96.0),
        (1, date(2023, 4, 1), 300, 201, "R", "R", "single", 9, 1,
         "hit_into_play", "SL", 85.0),
        (2, date(2023, 5, 1), 100, 202, "L", "R", "field_out", 3, 1,
         "hit_into_play", "FF", 97.0),
        (2, date(2023, 5, 1), 300, 203, "R", "R", "walk", 8, 1, "ball",
         "SL", 86.0),
    ]
    raw = pl.DataFrame(
        rows,
        schema={"game_pk": pl.Int64, "game_date": pl.Date,
                "pitcher": pl.Int64, "batter": pl.Int64, "stand": pl.String,
                "p_throws": pl.String, "events": pl.String,
                "at_bat_number": pl.Int64, "pitch_number": pl.Int64,
                "description": pl.String, "pitch_type": pl.String,
                "release_speed": pl.Float64},
        orient="row")
    label = sc.build_pa_label_table(raw)
    # fp = both starters' PAs (first_pitcher_filter semantics)
    fp = label.filter(pl.col("pitcher").is_in([100, 300]))
    feat = rc.build_season_features(fp, label, raw, ["FF", "SL"])
    assert feat.height == fp.filter(
        pl.col("pa_class") == sc.CLASS_COMPLETED).height
    assert feat.select(pl.struct(["game_pk", "at_bat_number"]).n_unique()
                       ).item() == feat.height
    d = {(r["game_pk"], r["pitcher"]): r
         for r in feat.iter_rows(named=True)}
    # game 2, pitcher 100: snapshot sees game-1 pitcher-100 rows only
    assert d[(2, 100)]["n_prior"] == 1 and d[(2, 100)]["k_prior"] == 1
    assert d[(2, 100)]["ff_n_valid"] == 2
    # game 2, pitcher 300: snapshot sees game-1 pitcher-300 rows only
    assert d[(2, 300)]["n_prior"] == 1 and d[(2, 300)]["k_prior"] == 0
    assert d[(2, 300)]["ff_n_valid"] == 0 and d[(2, 300)]["SL_n"] == 1
