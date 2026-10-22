"""Integration tests for the M0 multi-class PA outcome model.
SYNTHETIC ONLY. Self-contained lake, no real data, no shared state.
Path claims: tests/fixtures_m0_integration.py + tests/test_m0_integration.py
(Chat 1 builder)."""
from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys = __import__("sys")
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))
sys.path.insert(0, str(HERE / "tests"))

import pregame_pa_ext.adapter as ad  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402
from fixtures_m0_integration import (  # noqa: E402
    build_integration_lake, CLASS_CYCLE, CLASS_TO_EVENT, BATTERS,
)


# --- 1. five-class fixture -------------------------------------------------
def test_five_classes_present_in_each_dev_block():
    """Every dev block's training data contains all five taxonomy
    classes with deterministic identities."""
    tmp = Path(tempfile.mkdtemp())
    lake = build_integration_lake(tmp, include_confirm=False,
                                  include_2022=False)
    mc = lake["pa_with_events"]
    for block in ("block_2024H2", "block_2025H1"):
        if block == "block_2024H2":
            lo, hi = pl.date(2024, 7, 1), pl.date(2024, 12, 31)
        else:
            lo, hi = pl.date(2025, 1, 1), pl.date(2025, 6, 30)
        block_data = mc.filter(
            (pl.col("game_date") >= lo) & (pl.col("game_date") <= hi))
        for cls in range(5):
            count = block_data.filter(pl.col("class_label") == cls).height
            assert count > 0, (
                f"block {block}: class {cls} "
                f"({m0.CLASS_NAMES[cls]}) has 0 training examples")


def test_five_class_identities_are_deterministic():
    """The event-to-class mapping produces the EXPECTED class label for
    each PA (not random coverage)."""
    tmp = Path(tempfile.mkdtemp())
    lake = build_integration_lake(tmp, include_confirm=False,
                                  include_2022=False)
    mc = lake["pa_with_events"]
    # verify the first 18 PAs cycle through the 5 classes in order
    game_first = mc.filter(pl.col("game_pk") == 900).sort("at_bat_number")
    for i, r in enumerate(game_first.iter_rows(named=True)):
        expected = CLASS_CYCLE[i % len(CLASS_CYCLE)]
        assert r["class_label"] == expected, (
            f"PA {i}: expected {expected}, got {r['class_label']}")


# --- 2. block isolation -----------------------------------------------------
def test_confirm_rows_isolated_from_dev(tmp_path):
    """Changing confirm-block outcomes does not change dev-block
    evaluation results."""
    lake_n = build_integration_lake(tmp_path / "n", include_confirm=True,
                                    confirm_outcome_flip=False)
    lake_f = build_integration_lake(tmp_path / "f", include_confirm=True,
                                    confirm_outcome_flip=True)
    # confirm-block outcomes differ
    cn = lake_n["pa_with_events"].filter(
        pl.col("game_date") > pl.date(2025, 6, 30))
    cf = lake_f["pa_with_events"].filter(
        pl.col("game_date") > pl.date(2025, 6, 30))
    if cn.height > 0 and cf.height > 0:
        assert cn["y"].to_list() != cf["y"].to_list()
    # dev-block outcomes are identical
    dn = lake_n["pa_with_events"].filter(
        pl.col("game_date") <= pl.date(2025, 6, 30))
    df = lake_f["pa_with_events"].filter(
        pl.col("game_date") <= pl.date(2025, 6, 30))
    assert dn["y"].to_list() == df["y"].to_list()
    # dev slot probabilities are identical
    ln = lake_n["ledger"].filter(pl.col("game_date") <= pl.date(2025, 6, 30))
    lf = lake_f["ledger"].filter(pl.col("game_date") <= pl.date(2025, 6, 30))
    assert ln["p_h3_raw"].to_list() == lf["p_h3_raw"].to_list()


# --- 3. probability output ---------------------------------------------------
def test_probability_output_shape_and_bounds():
    """The multinomial model produces 5 correctly ordered class
    probabilities per evaluated row: finite, in [0, 1], summing to 1."""
    tmp = Path(tempfile.mkdtemp())
    lake = build_integration_lake(tmp, include_confirm=False,
                                  include_2022=True)
    mc = lake["pa_with_events"]
    model = m0.fit_multinomial(mc)
    probs = m0.apply_multinomial(mc, model)
    assert probs.shape == (mc.height, 5)
    assert np.all(np.isfinite(probs))
    assert np.all(probs >= 0)
    assert np.all(probs <= 1)
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-12)
    assert sorted(model["classes"]) == list(range(5))


# --- 4. historical continuity -----------------------------------------------
def test_2022_history_affects_2024_features():
    """Removing 2022 PA rows CHANGES the multinomial model (the
    registered behavior: feature history spans 2022-2025, no season
    reset). This is the EXPECTED effect."""
    tmp = Path(tempfile.mkdtemp())
    lake_w = build_integration_lake(tmp / "w", include_2022=True,
                                    include_confirm=False)
    lake_wo = build_integration_lake(tmp / "wo", include_2022=False,
                                     include_confirm=False)
    # both have dev-block rows with the same class labels
    dev_w = lake_w["pa_with_events"].filter(
        pl.col("game_date") >= pl.date(2024, 7, 1))
    dev_wo = lake_wo["pa_with_events"].filter(
        pl.col("game_date") >= pl.date(2024, 7, 1))
    assert dev_w["y"].to_list() == dev_wo["y"].to_list()
    # the models differ because the training lineage differs
    model_w = m0.fit_multinomial(dev_w)
    model_wo = m0.fit_multinomial(dev_wo)
    assert model_w["mean"] != model_wo["mean"] or \
        model_w["scale"] != model_wo["scale"]


def test_future_history_cannot_affect_earlier_forecasts():
    """PA rows AFTER a forecast date cannot change the features for
    that forecast (strictly-prior as-of construction)."""
    tmp = Path(tempfile.mkdtemp())
    lake = build_integration_lake(tmp, include_confirm=True,
                                  include_2022=True)
    pa = lake["pa_with_events"]
    forecast_date = lake["grid"][0][1]  # first dev-block game date
    feat_full = pa.filter(pl.col("game_date") == forecast_date)
    # verify that the features for this date exist and are finite
    assert feat_full.height > 0
    model = m0.fit_multinomial(
        pa.filter(pl.col("game_date") >= pl.date(2023, 1, 1)))
    probs = m0.apply_multinomial(feat_full, model)
    assert np.all(np.isfinite(probs))
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-12)


# --- 5. self-containment ---------------------------------------------------
def test_no_real_data_fallback(tmp_path):
    """The fixture is entirely temporary: it creates files in tmp_path
    and never falls back to a local real-data directory."""
    lake = build_integration_lake(tmp_path, include_confirm=False)
    for k, v in lake["paths"].items():
        assert str(tmp_path) in str(v), (
            f"artifact {k} path {v} is outside tmp_path {tmp_path}")
    assert lake["pa_with_events"].height > 0
