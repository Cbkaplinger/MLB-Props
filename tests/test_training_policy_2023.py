"""Synthetic readiness tests for the BF training-policy comparison.

Frozen prereg: research/offseason_2026/expanding-training-prereg.md
(sha af2f4bf2...). All tests inject synthetic frames only - no real
data, no scored execution.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import bf_distribution as bfd  # noqa: E402
import run_training_policy_2023 as rtp  # noqa: E402
from run_corrected_history_2023 import CHALLENGER_FEATURES  # noqa: E402

FEATS = list(CHALLENGER_FEATURES)


def synth_frame(rows, origin=None):
    """rows: list of (date_iso, PA). origin: value for the origin col."""
    return pd.DataFrame({
        "game_pk": [1000 + i for i in range(len(rows))],
        "pitcher": [500 + i for i in range(len(rows))],
        "game_date": pd.to_datetime([r[0] for r in rows]),
        "PA": [r[1] for r in rows],
        "origin": [origin] * len(rows),
        **{f: np.linspace(0.0, 1.0, len(rows)) + i * 0.01
           for i, f in enumerate(FEATS)},
    })


def train_synth(n=60, short=3, seed=1):
    rng = np.random.default_rng(seed)
    return synth_frame(
        [("2023-03-%02d" % (1 + i % 30), int(rng.integers(9, 33))
          if i >= short else int(rng.integers(3, 8)))
         for i in range(n)])


def test_train_masks_boundary_and_exclusion():
    assigned = pd.concat([
        synth_frame([("2023-04-01", 20), ("2023-04-14", 21)]),          # train
        synth_frame([("2023-06-30", 22)], origin="2023-04-15"),         # Apr eval
        synth_frame([("2023-07-01", 23)], origin="2023-07-01"),         # Jul eval
    ], ignore_index=True)
    ts_jul = pd.Timestamp("2023-07-01")
    mB = rtp.train_mask_B(assigned, ts_jul)
    assert mB.sum() == 3  # 04-01, 04-14, 06-30 (Apr eval row included)
    assert "2023-06-30" in assigned[mB]["game_date"].astype(str).tolist()
    assert "2023-07-01" not in assigned[mB]["game_date"].astype(str).tolist()
    mA = rtp.train_mask_A(assigned, ts_jul)
    assert mA.sum() == 2  # frozen pre-04-15 only


def test_per_arm_preprocess_fitted_on_own_rows():
    t1 = train_synth(n=60, seed=1)
    t2 = train_synth(n=60, seed=2)
    # feature values differ between frames so stats must too
    t2[FEATS] = t2[FEATS].to_numpy() + 0.25
    b1 = rtp.fit_arm(t1)
    b2 = rtp.fit_arm(t2)
    m1 = b1["preprocess"]["medians"]
    m2 = b2["preprocess"]["medians"]
    assert not np.allclose(m1, m2)
    # b1's stats reproduce b1's own standardized data
    std = bfd._apply_preprocess(b1["preprocess"],
                                t1[FEATS].to_numpy(dtype=float))
    assert np.abs(std.mean(axis=0)).max() < 1e-8


def test_april_arms_coincide_on_identical_inputs():
    t = train_synth(n=60, seed=5)
    ev = synth_frame([("2023-04-20", 18), ("2023-04-25", 24)])
    bA = rtp.fit_arm(t)
    bB = rtp.fit_arm(t)  # identical inputs -> must be identical
    f = ev[FEATS].to_numpy(dtype=float)
    assert np.abs(rtp.batch_predict(bA, f)
                  - rtp.batch_predict(bB, f)).max() <= 1e-12


def test_training_mutation_changes_only_own_arm():
    tA = train_synth(n=60, seed=9)
    tB = tA.copy()
    tB.loc[0, "PA"] = 3  # mutate one outcome
    ev = synth_frame([("2023-04-20", 18)])
    f = ev[FEATS].to_numpy(dtype=float)
    pA = rtp.batch_predict(rtp.fit_arm(tA), f)
    pB = rtp.batch_predict(rtp.fit_arm(tB), f)
    assert np.abs(pA - pB).max() > 1e-9
    # a bundle fit on tA is unaffected by tB's mutation
    assert np.abs(rtp.batch_predict(rtp.fit_arm(tA), f) - pA).max() == 0.0


def test_min_count_gate_fails_loud():
    thin = train_synth(n=30, short=1)          # n < 50
    with pytest.raises(rtp.RunFailure):
        rtp.fit_arm(thin)
    noshort = train_synth(n=60, short=0)
    with pytest.raises(rtp.RunFailure):
        rtp.fit_arm(noshort)


def test_batch_predict_matches_per_row_path():
    t = train_synth(n=60, seed=11)
    b = rtp.fit_arm(t)
    ev = synth_frame([("2023-04-20", 18), ("2023-04-21", 25)])
    f = ev[FEATS].to_numpy(dtype=float)
    batched = rtp.batch_predict(b, f)
    for i in range(len(f)):
        per_row = bfd.predict_pmf(b, f[i:i + 1])
        assert np.abs(batched[i] - per_row[0]).max() < 1e-10
        assert abs(batched[i].sum() - 1.0) < 1e-9
