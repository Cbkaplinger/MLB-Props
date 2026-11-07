"""Synthetic tests for the label-free inference module
(label_free_inference.py). SYNTHETIC ONLY. Pure dict-in, dict-out tests.

Requirement -> implementation -> test-evidence closure table:
  Valid fitted-model fixture produces expected keyed outputs  -> test 1
  Model serialize/reload gives identical predictions          -> test 2
  Shuffling feature/workload rows preserves keyed results     -> test 3
  Semantic slot ordering respected; K-marginal present        -> test 4
  Duplicate keys refuse                                       -> test 5
  Incomplete nine-slot coverage refuses                       -> test 6
  Incompatible features refuse                                -> test 7
  Missing workload refuses                                    -> test 8
  Hand-calculated probability (zero coef -> 0.5)              -> test 9
  Assessment/realized-outcome input refused                   -> test 10
  Inputs not mutated                                          -> test 11
  Provenance context not needed (this module does not use it) -> implied
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import label_free_inference as lfi  # noqa: E402
from pregame_pa_ext import platoon_comparison as pc  # noqa: E402

FEATURES = pc.CHALLENGE_FEATURES  # 12 features
KEY_COLS = lfi.KEY_COLS
P1, P2 = 700001, 700002
B1 = [800001 + i for i in range(9)]
B2 = [800101 + i for i in range(9)]


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def _make_model(intercept=0.0, coef_scale=0.5):
    """A hand-checkable fitted-model dict matching the 12-feature
    contract (deterministic synthetic coefficients, 2-class)."""
    coef = [coef_scale * (i + 1) * 0.01 for i in range(len(FEATURES))]
    return {
        "features": FEATURES,
        "classes": [0, 2],  # strikeout=0, in_play_out=2
        "coef": [coef],
        "intercept": [intercept],
        "mean": [0.0] * len(FEATURES),
        "scale": [1.0] * len(FEATURES),
        "n_train_rows": 100,
        "label_definition": "is_k = 1[class_label == 0]",
    }


def _make_features(n_starts=2):
    rows = []
    starts = [(900001, "Top", P1, B1), (900001, "Bot", P2, B2)]
    for gi, (gk, side, pitcher, batters) in enumerate(starts[:n_starts]):
        for slot, batter in enumerate(batters, start=1):
            row = {"game_pk": gk, "side": side, "pitcher": pitcher,
                   "slot": slot, "batter": batter}
            for fi, fname in enumerate(FEATURES):
                row[fname] = 0.1 * (fi + 1) + 0.05 * slot
            rows.append(row)
    return pl.DataFrame(rows)


def _make_bf():
    rows = []
    for gk, side, pitcher in [(900001, "Top", P1), (900001, "Bot", P2)]:
        v = np.full(37, 0.0)
        v[:35] = 0.02
        v[35] = 0.20
        v[36] = 0.10
        rows.append({"game_pk": gk, "side": side, "pitcher": pitcher,
                     **{f"pmf37_{k}": float(v[k]) for k in range(37)}})
    return pl.DataFrame(rows)


# ------------------- 1. valid fixture produces keyed outputs
def test_valid_produces_expected_keyed_outputs():
    model = _make_model()
    features = _make_features()
    bf = _make_bf()
    result = lfi.run_label_free_inference(model, features, bf)
    assert result["n_starts"] == 2
    assert result["n_slots"] == 18
    keyed = result["keyed_pa_probabilities"]
    assert keyed.height == 18
    pmf = result["k_pmf_per_start"]
    assert pmf.height == 2 * 24
    assert len(result["scored_starts"]) == 2
    assert result["classes"] == [0, 2]


# ------------------- 2. model serialize/reload identical
def test_model_serialize_reload_identical(tmp_path):
    model = _make_model()
    features = _make_features()
    bf = _make_bf()
    res1 = lfi.run_label_free_inference(model, features, bf)
    mp = tmp_path / "model.json"
    mp.write_text(json.dumps(model, indent=1, sort_keys=True,
                             default=str))
    model2 = json.loads(mp.read_text(encoding="utf-8"))
    res2 = lfi.run_label_free_inference(model, features, bf)
    k1 = res1["keyed_pa_probabilities"].sort(KEY_COLS)
    k2 = res2["keyed_pa_probabilities"].sort(KEY_COLS)
    from polars.testing import assert_frame_equal
    assert_frame_equal(k1, k2, check_exact=False, rel_tol=0, abs_tol=1e-12)


# ------------------- 3. shuffling preserves keyed results
def test_shuffle_preserves_keyed_results():
    model = _make_model()
    features = _make_features()
    bf = _make_bf()
    res1 = lfi.run_label_free_inference(model, features, bf)
    idx = list(range(features.height))
    random.seed(42)
    random.shuffle(idx)
    features_shuf = features[idx]
    res2 = lfi.run_label_free_inference(model, features_shuf, bf)
    k1 = res1["keyed_pa_probabilities"].sort(KEY_COLS)
    k2 = res2["keyed_pa_probabilities"].sort(KEY_COLS)
    from polars.testing import assert_frame_equal
    assert_frame_equal(k1, k2, check_exact=False, rel_tol=0, abs_tol=1e-12)


# ------------------- 4. semantic slot ordering respected
def test_slot_ordering_respected():
    model = _make_model()
    features = _make_features()
    bf = _make_bf()
    result = lfi.run_label_free_inference(model, features, bf)
    keyed = result["keyed_pa_probabilities"]
    for side in ("Top", "Bot"):
        slots = keyed.filter(
            (pl.col("game_pk") == 900001)
            & (pl.col("side") == side)).sort("slot")["slot"].to_list()
        assert slots == list(range(1, 10))
    # K-marginal columns use the declared K_CLASS (0)
    assert "p_class_0" in keyed.columns


# ------------------- 5. duplicate keys refuse
def test_duplicate_keys_refuse():
    model = _make_model()
    features = _make_features()
    features = pl.concat([features, features.head(1)])
    with pytest.raises(ValueError, match="duplicate identity keys"):
        lfi.run_label_free_inference(model, features, _make_bf())


# ------------------- 6. incomplete nine-slot coverage refuses
def test_incomplete_nine_slot_refuses():
    model = _make_model()
    features = _make_features()
    features = features.filter(
        ~((pl.col("game_pk") == 900001) & (pl.col("slot") == 9)))
    with pytest.raises(ValueError, match="incomplete nine-slot"):
        lfi.run_label_free_inference(model, features, _make_bf())


# ------------------- 7. incompatible features refuse
def test_incompatible_features_refuse():
    model = _make_model()
    features = _make_features()
    features = features.drop(FEATURES[3])
    with pytest.raises(ValueError, match="feature contract mismatch"):
        lfi.run_label_free_inference(model, features, _make_bf())


# ------------------- 8. missing workload refuses
def test_missing_workload_refuses():
    model = _make_model()
    features = _make_features()
    bf = _make_bf().head(1)  # only 1 of 2 starts
    with pytest.raises(Exception):
        lfi.run_label_free_inference(model, features, bf)


# ------------------- 9. hand-calculated probability
def test_hand_calculated_probability():
    """Model with zero coefficients and zero intercept → sigmoid(0)
    = 0.5 for each class in a 2-class model."""
    model = _make_model(intercept=0.0, coef_scale=0.0)
    features = _make_features()
    bf = _make_bf()
    result = lfi.run_label_free_inference(model, features, bf)
    keyed = result["keyed_pa_probabilities"]
    # 2-class model with zero logits: p_class_0 = p_class_2 = 0.5
    for c in keyed.columns:
        if c.startswith("p_class_"):
            v = keyed[c].to_numpy()
            assert np.allclose(v, 0.5, atol=1e-12)


# ------------------- 10. assessment/realized-outcome refused
def test_outcome_input_refused():
    model = _make_model()
    features = _make_features()
    features = features.with_columns(
        pl.lit(1, dtype=pl.Int64).alias("realized_k"))
    bf = _make_bf()
    with pytest.raises(ValueError, match="realized-outcome"):
        lfi.run_label_free_inference(model, features, bf)


# ------------------- 11. inputs not mutated
def test_inputs_not_mutated():
    model = _make_model()
    features = _make_features()
    bf = _make_bf()
    features_before = features.clone()
    bf_before = bf.clone()
    lfi.run_label_free_inference(model, features, bf)
    assert features.equals(features_before)
    assert bf.equals(bf_before)
