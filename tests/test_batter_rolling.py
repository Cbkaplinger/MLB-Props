"""Tests for leakage-safe rolling / season-to-date batter K%."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from Python import batter_rolling as br


def _games(rows):
    return pl.DataFrame(rows, schema_overrides={"game_date": pl.Date})


def _g(day, pa, k, *, pa_vl=0, k_vl=0, pa_vr=0, k_vr=0, batter=1, gp=None, year=2024,
       whiffs=0, pitches=0, chases=0, outzone=0):
    return dict(
        batter=batter,
        game_pk=gp if gp is not None else day,
        game_date=dt.date(year, 4, day),
        PA=pa, K=k,
        PA_vL=pa_vl, K_vL=k_vl, PA_vR=pa_vr, K_vR=k_vr,
        Whiffs=whiffs, Pitches=pitches, Chases=chases, OutZone=outzone,
    )


def test_season_to_date_is_pregame_only():
    df = br.add_leakage_safe_k(
        _games([_g(1, 4, 2), _g(2, 4, 1), _g(3, 4, 0)]),
        windows=(5,), shrink_pa=0,
    ).sort("game_date")

    # Game 1 has no prior PA -> null; later games use only earlier games.
    assert df["k_rate_std"][0] is None
    assert abs(df["k_rate_std"][1] - 0.5) < 1e-9      # 2/4
    assert abs(df["k_rate_std"][2] - 0.375) < 1e-9    # (2+1)/(4+4)


def test_rolling_window_excludes_current_game():
    df = br.add_leakage_safe_k(
        _games([_g(1, 4, 4), _g(2, 4, 0)]),
        windows=(5,), shrink_pa=0,
    ).sort("game_date")
    # If the current game leaked in, game 2 would be (4+0)/(4+4)=0.5.
    assert df["k_rate_P5"][0] is None
    assert abs(df["k_rate_P5"][1] - 1.0) < 1e-9       # only game 1


def test_same_date_games_do_not_feed_each_other():
    df = br.add_leakage_safe_k(
        _games([
            _g(1, 4, 4, gp=100),
            _g(1, 4, 0, gp=200),
            _g(2, 4, 0, gp=300),
        ]),
        windows=(5,),
        shrink_pa=0,
    ).sort("game_pk")
    assert df["k_rate_P5"][0] is None
    assert df["k_rate_P5"][1] is None
    assert df["k_rate_P5"][2] == pytest.approx(4 / 8)


def test_season_to_date_resets_but_rolling_carries():
    df = br.add_leakage_safe_k(
        _games([
            _g(1, 4, 4, year=2024, gp=202401),
            _g(1, 4, 0, year=2025, gp=202501),
        ]),
        windows=(5,), shrink_pa=0,
    ).sort("game_date")
    # New season -> season-to-date starts empty again.
    assert df["k_rate_std"][1] is None
    # Rolling last-N still sees last season's game.
    assert abs(df["k_rate_P5"][1] - 1.0) < 1e-9


def test_handedness_splits():
    df = br.add_leakage_safe_k(
        _games([
            _g(1, 4, 2, pa_vl=2, k_vl=2, pa_vr=2, k_vr=0),
            _g(2, 4, 0, pa_vl=2, k_vl=0, pa_vr=2, k_vr=0),
        ]),
        windows=(5,), shrink_pa=0,
    ).sort("game_date")
    assert abs(df["k_rate_std_vL"][1] - 1.0) < 1e-9   # 2/2 vs LHP
    assert abs(df["k_rate_std_vR"][1] - 0.0) < 1e-9   # 0/2 vs RHP


def test_extra_rate_stats_whiff_and_chase():
    df = br.add_leakage_safe_k(
        _games([
            _g(1, 4, 1, whiffs=10, pitches=50, chases=6, outzone=20),
            _g(2, 4, 1, whiffs=0, pitches=50, chases=0, outzone=20),
        ]),
        windows=(5,), shrink_pa=0,
    ).sort("game_date")
    # game 2 uses only game 1: whiff/pitch = 10/50, chase/outzone = 6/20
    assert abs(df["whiff_rate_std"][1] - 0.2) < 1e-9
    assert abs(df["chase_rate_std"][1] - 0.3) < 1e-9


def test_shrinkage_pulls_small_samples_toward_league():
    # Batter 1 K'd every PA; a low-K batter 2 keeps the league mean well below 1.
    df = br.add_leakage_safe_k(
        _games([
            _g(1, 4, 4, batter=1, gp=1), _g(2, 4, 4, batter=1, gp=2),
            _g(1, 40, 2, batter=2, gp=3), _g(2, 40, 2, batter=2, gp=4),
        ]),
        windows=(5,), shrink_pa=200.0,
    ).filter(pl.col("batter") == 1).sort("game_date")
    raw = df["k_rate_std"][1]
    shrunk = df["k_rate_std_shrunk"][1]
    assert abs(raw - 1.0) < 1e-9
    assert shrunk < raw   # regressed toward the league mean (< 1.0)


def test_shrinkage_uses_sourced_prior_on_first_date():
    games = _games([_g(1, 4, 1), _g(2, 4, 1)]).with_columns(
        pl.lit(0.21).alias("prior_league_k_rate")
    )
    df = br.add_leakage_safe_k(games, windows=(5,), shrink_pa=200.0).sort(
        "game_date"
    )
    assert df["k_rate_std_shrunk"][0] == pytest.approx(0.21)


def test_shrinkage_without_prior_remains_null_on_first_date():
    df = br.add_leakage_safe_k(
        _games([_g(1, 4, 1), _g(2, 4, 1)]),
        windows=(5,),
        shrink_pa=200.0,
    ).sort("game_date")
    assert df["k_rate_std_shrunk"][0] is None


def test_shrinkage_prior_does_not_use_future_games():
    history = [
        _g(1, 4, 1, batter=1, gp=1),
        _g(1, 4, 1, batter=2, gp=2),
        _g(2, 4, 2, batter=1, gp=3),
    ]
    base = br.add_leakage_safe_k(
        _games(history), windows=(5,), shrink_pa=200.0
    )
    with_future = br.add_leakage_safe_k(
        _games(history + [_g(3, 100, 100, batter=3, gp=4)]),
        windows=(5,),
        shrink_pa=200.0,
    )
    base_value = base.filter(
        (pl.col("batter") == 1) & (pl.col("game_pk") == 3)
    )["k_rate_std_shrunk"][0]
    future_value = with_future.filter(
        (pl.col("batter") == 1) & (pl.col("game_pk") == 3)
    )["k_rate_std_shrunk"][0]
    assert abs(base_value - future_value) < 1e-12


def test_duplicate_batter_game_keys_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        br.add_leakage_safe_k(
            _games([_g(1, 4, 1), _g(1, 4, 1)]),
            windows=(5,),
            shrink_pa=0,
        )
