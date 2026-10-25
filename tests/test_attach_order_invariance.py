"""Regression tests for the attach_prior_features order-sensitivity
defect (demonstrated 2026-10-22, repaired in the same commit): the
function must return IDENTICAL features regardless of the input row
order. Each test builds its own chronological reference independently
(no cross-test state); shuffled and reversed inputs are derived from
that same canonical request frame; request identity (_rid) is carried
through and asserted.
"""
from __future__ import annotations

import sys
from datetime import date
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


def _canonical_requests(pa):
    """The canonical request frame: unique (pitcher, batter, game_date)
    triples sorted chronologically, with stable request IDs _rid."""
    reqs = (pa.select(pl.col("pitcher"), pl.col("batter"),
                      pl.col("game_date")).unique()
            .sort("game_date", "pitcher", "batter")
            .with_row_index("_rid"))
    return reqs


def _attach(requests):
    return ad.attach_prior_features(requests, *_state_cache())


_STATE = {}


def _state_cache():
    if not _STATE:
        pa = _synthetic_state()
        _STATE["p"] = ad.entity_daily_state(pa, "pitcher")
        _STATE["b"] = ad.entity_daily_state(pa, "batter")
        _STATE["l"] = ad.league_daily_state(pa)
    return _STATE["p"], _STATE["b"], _STATE["l"]


def _ordered(reqs, order):
    """Derive an input ordering from the CANONICAL chronologically
    sorted request frame; identity (_rid) travels with each row."""
    if order == "chronological":
        return reqs
    if order == "reversed":
        return reqs.reverse()  # true reverse-chronological
    return reqs.sample(fraction=1.0, shuffle=True, seed=777)


@pytest.mark.parametrize("order", ["chronological", "shuffled",
                                   "reversed"])
def test_attach_prior_features_order_invariance(order):
    """Each case: attach on the reordered canonical requests, join back
    by _rid, and require exact equality with the chronological
    reference. Runnable standalone."""
    pa = _synthetic_state()
    p_state, b_state, lg_state = _state_cache()
    reqs = _canonical_requests(pa)
    n_requests = reqs.height
    inp = _ordered(reqs, order)
    # request-count preservation: reordering never adds/drops rows
    assert inp.height == n_requests
    assert set(inp["_rid"].to_list()) == set(reqs["_rid"].to_list())
    out = ad.attach_prior_features(
        inp.select("_rid", "pitcher", "batter", "game_date"),
        p_state, b_state, lg_state)
    # exactly one result per request, no fan-out
    assert out.height == n_requests
    one_to_one = out.group_by("_rid").agg(pl.len().alias("n"))
    assert (one_to_one["n"] == 1).all()
    # reference: attach on the CHRONOLOGICAL canonical frame
    ref = ad.attach_prior_features(
        reqs.select("_rid", "pitcher", "batter", "game_date"),
        p_state, b_state, lg_state)
    j = (ref.select("_rid", *ad.FEAT_H3)
         .join(out.select("_rid", *ad.FEAT_H3), on="_rid",
               suffix="_reordered", validate="1:1"))
    assert j.height == n_requests
    for f in ad.FEAT_H3:
        a = j[f].to_numpy().astype(float)
        b = j[f + "_reordered"].to_numpy().astype(float)
        d = np.where(np.isnan(a) & np.isnan(b), 0.0, np.abs(a - b))
        assert (d <= 1e-12).all(), (
            f"order={order}: {f} is order-sensitive (max {d.max()})")


def test_attach_prior_features_reversed_equals_chronological_pairwise():
    """Direct pairwise check on a synthetic lake: true
    reverse-chronological input order reproduces the chronological
    features exactly (per-feature, per-row)."""
    pa = _synthetic_state()
    p_state, b_state, lg_state = _state_cache()
    reqs = _canonical_requests(pa)
    chron = ad.attach_prior_features(
        reqs.select("_rid", "pitcher", "batter", "game_date"),
        p_state, b_state, lg_state)
    rev = ad.attach_prior_features(
        reqs.reverse().select("_rid", "pitcher", "batter", "game_date"),
        p_state, b_state, lg_state)
    j = (chron.select("_rid", *ad.FEAT_H3)
         .join(rev.select("_rid", *ad.FEAT_H3), on="_rid",
               suffix="_rev", validate="1:1"))
    assert j.height == reqs.height
    for f in ad.FEAT_H3:
        a = j[f].to_numpy().astype(float)
        b = j[f + "_rev"].to_numpy().astype(float)
        d = np.where(np.isnan(a) & np.isnan(b), 0.0, np.abs(a - b))
        assert (d <= 1e-12).all(), f"{f}: order-sensitive (max {d.max()})"
