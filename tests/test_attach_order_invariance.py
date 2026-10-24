"""Regression test for the attach_prior_features order-sensitivity
defect (demonstrated 2026-10-22, repaired in the same commit): the
function must return IDENTICAL features regardless of the input row
order (chronological / shuffled / reversed), preserving request
identity.
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

from pregame_pa_ext import adapter as ad  # noqa: E402


def _synthetic_state(n_players=6, days=40, seed=3):
    """Deterministic pa_table-like frame for building state tables."""
    rng = np.random.default_rng(seed)
    import datetime as dt
    rows = []
    pid = 0
    for p in range(n_players):
        base = 0.15 + 0.04 * p
        for d in range(days):
            gd = date(2023, 4, 1) + dt.timedelta(days=d)
            for k in range(10):
                pid += 1
                rows.append((900000 + p, pid, 600000 + pid % 40,
                             500000 + p, gd,
                             int(rng.random() < base + 0.001 * d)))
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "at_bat_number": pl.Int64,
        "batter": pl.Int64, "pitcher": pl.Int64,
        "game_date": pl.Date, "y": pl.Int8}, orient="row")


def _requests(pa, order):
    reqs = pa.select(pl.col("pitcher"), pl.col("batter"),
                     pl.col("game_date")).unique()
    if order == "chronological":
        return reqs.sort("game_date")
    if order == "reversed":
        return reqs.reverse()
    return reqs.sample(fraction=1.0, shuffle=True, seed=777)


@pytest.mark.parametrize("order", ["chronological", "shuffled",
                                   "reversed"])
def test_attach_prior_features_order_invariance(order):
    """The join contract: identical requests in ANY input order must
    produce identical features (keyed by pitcher+batter+game_date)."""
    pa = _synthetic_state()
    p_state = ad.entity_daily_state(pa, "pitcher")
    b_state = ad.entity_daily_state(pa, "batter")
    lg_state = ad.league_daily_state(pa)
    reqs = _requests(pa, order)
    out = ad.attach_prior_features(reqs, p_state, b_state, lg_state)
    key = ["pitcher", "batter", "game_date"]
    base = out.sort(key).select(key, *ad.FEAT_H3)
    if order == "chronological":
        globals()["_base_frame"] = base
    else:
        assert base.equals(globals()["_base_frame"]), (
            f"order={order}: features differ from the chronological run")


def test_attach_prior_features_reversed_equals_chronological():
    """Direct pairwise check with the synthetic lake: reversed input
    order must reproduce the chronological features exactly."""
    pa = _synthetic_state()
    p_state = ad.entity_daily_state(pa, "pitcher")
    b_state = ad.entity_daily_state(pa, "batter")
    lg_state = ad.league_daily_state(pa)
    chron = ad.attach_prior_features(_requests(pa, "chronological"),
                                     p_state, b_state, lg_state)
    rev_in = _requests(pa, "reversed")
    rev = ad.attach_prior_features(rev_in, p_state, b_state, lg_state)
    key = ["pitcher", "batter", "game_date"]
    j = chron.sort(key).join(rev.sort(key), on=key, suffix="_rev",
                             how="inner")
    assert j.height == chron.height
    for f in ad.FEAT_H3:
        a = j[f].to_numpy().astype(float)
        b = j[f + "_rev"].to_numpy().astype(float)
        d = np.where(np.isnan(a) & np.isnan(b), 0.0, np.abs(a - b))
        assert (d <= 1e-12).all(), f"{f}: order-sensitive (max {d.max()})"
