"""Regression tests for the pooled mean-K RMSE correction (rmse_correction_v2).

The frozen scorer stored per-start SQUARED errors in `{tag}_rmse_mean_k`
and pooled them with the buggy form sqrt(mean(se**2)) = sqrt(mean(err^4)).
The corrected function compute_corrected_rmse.corrected_pooled_rmse takes
per-start squared errors and returns sqrt(mean(se)) = sqrt(mean(err^2)).
"""
import math

import numpy as np
import polars as pl
import pytest

from compute_corrected_rmse import (
    BLOCK_COL,
    buggy_pooled_rmse_v1,
    corrected_pooled_rmse,
    row_weighted_block_rmse,
)

# raw errors 1, 2, 4 -> squared errors 1, 4, 16 -> mean 21/3
RAW_ERRORS = np.array([1.0, 2.0, 4.0])
SQUARED_ERRORS = RAW_ERRORS ** 2
HAND_RMSE = math.sqrt(21.0 / 3.0)
BUGGY_RMSE = math.sqrt((1.0 + 16.0 + 256.0) / 3.0)  # sqrt(mean(err^4))


def test_hand_calculated_fixture_unequal_errors():
    assert corrected_pooled_rmse(SQUARED_ERRORS) == pytest.approx(
        HAND_RMSE, rel=0, abs=1e-15)
    assert HAND_RMSE == pytest.approx(math.sqrt(7.0))


def test_pooled_matches_row_weighted_block_aggregation():
    # two blocks with UNEQUAL sizes: n1=2, n2=3
    se1 = np.array([1.0, 4.0])        # mse1 = 2.5
    se2 = np.array([9.0, 16.0, 25.0])  # mse2 = 50/3
    pooled = corrected_pooled_rmse(np.concatenate([se1, se2]))
    weighted = math.sqrt(
        (se1.size * se1.mean() + se2.size * se2.mean())
        / (se1.size + se2.size))
    assert pooled == pytest.approx(math.sqrt(11.0), rel=0, abs=1e-15)
    assert pooled == pytest.approx(weighted, rel=0, abs=1e-15)

    frame = pl.DataFrame({
        BLOCK_COL: ["b1", "b1", "b2", "b2", "b2"],
        "se": [1.0, 4.0, 9.0, 16.0, 25.0],
    })
    assert row_weighted_block_rmse(frame, "se") == pytest.approx(
        pooled, rel=0, abs=1e-12)


def test_buggy_form_differs_and_corrected_matches_hand_calc():
    corrected = corrected_pooled_rmse(SQUARED_ERRORS)
    buggy = buggy_pooled_rmse_v1(SQUARED_ERRORS)
    # the shipped buggy form sqrt(mean((err^2)^2)) does NOT match the
    # hand calculation on this fixture
    assert buggy == pytest.approx(BUGGY_RMSE, rel=0, abs=1e-15)
    assert buggy != pytest.approx(HAND_RMSE, rel=0, abs=1e-12)
    assert abs(buggy - corrected) > 1.0
    # ...and the corrected one does
    assert corrected == pytest.approx(HAND_RMSE, rel=0, abs=1e-15)


def test_corrected_rejects_negative_input():
    # the input contract is SQUARED errors (non-negative); negatives mean
    # the caller passed raw errors or the wrong column
    with pytest.raises(ValueError):
        corrected_pooled_rmse(np.array([1.0, -4.0]))
