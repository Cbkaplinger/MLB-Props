"""Synthetic tests for the lineup diagnostic runner. No real data.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import lineup_diagnostic as ld  # noqa: E402
from pregame_pa_ext import ablation_features as ab  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402


def _synthetic_inputs(tmp_path):
    """A tiny deterministic lake: 12 starts x 9 projected slots with
    realized PAs (some starts with <9 distinct batters to exercise the
    drop accounting), plus the frames the runner consumes."""
    import datetime as dt
    rng = np.random.default_rng(5)
    pa_rows = []
    led_rows = []
    pid = 0
    for g in range(12):
        gid = 800000 + g
        gd = date(2024, 8, 1) + dt.timedelta(days=g)
        pitcher = 700000 + g
        slot_batters = {}
        for slot in range(1, 10):
            b = 600000 + g * 10 + slot
            slot_batters[slot] = b
        led_rows.append((gid, "Top" if g % 2 else "Bot", pitcher, gd,
                         slot_batters))
        # actual PAs: batters in ACTUAL order (a shuffled projection)
        n_bf = int(rng.integers(7, 25))
        order = list(slot_batters.values())
        rng.shuffle(order)
        for k in range(n_bf):
            pid += 1
            b = order[k % len(order)]
            y = int(rng.random() < 0.22)
            pa_rows.append((gid, k + 1, b, pitcher, gd, y))
    pa = pl.DataFrame(pa_rows, schema={
        "game_pk": pl.Int64, "at_bat_number": pl.Int64,
        "batter": pl.Int64, "pitcher": pl.Int64,
        "game_date": pl.Date, "y": pl.Int8}, orient="row")
    return pa


def test_control_invariant_batter_independent_arm():
    """The PITCHER-only arm's probabilities are batter-independent, so
    the projected and oracle count PMFs must be IDENTICAL within the
    declared tolerance - the control invariant the owner ordered."""
    # one start; projected slot order != actual appearance order
    slot_rows = pl.DataFrame({"slot": list(range(1, 10)),
                              "p_k": [0.22] * 9})
    actual_order = [105, 101, 109, 102, 108, 103, 107, 104, 106, 101,
                    102, 103]
    rows = []
    for k, b in enumerate(actual_order):
        rows.append((1, k + 1, b, 500, date(2024, 8, 1),
                     1 if b in (101, 105) else 0))
    feat_start = pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "at_bat_number": pl.Int64,
        "batter": pl.Int64, "pitcher": pl.Int64,
        "game_date": pl.Date, "y": pl.Int8}, orient="row").with_columns(
        pl.lit(0.22).alias("p_k"))  # batter-independent probability
    p_proj = ld._slot_order_p9(slot_rows)
    p_orac = ld._appearance_order_p9(feat_start)
    assert p_proj is not None and p_orac is not None
    # the values are identical by construction (batter-independent p)
    assert sorted(p_proj) == sorted(p_orac)
    # identical values everywhere -> order cannot change the PMF
    bf_ext = np.full(60, 1.0 / 60)
    pmf_proj = __import__("pregame_pa_ext.adapter", fromlist=["x"]) \
        .count_pmf_from_mixture(
        bf_ext, __import__("pregame_pa_ext.adapter", fromlist=["x"])
        .cycled_cond_mean(np.asarray(p_proj)))
    pmf_orac = __import__("pregame_pa_ext.adapter", fromlist=["x"]) \
        .count_pmf_from_mixture(
        bf_ext, __import__("pregame_pa_ext.adapter", fromlist=["x"])
        .cycled_cond_mean(np.asarray(p_orac)))
    assert float(np.max(np.abs(pmf_proj - pmf_orac))) \
        <= ld.CONTROL_TOLERANCE


def test_slot_order_p9_requires_all_slots():
    rows = [(1, k + 1, 600 + k, 500, date(2024, 8, 1), 0)
            for k in range(8)]
    feat_start = pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "at_bat_number": pl.Int64,
        "batter": pl.Int64, "pitcher": pl.Int64,
        "game_date": pl.Date, "y": pl.Int8}, orient="row").with_columns(
        pl.lit(0.2).alias("p_k"))
    # the new signature: a frame of (slot, p_k) rows; 8 slots -> None
    slot_rows = pl.DataFrame({"slot": list(range(1, 9)),
                              "p_k": [0.2] * 8})
    assert ld._slot_order_p9(slot_rows) is None
    assert ld._appearance_order_p9(feat_start) is None  # 8 < 9 batters


def test_appearance_order_p9_is_first_appearance_order():
    # batter 603 appears LATE in at_bat order but must be placed by its
    # own first appearance
    rows = []
    order = [601, 602, 604, 603, 605, 606, 607, 608, 609]
    for k, b in enumerate(order):
        rows.append((1, k + 1, b, 500, date(2024, 8, 1), 0))
    feat_start = pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "at_bat_number": pl.Int64,
        "batter": pl.Int64, "pitcher": pl.Int64,
        "game_date": pl.Date, "y": pl.Int8}, orient="row").with_columns(
        (1.0 / pl.col("batter")).alias("p_k"))
    p9 = ld._appearance_order_p9(feat_start)
    assert len(p9) == 9
    # probabilities identify the batters: 1/603 sits at position 4
    assert p9[3] == pytest.approx(1.0 / 603)


def test_runner_write_once_and_receipts(tmp_path):
    """The runner's write-once guard and receipt pattern (empty but
    correctly-schemed frames fail loud inside the try, after the
    initial receipt is written)."""
    feat_schema = {"game_pk": pl.Int64, "at_bat_number": pl.Int64,
                   "batter": pl.Int64, "pitcher": pl.Int64,
                   "game_date": pl.Date, "y": pl.Int8,
                   **{c: pl.Float64 for c in ab.FEATURE_SETS["FULL"]}}
    empty_feat = pl.DataFrame(schema=feat_schema)
    ledger = pl.DataFrame(schema={"game_pk": pl.Int64, "side": pl.Utf8,
                                  "pitcher": pl.Int64, "slot": pl.Int8,
                                  "batter": pl.Int64,
                                  "exclusion_reason": pl.Utf8})
    pmfs = pl.DataFrame(schema={"game_pk": pl.Int64, "side": pl.Utf8,
                                "pitcher": pl.Int64})
    realized = pl.DataFrame(schema={"game_pk": pl.Int64, "side": pl.Utf8,
                                    "pitcher": pl.Int64,
                                    "realized_k": pl.Int64})
    bf = pl.DataFrame(schema={"game_pk": pl.Int64, "side": pl.Utf8,
                              "pitcher": pl.Int64,
                              **{f"pmf37_{k}": pl.Float64
                                 for k in range(37)}})
    out = tmp_path / "ld"
    out.mkdir()
    with pytest.raises(ValueError, match="write-once violation"):
        ld.run_lineup_diagnostic(empty_feat, ledger, pmfs, realized, bf,
                                 out)
    rec = tmp_path / "ld2"
    with pytest.raises(Exception):
        ld.run_lineup_diagnostic(empty_feat, ledger, pmfs, realized, bf,
                                 rec)
    assert (rec / "failure_record.json").exists()
    assert (rec / "receipt_initial.json").exists()
    assert not (rec / "receipt_final.json").exists()
