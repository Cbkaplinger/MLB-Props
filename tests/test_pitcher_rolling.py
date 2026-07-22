"""Tests for leakage-safe rolling / season-to-date pitcher features."""

from __future__ import annotations

import datetime as dt

import polars as pl

from mlb_props import pitcher_rolling as pr


def _starts(rows):
    return pl.DataFrame(rows, schema_overrides={"game_date": pl.Date})


def _s(day, k, pa, *, pitcher=1, gp=None, year=2024, ff_velo=95.0, pitches=90):
    return dict(
        pitcher=pitcher,
        game_pk=gp if gp is not None else day,
        game_date=dt.date(year, 4, day),
        K=k, PA=pa, Pitches=pitches, ff_velo=ff_velo,
    )


def test_season_to_date_and_rolling_are_pregame():
    df = pr.add_rolling_pitcher_features(
        _starts([_s(1, 8, 20), _s(2, 4, 20), _s(3, 0, 20)]),
        rate_stats={"k_rate": ("K", "PA")},
        mean_cols=["ff_velo"],
        rate_windows=(5,), mean_windows=(5,),
    ).sort("game_date")

    assert df["k_rate_std"][0] is None                    # no prior starts
    assert abs(df["k_rate_std"][1] - 8 / 20) < 1e-9        # start 1 only
    assert abs(df["k_rate_std"][2] - 12 / 40) < 1e-9       # starts 1+2
    # rolling excludes the current start
    assert df["k_rate_P5"][0] is None
    assert abs(df["k_rate_P5"][2] - 12 / 40) < 1e-9


def test_rate_is_pa_weighted_not_mean_of_ratios():
    # Start 1: 10/10 = 1.0, Start 2: 0/40 = 0.0. PA-weighted over both = 10/50 = 0.2,
    # which differs from the naive average of ratios (0.5).
    df = pr.add_rolling_pitcher_features(
        _starts([_s(1, 10, 10), _s(2, 0, 40), _s(3, 0, 1)]),
        rate_stats={"k_rate": ("K", "PA")},
        mean_cols=[], rate_windows=(5,), season_to_date=False,
    ).sort("game_date")
    assert abs(df["k_rate_P5"][2] - 10 / 50) < 1e-9


def test_mean_column_rolls_and_shifts():
    df = pr.add_rolling_pitcher_features(
        _starts([_s(1, 0, 20, ff_velo=96.0), _s(2, 0, 20, ff_velo=94.0)]),
        rate_stats={}, mean_cols=["ff_velo"], mean_windows=(5,),
    ).sort("game_date")
    assert df["ff_velo_P5"][0] is None
    assert abs(df["ff_velo_P5"][1] - 96.0) < 1e-9   # only the prior start


def test_missing_columns_are_skipped():
    # No 'Swings' column -> whiff_rate is silently skipped, no crash.
    df = pr.add_rolling_pitcher_features(
        _starts([_s(1, 5, 20), _s(2, 5, 20)]),
        rate_stats={"whiff_rate": ("Whiffs", "Swings")},
        mean_cols=[], rate_windows=(5,),
    )
    assert not any(c.startswith("whiff_rate") for c in df.columns)
