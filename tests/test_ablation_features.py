"""Synthetic tests for the feature-set ablation harness. No real data.
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

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import ablation_features as ab  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402


def _synth_pa(n_players=6, days=40, seed=3, with_events=True):
    rng = np.random.default_rng(seed)
    rows = []
    d0 = date(2023, 4, 1)
    import datetime as dt
    pid = 0
    event_cycle = ["strikeout", "walk", "field_out", "single"]
    for p in range(n_players):
        base = 0.15 + 0.04 * p
        for d in range(days):
            gd = d0 + dt.timedelta(days=d)
            for k in range(10):
                pid += 1
                y = int(rng.random() < base + 0.001 * d)
                ev = event_cycle[pid % 4] if with_events else None
                rows.append((9000000 + p, pid, 600000 + pid % 40,
                             500000 + p, gd, y, ev))
    schema = {
        "game_pk": pl.Int64, "at_bat_number": pl.Int64,
        "batter": pl.Int64, "pitcher": pl.Int64,
        "game_date": pl.Date, "y": pl.Int8, "events": pl.Utf8,
    }
    return pl.DataFrame(rows, schema=schema, orient="row")


# ------------------------------------------------------------ EW variant
def test_entity_daily_state_hl_monotone_in_half_life():
    """A SHORTER half-life weights recent games more: after a rate
    drop, the EW rate at hl=30 sits BELOW the EW rate at hl=180."""
    import datetime as dt
    rows = []
    for d in range(60):
        gd = date(2023, 4, 1) + dt.timedelta(days=d)
        # 40 PAs/day; K rate 0.30 first 40 days, 0.10 last 20 days
        rate = 0.30 if d < 40 else 0.10
        for k in range(40):
            rows.append((1, k + 1, 600 + k, 500, gd,
                         int(k < rate * 40)))
    pa = pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "at_bat_number": pl.Int64,
        "batter": pl.Int64, "pitcher": pl.Int64,
        "game_date": pl.Date, "y": pl.Int8}, orient="row")
    s30 = ab.entity_daily_state_hl(pa, "pitcher", 30.0)
    s180 = ab.entity_daily_state_hl(pa, "pitcher", 180.0)
    late = date(2023, 5, 30)
    ew30 = s30.filter(pl.col("game_date") == late)["ew_k"][0] \
        / s30.filter(pl.col("game_date") == late)["ew_den"][0]
    ew180 = s180.filter(pl.col("game_date") == late)["ew_k"][0] \
        / s180.filter(pl.col("game_date") == late)["ew_den"][0]
    assert ew30 < ew180  # recent slump drags the short half-life lower
    # strictly-prior: the state at the LAST day excludes that day
    tot = pa.filter(pl.col("game_date") == late)["y"].sum()
    assert s30.filter(pl.col("game_date") == late)["prior_k"][0] \
        == pa.filter(pl.col("game_date") < late)["y"].sum()


def test_build_features_with_half_life_matches_registered_at_90():
    """The half-life shadow at 90.0 must reproduce the REGISTERED
    ew_pitcher on the same synthetic lineage (machinery identity)."""
    pa = _synth_pa()
    feat_hl = ab.build_features_with_half_life(pa, 90.0)
    p_daily = ad.entity_daily_state(pa, "pitcher")
    b_daily = ad.entity_daily_state(pa, "batter")
    lg = ad.league_daily_state(pa)
    long = pa.select("game_pk", "at_bat_number", "batter", "pitcher",
                     "game_date", "y")
    feat_reg = ad.attach_prior_features(long, p_daily, b_daily, lg)
    key = ["game_pk", "at_bat_number", "batter"]
    j = feat_hl.join(feat_reg, on=key, suffix="_reg")
    assert j.height == feat_reg.height
    assert np.allclose(j["ew_pitcher"].to_numpy(),
                       j["ew_pitcher_reg"].to_numpy(), atol=1e-12,
                       equal_nan=True)
    assert np.allclose(j["p_pitcher_prior_w150"].to_numpy(),
                       j["p_pitcher_prior_w150_reg"].to_numpy(),
                       atol=1e-12, equal_nan=True)


# ---------------------------------------------------------- fit/apply
def _labeled(pa, half_life=90.0):
    """Feature frame + labels WITHOUT touching any real data: the
    synthetic events column rides through and the labels derive from
    it (the raw-directory fallback is never reachable)."""
    feats = ab.build_features_with_half_life(pa, half_life)
    feats = feats.join(
        pa.select("game_pk", "at_bat_number", "batter", "events"),
        on=["game_pk", "at_bat_number", "batter"], how="left")
    return m0.build_multiclass_labels(feats)


def test_fit_apply_feature_subset_shapes_and_normalization():
    pa = _synth_pa()
    feat = _labeled(pa)
    # the frozen lineage's lg-finite rule: rows with non-finite features
    # (day-one league state 0/0) are excluded from fitting
    feat = feat.filter(pl.all_horizontal(
        [pl.col(c).is_finite() for c in ab.FEATURE_SETS["FULL"]]))
    assert feat.height > 0
    train = feat.head(1500)
    evalf = feat.tail(400)
    model = ab.fit_multinomial_features(train, ab.FEATURE_SETS["PITCHER"])
    probs = ab.apply_multinomial_features(evalf, model)
    assert probs.shape == (400, m0.N_CLASSES)
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-12)
    assert np.all(probs >= 0)
    with pytest.raises(ValueError):
        ab.fit_multinomial_features(train, [])


def test_league_constant_probs_normalization():
    pa = _synth_pa()
    feat = _labeled(pa)
    probs = ab.league_constant_probs(feat, 25)
    assert probs.shape == (25, m0.N_CLASSES)
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-12)
    assert np.allclose(probs[0], probs[-1])  # constant row


def test_evaluate_set_on_known_labels():
    feat = pl.DataFrame({
        "class_label": [0, 1, 2, 3],
        "y": [1, 0, 0, 0],
    })
    probs = np.array([
        [0.8, 0.1, 0.05, 0.05],
        [0.1, 0.8, 0.05, 0.05],
        [0.1, 0.1, 0.7, 0.1],
        [0.25, 0.25, 0.25, 0.25],
    ])
    res = ab.evaluate_set(feat, probs)
    assert res["n_eval_pa"] == 4
    # hand-check the first row's contribution
    expected_mc = -np.mean(np.log([
        0.8, 0.8, 0.7, 0.25]))
    assert res["multiclass_log_loss"] == pytest.approx(expected_mc,
                                                       abs=1e-9)


# --------------------------------------------------------- count RPS
def test_count_rps_from_eval_synthetic():
    rng = np.random.default_rng(9)
    starts = []
    for g in range(4):
        for slot in range(1, 10):
            starts.append((800000 + g, "Top" if g % 2 else "Bot",
                           700000 + g, slot,
                           date(2024, 8, 1) if g < 2
                           else date(2025, 4, 1)))
    feat = pl.DataFrame(starts, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "slot": pl.Int8, "game_date": pl.Date}, orient="row")
    feat = feat.with_columns((pl.col("slot").cast(pl.Int64)
                              * 10).alias("at_bat_number"))
    probs = rng.dirichlet(np.ones(4) * 3, size=36)
    bf = pl.DataFrame([{"game_pk": 800000 + g,
                        "side": "Top" if g % 2 else "Bot",
                        "pitcher": 700000 + g,
                        **{f"pmf37_{j}": 1.0 / 37 for j in range(37)}}
                       for g in range(4)])
    realized = pl.DataFrame(
        [(800000 + g, "Top" if g % 2 else "Bot", 700000 + g, 3)
         for g in range(4)],
        schema={"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
                "realized_k": pl.Int64}, orient="row")
    out = ab.count_rps_from_eval(probs, feat, bf, realized)
    assert out["rps"].shape == (4,)
    assert np.all(np.isfinite(out["rps"]))
    assert len(out["keys"]) == 4
    # realized-count mismatch fails loud
    with pytest.raises(ValueError, match="realized count mismatch"):
        ab.count_rps_from_eval(probs, feat, bf,
                               realized.filter(pl.col("game_pk") != 800000))
    # a start with a missing slot is SKIPPED and disclosed (the
    # registered count layer needs 9 slots; cold exclusions drop some)
    feat_i = feat.with_row_index("_i")
    idx = (feat_i.filter((pl.col("game_pk") == 800000)
                         & (pl.col("slot") == 9))["_i"][0])
    out = ab.count_rps_from_eval(np.delete(probs, idx, axis=0),
                                 feat_i.filter(pl.col("_i") != idx)
                                 .drop("_i"), bf, realized)
    assert out["n_skipped_incomplete_slots"] == 1
    assert out["rps"].shape == (3,)
