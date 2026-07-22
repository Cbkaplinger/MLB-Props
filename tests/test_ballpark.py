"""Tests for empirical ballpark strikeout factors."""

from __future__ import annotations

import datetime as dt

import polars as pl

from mlb_props import ballpark as bp


def _pa(home_team, k_flags):
    return pl.DataFrame({"home_team": [home_team] * len(k_flags), "is_k": k_flags})


def test_park_factor_direction_and_neutral_scale():
    pa = pl.concat([
        _pa("HiK", [True] * 6 + [False] * 4),   # 60% K
        _pa("LoK", [True] * 1 + [False] * 9),   # 10% K
    ])
    out = bp.park_k_factor(pa, regress=0.0)
    hi = out.filter(pl.col("home_team") == "HiK")["park_k_factor"][0]
    lo = out.filter(pl.col("home_team") == "LoK")["park_k_factor"][0]
    # League K rate = 7/20 = 0.35.
    assert hi > 1.0 > lo
    assert abs(hi - (0.6 / 0.35)) < 1e-9
    assert abs(lo - (0.1 / 0.35)) < 1e-9


def test_regression_pulls_toward_neutral():
    pa = pl.concat([
        _pa("HiK", [True] * 6 + [False] * 4),
        _pa("LoK", [True] * 1 + [False] * 9),
    ])
    raw = bp.park_k_factor(pa, regress=0.0).filter(pl.col("home_team") == "HiK")["park_k_factor"][0]
    reg = bp.park_k_factor(pa, regress=50.0).filter(pl.col("home_team") == "HiK")["park_k_factor"][0]
    assert 1.0 < reg < raw   # heavy regression shrinks the extreme park toward 1.0


def test_pregame_factors_use_prior_seasons_only():
    pa = pl.DataFrame(
        {
            "game_date": [
                dt.date(2023, 4, 1), dt.date(2023, 4, 2),
                dt.date(2024, 4, 1), dt.date(2024, 4, 2),
            ],
            "home_team": ["AAA", "BBB", "AAA", "BBB"],
            "is_k": [True, False, False, True],
        },
        schema_overrides={"game_date": pl.Date},
    )
    out = bp.pregame_park_factors(pa, (2023, 2024), regress=0.0)
    # No pre-2023 history: neutral fallback.
    assert set(out.filter(pl.col("season") == 2023)["park_k_factor"]) == {1.0}
    # 2024 uses 2023 only: AAA was all K; BBB had no K.
    factors_2024 = out.filter(pl.col("season") == 2024)
    assert factors_2024.filter(pl.col("home_team") == "AAA")["park_k_factor"][0] > 1.0
    assert factors_2024.filter(pl.col("home_team") == "BBB")["park_k_factor"][0] < 1.0
