"""Synthetic tests for the label-free prediction orchestration
(label_free_prediction.py). SYNTHETIC ONLY. Frame-in, dict-out tests
through the public entry point. Supersedes the 91ae218 evidence after
Chat 2's probe: the default fixture previously used identical
coefficient rows across classes (feature-independent predictions); the
default model is now feature-sensitive and the degenerate zero-coef
case is a separate arithmetic smoke test.

Requirement -> implementation -> test-evidence closure table:
  Valid requests reach keyed probabilities and K-count PMFs,
  with feature-sensitive (distinct per-class) coefficients   -> test 1
  Same-date label perturbations leave the forecast unchanged
  (semantics-preserving labels; strictly-prior enforced)     -> test 2
  Future pre-R3 label perturbations leave the earlier
  forecast unchanged                                         -> test 3
  A strictly-prior label perturbation changes relevant keyed
  probabilities by a comfortably detectable amount           -> test 4
  Row permutations preserve keyed outputs within declared
  numerical tolerance                                        -> test 5
  Zero-coef uniform probabilities: degenerate arithmetic
  smoke ONLY (not chronology or construction evidence)       -> test 6
  Adapter parity: wrapper output == the registered
  construction seams followed by label-free inference on the
  same synthetic inputs (no numerical re-implementation)     -> test 7
  Contract mismatch refuses                                  -> test 8
  Incomplete lineup coverage refuses                         -> test 9
  R3-partition request dates refuse                          -> test 10

Evidence honesty: these are synthetic-path tests through the public
entry point; they do not validate feature construction against real
registered outputs, and they are not full-suite or private-artifact
validation.
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

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import forecast_states_v2 as fv  # noqa: E402
from pregame_pa_ext import label_free_inference as lfi  # noqa: E402
from pregame_pa_ext import label_free_prediction as lp  # noqa: E402
from pregame_pa_ext import platoon_comparison as pc  # noqa: E402
from pregame_pa_ext import platoon_features as pf  # noqa: E402

FEATURES = pc.CHALLENGE_FEATURES
P1, P2 = 700001, 700002
B1 = [800001 + i for i in range(9)]
B2 = [800101 + i for i in range(9)]
REQ_DATE = date(2025, 5, 1)
KEY = ["game_pk", "side", "pitcher", "slot", "batter"]
PMF_KEY = ["game_pk", "side", "pitcher", "bucket"]

PA_SCHEMA = {
    "game_date": pl.Date, "game_pk": pl.Int64, "pitcher": pl.Int64,
    "batter": pl.Int64, "y": pl.Int64, "stand": pl.Utf8,
    "p_throws": pl.Utf8, "class_label": pl.Int64}


def _row(gd, gk, p, b, y, stand, throws, cls):
    return (gd, gk, p, b, y, stand, throws, cls)


def _label(y, i):
    """Registered bridge semantics: class_label 0 = strikeout (y = 1);
    non-K rows map to distinct non-K classes."""
    return 0 if y == 1 else 1 + (i % 3)


def _relabel_from_y(frame: pl.DataFrame) -> pl.DataFrame:
    """Flip y (y -> 1 - y) and re-derive class_label with the fixture's
    declared mapping, so y = 1 iff class_label = 0 stays consistent."""
    flipped = frame.with_columns(pl.col("y").sub(1).abs().alias("y"))
    idx = flipped.with_row_index("__i__")
    idx = idx.with_columns(
        pl.when(pl.col("y") == 1).then(pl.lit(0))
        .otherwise(1 + (pl.col("__i__") % 3))
        .cast(pl.Int64).alias("class_label"))
    return idx.drop("__i__")


def _pa_rows():
    rows = []
    # 2023 history (strictly before every later cutoff)
    h23 = date(2023, 5, 10)
    for i, b in enumerate(B1):
        rows.append(_row(h23, 40, P1, b, 0, "L", "R", 0))
    for i, b in enumerate(B2):
        rows.append(_row(h23, 40, P2, b, 0, "R", "L", 1 + (i % 3)))
    # 2024 training rows (strictly prior to the 2025-05-01 cutoff)
    d24 = date(2024, 5, 10)
    for i, b in enumerate(B1):
        y = 1 if i % 2 == 0 else 0
        rows.append(_row(d24, 41, P1, b, y, "L", "R", _label(y, i)))
    for i, b in enumerate(B2):
        y = 1 if i % 3 == 0 else 0
        rows.append(_row(d24, 41, P2, b, y, "R", "L", _label(y, i)))
    # 2025-05-01 score-window rows (SAME DATE as the request cutoff)
    for i, b in enumerate(B1):
        y = 1 if i % 2 == 0 else 0
        rows.append(_row(REQ_DATE, 900201, P1, b, y, "L", "R",
                         _label(y, i)))
    for i, b in enumerate(B2):
        y = 1 if i % 2 else 0
        rows.append(_row(REQ_DATE, 900201, P2, b, y, "R", "L",
                         _label(y, i)))
    # 2025-06-15 rows (future relative to the request cutoff, still
    # before the R3 boundary)
    f15 = date(2025, 6, 15)
    for i, b in enumerate(B1[:3]):
        rows.append(_row(f15, 900301, P1, b, 0, "L", "R", 1))
    return rows


def _pa_frame():
    return pl.DataFrame(_pa_rows(), schema=PA_SCHEMA, orient="row")


def _lineups():
    rows = [(900201, "Top", P1, REQ_DATE, True, *B1),
            (900201, "Bot", P2, REQ_DATE, True, *B2)]
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{s}": pl.Int64 for s in range(1, 10)})
    return pl.DataFrame(rows, schema=schema, orient="row")


def _make_model():
    """Deterministic feature-sensitive model: DISTINCT per-class
    coefficient rows so features affect relative logits (identical
    rows would be a common shift that cancels in the softmax)."""
    n = len(FEATURES)
    return {
        "features": FEATURES,
        "classes": [0, 1, 2, 3],
        "coef": [[round(0.011 * (c + 1) * (j + 2), 6) for j in range(n)]
                 for c in range(4)],
        "intercept": [-0.30, -0.10, 0.10, 0.30],
        "mean": [0.0] * n,
        "scale": [1.0] * n,
    }


def _make_bf():
    v = np.full(37, 0.0)
    v[:35] = 0.02
    v[35] = 0.20
    v[36] = 0.10  # sums to 1.0
    rows = [{"game_pk": 900201, "side": side, "pitcher": pitcher,
             **{f"pmf37_{k}": float(v[k]) for k in range(37)}}
            for side, pitcher in (("Top", P1), ("Bot", P2))]
    return pl.DataFrame(rows)


def _prob_cols(keyed):
    return [c for c in keyed.columns if c.startswith("p_class_")]


def _keyed(res):
    return res["keyed_pa_probabilities"].sort(KEY)


def _pmf(res):
    return res["k_pmf_per_start"].sort(PMF_KEY)


# ------------- 1. valid requests produce keyed, feature-sensitive outputs
def test_valid_requests_produce_keyed_outputs():
    result = lp.run_prediction(_make_model(), _pa_frame(), _lineups(),
                               _make_bf())
    assert result["n_starts"] == 2
    assert result["n_slots"] == 18
    keyed = result["keyed_pa_probabilities"]
    assert keyed.height == 18
    assert len(result["scored_starts"]) == 2
    cols = _prob_cols(keyed)
    assert len(cols) == 4
    vals = keyed.select(cols).to_numpy()
    assert np.all(np.isfinite(vals))
    assert np.all(vals >= 0.0)
    sums = keyed.select(pl.sum_horizontal(cols).alias("s"))["s"]
    assert np.allclose(sums.to_numpy(), 1.0, atol=1e-9)
    # the fixture model is feature-sensitive: predictions must not
    # collapse to a uniform/degenerate constant across classes
    assert np.ptp(vals, axis=1).max() > 1e-9
    pmf = result["k_pmf_per_start"]
    assert pmf.height == 2 * 24
    tot = pmf.group_by("game_pk", "side", "pitcher").agg(
        s=pl.col("pmf_h3_raw").sum())
    assert np.allclose(tot["s"].to_numpy(), 1.0, atol=1e-9)


# --------- 2. same-date label perturbation cannot enter the cutoff
def test_same_date_labels_cannot_enter_cutoff():
    model = _make_model()
    pa = _pa_frame()
    bf = _make_bf()
    res1 = lp.run_prediction(model, pa, _lineups(), bf)
    mask = pl.col("game_date") == REQ_DATE
    perturbed = _relabel_from_y(pa.filter(mask))
    res2 = lp.run_prediction(model,
                             pl.concat([pa.filter(~mask), perturbed]),
                             _lineups(), bf)
    assert_frame_equal(_keyed(res1), _keyed(res2),
                       check_exact=False, abs_tol=1e-12)
    assert_frame_equal(_pmf(res1), _pmf(res2),
                       check_exact=False, abs_tol=1e-12)


# --------- 3. future pre-R3 label perturbation cannot enter earlier cutoff
def test_future_pre_r3_labels_cannot_enter_earlier_cutoff():
    model = _make_model()
    pa = _pa_frame()
    bf = _make_bf()
    res1 = lp.run_prediction(model, pa, _lineups(), bf)
    # rows dated 2025-06-15: after the 2025-05-01 request cutoff,
    # still before the R3 boundary
    fmask = pl.col("game_date") == date(2025, 6, 15)
    perturbed = _relabel_from_y(pa.filter(fmask))
    res2 = lp.run_prediction(model,
                             pl.concat([pa.filter(~fmask), perturbed]),
                             _lineups(), bf)
    assert_frame_equal(_keyed(res1), _keyed(res2),
                       check_exact=False, abs_tol=1e-12)
    assert_frame_equal(_pmf(res1), _pmf(res2),
                       check_exact=False, abs_tol=1e-12)


# ---- 4. strictly-prior label perturbation MUST move keyed probabilities
def test_strictly_prior_perturbation_changes_probabilities():
    model = _make_model()
    pa = _pa_frame()
    bf = _make_bf()
    res1 = lp.run_prediction(model, pa, _lineups(), bf)
    # perturb the 2024-05-10 training rows (strictly prior to the
    # 2025-05-01 cutoff); the declared y/class_label semantics hold
    pmask = pl.col("game_date") == date(2024, 5, 10)
    perturbed = _relabel_from_y(pa.filter(pmask))
    res2 = lp.run_prediction(model,
                             pl.concat([pa.filter(~pmask), perturbed]),
                             _lineups(), bf)
    cols = _prob_cols(_keyed(res1))
    diff = (_keyed(res1).select(cols).to_numpy()
            - _keyed(res2).select(cols).to_numpy())
    max_diff = float(np.abs(diff).max())
    assert max_diff > 1e-6, (
        f"strictly-prior perturbation moved keyed probabilities by only "
        f"{max_diff}; feature sensitivity not exercised")


# --------- 5. row permutations preserve keyed outputs (declared tolerance)
def test_row_permutation_invariance():
    model = _make_model()
    bf = _make_bf()
    lineups = _lineups()
    res1 = lp.run_prediction(model, _pa_frame(), lineups, bf)
    pa_shuf = _pa_frame().sample(fraction=1.0, shuffle=True, seed=7)
    bf_shuf = bf.sample(fraction=1.0, shuffle=True, seed=11)
    res2 = lp.run_prediction(model, pa_shuf, lineups, bf_shuf)
    assert_frame_equal(_keyed(res1), _keyed(res2),
                       check_exact=False, abs_tol=1e-12)
    assert_frame_equal(_pmf(res1), _pmf(res2),
                       check_exact=False, abs_tol=1e-12)


# ---- 6. degenerate zero-coef arithmetic smoke (NOT chronology evidence)
def test_zero_coef_uniform_smoke():
    model = _make_model()
    model["coef"] = [np.zeros(len(FEATURES)) for _ in range(4)]
    model["intercept"] = [0.0, 0.0, 0.0, 0.0]
    result = lp.run_prediction(model, _pa_frame(), _lineups(),
                               _make_bf())
    keyed = result["keyed_pa_probabilities"]
    cols = [c for c in keyed.columns if c.startswith("p_class_")]
    # softmax with identical logits -> 0.25 per class, for any inputs
    for c in cols:
        assert np.allclose(keyed[c].to_numpy(), 0.25, atol=1e-12)


# ---- 7. adapter parity: wrapper == registered seams + inference
def test_adapter_parity_with_registered_seams():
    model = _make_model()
    pa = _pa_frame()
    bf = _make_bf()
    lineups = _lineups()
    res = lp.run_prediction(model, pa, lineups, bf)

    # re-wire the SAME public construction functions (no parallel math)
    pa_ok = pa.filter(pl.col("game_date") < pl.lit(lp.R3_START))
    long, _ = ad.projected_long(lineups)
    req_dates = sorted(long["game_date"].unique().to_list())
    p_v2, b_v2, lg_v2, _ = fv.build_v2_states(pa_ok, req_dates)
    feat = ad.attach_prior_features(
        long.select("game_date", "pitcher", "batter", "game_pk",
                    "side", "slot"), p_v2, b_v2, lg_v2)
    rates = pf.build_split_class_rates(pa_ok, req_dates,
                                       alpha=pc.ALPHA, n_classes=4)
    hands = pf.forecast_matchup_hands(
        pa_ok, feat.select(pl.col("batter"), pl.col("pitcher"),
                           pl.col("game_date").alias("cutoff")))
    feat = (feat.join(hands.select("batter", "pitcher", "cutoff",
                                   "f_stand", "f_hand"),
                      left_on=["batter", "pitcher", "game_date"],
                      right_on=["batter", "pitcher", "cutoff"],
                      how="left")
            .with_columns(pl.col("game_date").alias("cutoff"),
                          pl.col("f_stand").alias("stand"),
                          pl.col("f_hand").alias("p_throws"))
            .drop(["f_stand", "f_hand"]))
    feat = pf.attach_platoon_features(feat, rates, n_classes=4)
    feat = feat.select(lfi.KEY_COLS + list(model["features"]))
    expected = lfi.run_label_free_inference(model, feat, bf)

    assert_frame_equal(_keyed(res), _keyed(expected),
                       check_exact=False, abs_tol=1e-12)
    assert_frame_equal(_pmf(res), _pmf(expected),
                       check_exact=False, abs_tol=1e-12)


# ------------------- 8. contract mismatches fail explicitly
def test_model_contract_mismatch_refuses():
    bad = _make_model()
    bad["features"] = FEATURES[:-1]
    with pytest.raises(ValueError, match="12-feature"):
        lp.run_prediction(bad, _pa_frame(), _lineups(), _make_bf())


# ------------------- 9. incomplete lineup coverage refuses
def test_incomplete_lineup_coverage_refuses():
    lineups = _lineups().with_columns(
        pl.when(pl.col("pitcher") == P2)
        .then(pl.lit(None))
        .otherwise(pl.col("u_slot_9"))
        .alias("u_slot_9"))
    with pytest.raises(ValueError, match="uncovered slot"):
        lp.run_prediction(_make_model(), _pa_frame(), lineups,
                          _make_bf())


# ------------------- 10. R3-partition request dates refuse
def test_r3_request_dates_refuse():
    lineups = _lineups().with_columns(
        pl.lit(date(2025, 7, 2)).alias("game_date"))
    with pytest.raises(ValueError, match="R3"):
        lp.run_prediction(_make_model(), _pa_frame(), lineups,
                          _make_bf())
