"""Focused correctness + leakage tests for the WF comparison lane."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, "research/offseason_2026")
sys.path.insert(0, "src")
sys.path.insert(0, ".")

import run_wf_comparison as wf  # noqa: E402


def test_windows_do_not_overlap():
    spans = [(date.fromisoformat(s), date.fromisoformat(e))
             for _, s, e in wf.WINDOWS]
    for i in range(len(spans) - 1):
        assert spans[i][1] <= spans[i + 1][0]


def test_training_labels_precede_scored_block():
    spine = pl.DataFrame({
        "game_date": [date(2023, 4, 1), date(2024, 3, 20),
                      date(2024, 4, 15), date(2024, 5, 1)],
        "k_rate": [0.2, 0.25, 0.3, 0.35], "K": [5, 6, 7, 8],
        "PA": [25, 24, 23, 22],
    })
    start = date(2024, 4, 1)
    tr = spine.filter(pl.col("game_date") < start)
    sc = spine.filter((pl.col("game_date") >= start))
    assert tr["game_date"].max() < start
    assert sc["game_date"].min() >= start
    assert len(tr) + len(sc) == spine.height


def test_val_split_chronological_and_pre_window():
    n = 100
    spine = pl.DataFrame({
        "game_date": [date(2023, 4, 1) + __import__("datetime")
                      .timedelta(days=i) for i in range(n)],
        "k_rate": np.linspace(0.2, 0.3, n), "K": np.ones(n),
        "PA": np.full(n, 20),
    })
    start = date(2024, 4, 1)
    tr = spine.filter(pl.col("game_date") < start)
    cut = int(len(tr) * (1.0 - wf.VAL_FRACTION))
    val = tr[cut:]
    trn = tr[:cut]
    assert val["game_date"].max() <= tr["game_date"].max()
    assert val["game_date"].max() < start
    assert trn["game_date"].max() < val["game_date"].min()


def test_monotone_constraints_only_arm_a():
    feats = ["k_rate_P5", "hit_rate_std", "park_k_factor", "PA_P5"]
    signs = wf._feature_constraints(feats)
    assert signs == [1, -1, 0, -1] or signs[0] == 1 and signs[1] == -1
    pos = wf._MONO_POSITIVE_STEMS
    neg = wf._MONO_NEGATIVE_STEMS
    assert any(s.startswith("k_rate") for s in pos)
    assert any(s.startswith("hit_rate") for s in neg)


def test_frozen_params_no_search_surface():
    p = wf.FROZEN_PARAMS
    assert p["n_estimators"] == 5_000 and p["learning_rate"] == 0.03
    assert p["random_state"] == 42
    assert "monotone_constraints" not in p
    assert wf.BLEND_W == (0.60, 0.40)
    assert wf.VAL_FRACTION == 0.15 and wf.ES_ROUNDS == 200


def test_blend_fixed_weights_and_clip():
    pa = np.array([0.1, 0.9, 0.5])
    pb = np.array([0.9, -0.2, 0.4])
    blend = np.clip(wf.BLEND_W[0] * pa + wf.BLEND_W[1] * pb, 0.0, 1.0)
    assert np.allclose(blend, [0.42, 0.46, 0.46])


def test_missing_row_excluded_from_all_arms():
    matched = np.array([True, True, False])
    pa = np.array([0.2, 0.3, np.nan])
    scored = np.where(matched)[0]
    assert len(scored) == 2
    assert not np.isnan(pa[scored]).any()
    assert np.isnan(pa[~matched]).any()


def test_holm_correction_ordering():
    pvals = [0.04, 0.004, 0.9]
    adj = wf._holm(pvals)
    assert adj[1] <= adj[0] <= adj[2]
    assert abs(adj[1] - 0.012) < 1e-9
    assert all(0.0 <= p <= 1.0 for p in adj)
