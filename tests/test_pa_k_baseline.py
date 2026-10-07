"""Synthetic readiness tests for the PA-K baseline (no real data, no scoring).

Frozen draft: research/offseason_2026/pa-k-baseline-prereg-draft.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import pa_k_baseline as pak  # noqa: E402
from datetime import date  # noqa: E402


def pa_frame(rows):
    """rows: (game_pk, game_date, pitcher, batter, at_bat, event,
    stand, p_throws)."""
    return pl.DataFrame({
        "game_pk": [r[0] for r in rows],
        "game_date": [r[1] for r in rows],
        "pitcher": [r[2] for r in rows],
        "batter": [r[3] for r in rows],
        "at_bat_number": [r[4] for r in rows],
        "events": [r[5] for r in rows],
        "stand": [r[6] for r in rows],
        "p_throws": [r[7] for r in rows],
    })


def keys_frame(pairs):
    return pl.DataFrame({"game_pk": [k[0] for k in pairs],
                         "pitcher": [k[1] for k in pairs]})


D1, D2, D3 = date(2023, 4, 1), date(2023, 4, 2), date(2023, 4, 3)


def test_identity_uniqueness_fails_loud():
    rows = [
        (1, D1, 10, 20, 5, "strikeout", "L", "R"),
        (1, D1, 10, 21, 5, "field_out", "R", "R"),  # duplicate PA id
    ]
    with pytest.raises(ValueError):
        pak.build_pa_table(pa_frame(rows), pa_frame([]))


def test_target_mapping_and_truncated_exclusion():
    rows = [
        (1, D1, 10, 20, 1, "strikeout", "L", "R"),
        (1, D1, 10, 21, 2, "strikeout_double_play", "R", "R"),
        (1, D1, 10, 22, 3, "walk", "L", "R"),
        (1, D1, 10, 23, 4, "single", "R", "R"),
        (1, D1, 10, 24, 5, "truncated_pa", "L", "R"),
        (2, D1, 11, 25, 1, "home_run", "R", "L"),  # not a first pitcher
    ]
    keys = keys_frame([(1, 10)])
    out = pak.build_pa_table(pa_frame(rows), keys)
    assert out.height == 4  # truncated_pa excluded, non-fp game excluded
    assert sorted(out["y"].to_list()) == [0, 0, 1, 1]
    assert out["n_truncated_excluded"][0] == 1


def test_leakage_same_date_and_future_perturbation():
    # training rows: pitcher 10 excellent (all K); eval on D3
    rows = [((i % 2) + 1, date(2023, 3, 1 + i % 20), 10, 20 + i % 5,
             i + 1, "strikeout", "L", "R") for i in range(40)]
    rows += [((i % 2) + 1, date(2023, 3, 1 + i % 20), 11, 25 + i % 5,
              100 + i + 1, "single", "R", "R") for i in range(40)]
    train = pak.build_pa_table(pa_frame(rows), keys_frame([(1, 10), (2, 11)]))
    eval_rows = [(1, D3, 10, 20, 1, "field_out", "L", "R"),
                 (2, D3, 11, 21, 1, "field_out", "R", "R")]
    ev = pak.build_pa_table(pa_frame(eval_rows), keys_frame([(1, 10), (2, 11)]))
    pA1, _, _ = pak.arm_a_probs(ev, train, D3)
    # perturb a FUTURE (D3) outcome in train -> features must not change
    train_mut = train.with_columns(
        pl.when(pl.col("game_date") == D3)
        .then(pl.lit("strikeout")).otherwise(pl.col("events"))
        .alias("events"))
    train_mut = train_mut.with_columns(
        pl.col("events").is_in(list(pak.K_EVENTS)).cast(pl.Int8).alias("y"))
    pA2, _, _ = pak.arm_a_probs(ev, train_mut, D3)
    assert np.abs(pA1 - pA2).max() == 0.0
    # same-date eval rows are never in the as-of training set anyway
    assert pA1[0] > pA1[1]  # good pitcher ranked above bad


def test_cold_start_falls_back_to_league_rate():
    rows = [((i % 2) + 1, D1, 10, 20 + i % 4, i + 1,
             "strikeout" if i % 2 else "single", "L", "R")
            for i in range(40)]
    train = pak.build_pa_table(pa_frame(rows),
                               keys_frame([(1, 10), (2, 10)]))
    ev = pak.build_pa_table(
        pa_frame([(1, D2, 99, 999, 1, "field_out", "L", "R")]),
        keys_frame([(1, 99)]))
    pA, lg, (n_p, n_b) = pak.arm_a_probs(ev, train, D2)
    assert n_p[0] == 0 and n_b[0] == 0  # cold start flagged by prior_n=0
    assert abs(pA[0] - lg) < 1e-9  # log5 identity: p_p=p_b=lg -> lg


def test_log5_identity_pin():
    lg = 0.22
    z = pak._logit(0.30) + pak._logit(0.25) - pak._logit(lg)
    p = pak._sigmoid(z)
    # log5 consistency: odds_p * odds_b / odds_lg
    odds = (0.30 / 0.70) * (0.25 / 0.75) / (lg / (1 - lg))
    assert abs(p - odds / (1 + odds)) < 1e-12


def test_clipping_and_scores():
    p = np.array([0.0, 1.0, 0.5])
    y = np.array([1, 0, 1])
    ll = pak.logloss(p, y)
    assert np.isfinite(ll).all()
    assert ll[0] > -np.log(pak.CLIP_LO) - 1e-6
    br = pak.brier(p, y)
    assert br[0] == pytest.approx(1.0) and br[2] == pytest.approx(0.25)


def test_arm_b_learns_separable_signal():
    # pitcher 10 = 60% K, pitcher 11 = 10% K over many train rows
    rng = np.random.default_rng(3)
    rows = []
    for i in range(600):
        pit = 10 if i % 2 == 0 else 11
        ev = "strikeout" if rng.random() < (0.6 if pit == 10 else 0.1) \
            else "single"
        rows.append(((i % 2) + 1, date(2023, 3, 1 + i % 25), pit,
                     20 + i % 40, i + 1, ev, "L", "R"))
    train = pak.build_pa_table(pa_frame(rows), keys_frame([(1, 10), (2, 11)]))
    ev = pak.build_pa_table(
        pa_frame([(1, date(2023, 4, 1), 10, 20, 1, "single", "L", "R"),
                  (2, date(2023, 4, 1), 11, 21, 1, "single", "L", "R")]),
        keys_frame([(1, 10), (2, 11)]))
    pA, _, _ = pak.arm_a_probs(ev, train, date(2023, 4, 1))
    pB, _ = pak.arm_b_probs(ev, train, date(2023, 4, 1))
    assert pA[0] > pA[1] and pB[0] > pB[1]
    assert pB[0] > 0.35 and pB[1] < 0.30  # logistic learns the rates


def test_row_parity_and_feature_shapes():
    rng = np.random.default_rng(7)
    rows = [((i % 2) + 1, date(2023, 3, 1 + i % 10), 10 + i % 2,
             20 + i % 6, i + 1,
             "strikeout" if rng.random() < 0.3 else "single", "L", "R")
            for i in range(200)]
    train = pak.build_pa_table(pa_frame(rows),
                               keys_frame([(1, 10), (2, 11)]))
    ev = train.head(20)
    X = pak.arm_b_features(ev, train, date(2023, 4, 1))
    assert X.shape == (20, len(pak.FEATURES))
    pA, _, _ = pak.arm_a_probs(ev, train, date(2023, 4, 1))
    assert len(pA) == 20
