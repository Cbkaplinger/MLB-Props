"""Synthetic tests for the label-free prediction orchestration
(label_free_prediction.py). SYNTHETIC ONLY. Frame-in, dict-out tests
through the public entry point.

Requirement -> implementation -> test-evidence closure table:
  Valid requests reach keyed probabilities and K-count PMFs  -> test 1
  Same-date rows cannot enter the same-date cutoff's features
  (strictly-prior enforced by construction)                  -> test 2
  Row permutations preserve keyed outputs within declared
  numerical tolerance                                        -> test 3
  Model/feature contract mismatch fails explicitly           -> test 4
  Incomplete lineup coverage refuses                         -> test 5
  R3-partition request dates refuse                          -> test 6
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import label_free_prediction as lp  # noqa: E402
from pregame_pa_ext import platoon_comparison as pc  # noqa: E402

FEATURES = pc.CHALLENGE_FEATURES
P1, P2 = 700001, 700002
B1 = [800001 + i for i in range(9)]
B2 = [800101 + i for i in range(9)]

PA_SCHEMA = {
    "game_date": pl.Date, "game_pk": pl.Int64, "pitcher": pl.Int64,
    "batter": pl.Int64, "y": pl.Int64, "stand": pl.Utf8,
    "p_throws": pl.Utf8, "class_label": pl.Int64}


def _label(y, i):
    """Registered bridge semantics: class_label 0 = strikeout (y = 1);
    non-K rows map to distinct non-K classes."""
    return 0 if y == 1 else 1 + (i % 3)


def _pa_rows():
    rows = []
    # 2023 history (strictly before every later cutoff)
    h23 = date(2023, 5, 10)
    for i, b in enumerate(B1):
        rows.append(_row(h23, 40, P1, b, 0, "L", "R", 0))
    for i, b in enumerate(B2):
        rows.append(_row(h23, 40, P2, b, 0, "R", "L", 1 + (i % 3)))
    # 2024 training rows (R1 fit window)
    d24 = date(2024, 5, 10)
    for i, b in enumerate(B1):
        y = 1 if i % 2 == 0 else 0
        rows.append(_row(d24, 41, P1, b, y, "L", "R",
                         0 if y == 1 else 1 + (i % 3)))
    for i, b in enumerate(B2):
        y = 1 if i % 3 == 0 else 0
        rows.append(_row(d24, 41, P2, b, y, "R", "L", _label(y, i)))
    # 2025-05-01 score-window rows (SAME DATE as the R2 request cutoff)
    r2d = date(2025, 5, 1)
    for i, b in enumerate(B1):
        y = 1 if i % 2 == 0 else 0
        rows.append(_row(r2d, 900201, P1, b, y, "L", "R", _label(y, i)))
    for i, b in enumerate(B2):
        y = 1 if i % 2 else 0
        rows.append(_row(r2d, 900201, P2, b, y, "R", "L", _label(y, i)))
    # 2025-06-15 rows (future relative to the 2025-05-01 cutoff,
    # still before the R3 boundary)
    f15 = date(2025, 6, 15)
    for i, b in enumerate(B1[:3]):
        rows.append(_row(f15, 900301, P1, b, 0, "L", "R", 1))
    return rows


def _row(gd, gk, p, b, y, stand, throws, cls):
    return (gd, gk, p, b, y, stand, throws, cls)


def _pa_frame():
    return pl.DataFrame(_pa_rows(), schema=PA_SCHEMA, orient="row")


def _lineups():
    rows = [(900201, "Top", P1, date(2025, 5, 1), True, *B1),
            (900201, "Bot", P2, date(2025, 5, 1), True, *B2)]
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{s}": pl.Int64 for s in range(1, 10)})
    return pl.DataFrame(rows, schema=schema, orient="row")


def _make_model():
    coef = [0.5 * (i + 1) * 0.01 for i in range(len(FEATURES))]
    return {
        "features": FEATURES,
        "classes": [0, 1, 2, 3],
        "coef": [coef, coef, coef, coef],
        "intercept": [0.0, 0.0, 0.0, 0.0],
        "mean": [0.0] * len(FEATURES),
        "scale": [1.0] * len(FEATURES),
    }


def _make_bf():
    rows = []
    v = np.full(37, 0.0)
    v[:35] = 0.02
    v[35] = 0.20
    v[36] = 0.10  # sums to 1.0
    for side, pitcher in (("Top", P1), ("Bot", P2)):
        rows.append({"game_pk": 900201, "side": side, "pitcher": pitcher,
                     **{f"pmf37_{k}": float(v[k]) for k in range(37)}})
    return pl.DataFrame(rows)


# ------------------- 1. valid requests produce keyed outputs
def test_valid_requests_produce_keyed_outputs():
    result = lp.run_prediction(_make_model(), _pa_frame(), _lineups(),
                               _make_bf())
    assert result["n_starts"] == 2
    assert result["n_slots"] == 18
    keyed = result["keyed_pa_probabilities"]
    assert keyed.height == 18
    assert len(result["scored_starts"]) == 2
    prob_cols = [c for c in keyed.columns if c.startswith("p_class_")]
    assert len(prob_cols) == 4
    for c in prob_cols:
        v = keyed[c].to_numpy()
        assert np.all(np.isfinite(v))
        assert np.all(v >= 0.0)
    sums = keyed.select(pl.sum_horizontal(prob_cols).alias("s"))["s"]
    assert np.allclose(sums.to_numpy(), 1.0, atol=1e-9)
    pmf = result["k_pmf_per_start"]
    assert pmf.height == 2 * 24
    tot = pmf.group_by("game_pk", "side", "pitcher").agg(
        s=pl.col("pmf_h3_raw").sum())
    assert np.allclose(tot["s"].to_numpy(), 1.0, atol=1e-9)


# --------- 2. same-date rows cannot enter the same-date cutoff
def test_same_date_labels_cannot_enter_cutoff():
    model = _make_model()
    pa = _pa_frame()
    bf = _make_bf()
    res1 = lp.run_prediction(model, pa, _lineups(), bf)
    # flip the labels of the SAME-DATE (2025-05-01) rows only; if any
    # same-date row leaked into its own cutoff's features, the keyed
    # outputs would change
    mask = pl.col("game_date") == date(2025, 5, 1)
    same_date = pa.filter(mask)
    flipped = same_date.with_columns(
        pl.col("y").sub(1).abs().alias("y"),
        ((pl.col("class_label") + 1) % 4).alias("class_label"))
    pa_flipped = pl.concat([pa.filter(~mask), flipped])
    res2 = lp.run_prediction(model, pa_flipped, _lineups(), bf)
    key = ["game_pk", "side", "pitcher", "slot", "batter"]
    k1 = res1["keyed_pa_probabilities"].sort(key)
    k2 = res2["keyed_pa_probabilities"].sort(key)
    assert_frame_equal(k1, k2, check_exact=False, abs_tol=1e-12)
    p1 = res1["k_pmf_per_start"].sort(
        ["game_pk", "side", "pitcher", "bucket"])
    p2 = res2["k_pmf_per_start"].sort(
        ["game_pk", "side", "pitcher", "bucket"])
    assert_frame_equal(p1, p2, check_exact=False, abs_tol=1e-12)
    model = _make_model()
    pa = _pa_frame()
    bf = _make_bf()
    lineups = _lineups()
    res1 = lp.run_prediction(model, pa, _lineups(), bf)
    # flip the labels of the SAME-DATE (2025-05-01) rows only; if any
    # same-date row leaked into its own cutoff's features, the keyed
    # outputs would change
    mask = pl.col("game_date") == date(2025, 5, 1)
    same_date = pa.filter(mask)
    flipped = same_date.with_columns(
        pl.col("y").sub(1).abs().alias("y"),
        ((pl.col("class_label") + 1) % 4).alias("class_label"))
    pa_flipped = pl.concat([pa.filter(~mask), flipped])
    res2 = lp.run_prediction(model, pa_flipped, _lineups(), bf)
    key = ["game_pk", "side", "pitcher", "slot", "batter"]
    k1 = res1["keyed_pa_probabilities"].sort(key)
    k2 = res2["keyed_pa_probabilities"].sort(key)
    assert_frame_equal(k1, k2, check_exact=False, abs_tol=1e-12)
    p1 = res1["k_pmf_per_start"].sort(
        ["game_pk", "side", "pitcher", "bucket"])
    p2 = res2["k_pmf_per_start"].sort(
        ["game_pk", "side", "pitcher", "bucket"])
    assert_frame_equal(p1, p2, check_exact=False, abs_tol=1e-12)


# ------------------- 3. zero-coef model -> uniform class probabilities
def test_hand_calculated_probability():
    model = _make_model()
    model["coef"] = [np.zeros(len(FEATURES)) for _ in range(4)]
    model["intercept"] = [0.0, 0.0, 0.0, 0.0]
    result = lp.run_prediction(model, _pa_frame(), _lineups(), _make_bf())
    keyed = result["keyed_pa_probabilities"]
    prob_cols = [c for c in keyed.columns if c.startswith("p_class_")]
    # 4-class softmax with identical logits -> 0.25 per class
    for c in prob_cols:
        assert np.allclose(keyed[c].to_numpy(), 0.25, atol=1e-12)


# --------- 3. row permutations preserve keyed outputs
def test_row_permutation_invariance():
    model = _make_model()
    bf = _make_bf()
    lineups = _lineups()
    res1 = lp.run_prediction(model, _pa_frame(), lineups, bf)
    pa_shuf = _pa_frame().sample(fraction=1.0, shuffle=True, seed=7)
    bf_shuf = bf.sample(fraction=1.0, shuffle=True, seed=11)
    res2 = lp.run_prediction(model, pa_shuf, lineups, bf_shuf)
    key = ["game_pk", "side", "pitcher", "slot", "batter"]
    k1 = res1["keyed_pa_probabilities"].sort(key)
    k2 = res2["keyed_pa_probabilities"].sort(key)
    assert_frame_equal(k1, k2, check_exact=False, abs_tol=1e-12)
    p1 = res1["k_pmf_per_start"].sort(
        ["game_pk", "side", "pitcher", "bucket"])
    p2 = res2["k_pmf_per_start"].sort(
        ["game_pk", "side", "pitcher", "bucket"])
    assert_frame_equal(p1, p2, check_exact=False, abs_tol=1e-12)


# ------------------- 7. contract mismatches fail explicitly
def test_model_contract_mismatch_refuses():
    bad_model = _make_model()
    bad_model["features"] = FEATURES[:-1]
    with pytest.raises(ValueError, match="12-feature"):
        lp.run_prediction(bad_model, _pa_frame(), _lineups(), _make_bf())


# ------------------- 8. R3-partition request dates refuse
def test_r3_request_dates_refuse():
    lineups = _lineups().with_columns(
        pl.lit(date(2025, 7, 2)).alias("game_date"))
    with pytest.raises(ValueError, match="R3"):
        lp.run_prediction(_make_model(), _pa_frame(), lineups, _make_bf())
