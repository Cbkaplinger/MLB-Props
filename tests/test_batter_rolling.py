"""Tests for leakage-safe rolling / season-to-date batter K%."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from Python import batter_rolling as br


def _games(rows):
    return pl.DataFrame(rows, schema_overrides={"game_date": pl.Date})


def _g(day, pa, k, *, pa_vl=0, k_vl=0, pa_vr=0, k_vr=0, batter=1, gp=None, year=2024,
       whiffs=0, swings=0, pitches=0, chases=0, outzone=0, zswings=0,
       inzone=0, zcontacts=0, bb=0, lineup_slot=1, woba_num=0.0,
       woba_den=0, xwoba_num=0.0, xba_num=0.0, xba_den=0,
       hard_hit=0, barrels=0, sweet_spot=0, ev_num=0.0, ev_den=0,
       la_num=0.0, la_den=0, babip_num=0, babip_den=0, hr=0, fb=0,
       bip=0, pull_air=0, rv_num=0.0, rv_den=0):
    return dict(
        batter=batter,
        game_pk=gp if gp is not None else day,
        game_date=dt.date(year, 4, day),
        PA=pa, K=k,
        PA_vL=pa_vl, K_vL=k_vl, PA_vR=pa_vr, K_vR=k_vr,
        Whiffs=whiffs, Swings=swings, Pitches=pitches,
        Chases=chases, OutZone=outzone,
        ZSwings=zswings, InZone=inzone, ZContacts=zcontacts, BB=bb,
        lineup_slot=lineup_slot, is_initial_lineup=True,
        wOBA_num=woba_num, wOBA_den=woba_den, xwOBA_num=xwoba_num,
        xBA_num=xba_num, xBA_den=xba_den, HardHit=hard_hit,
        Barrels=barrels, SweetSpot=sweet_spot, EV_num=ev_num, EV_den=ev_den,
        LA_num=la_num, LA_den=la_den, BABIP_num=babip_num,
        BABIP_den=babip_den, HR=hr, FB=fb, BIP=bip, PullAir=pull_air,
        RV_num=rv_num, RV_den=rv_den,
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


def test_extra_rate_stats_have_correct_whiff_and_swstr_denominators():
    df = br.add_leakage_safe_k(
        _games([
            _g(
                1, 4, 1, whiffs=10, swings=20, pitches=50,
                chases=6, outzone=20,
            ),
            _g(
                2, 4, 1, whiffs=0, swings=20, pitches=50,
                chases=0, outzone=20,
            ),
        ]),
        windows=(5,), shrink_pa=0,
    ).sort("game_date")
    # Game 2 uses only game 1.
    assert abs(df["swstr_rate_std"][1] - 10 / 50) < 1e-9
    assert abs(df["whiff_rate_std"][1] - 10 / 20) < 1e-9
    assert abs(df["chase_rate_std"][1] - 0.3) < 1e-9


def test_new_discipline_rates_are_season_to_date_and_rolling():
    df = br.add_leakage_safe_k(
        _games([
            _g(
                1,
                4,
                1,
                pitches=50,
                swings=20,
                inzone=25,
                zswings=15,
                zcontacts=12,
                bb=1,
            ),
            _g(
                2,
                4,
                1,
                pitches=50,
                swings=10,
                inzone=20,
                zswings=10,
                zcontacts=5,
                bb=0,
            ),
        ]),
        windows=(5,),
        shrink_pa=0,
    ).sort("game_date")

    assert df["zswing_rate_std"][1] == pytest.approx(15 / 25)
    assert df["swing_rate_std"][1] == pytest.approx(20 / 50)
    assert df["zcontact_rate_std"][1] == pytest.approx(12 / 15)
    assert df["bb_rate_std"][1] == pytest.approx(1 / 4)
    assert df["zswing_rate_P5"][1] == pytest.approx(15 / 25)
    assert df["swing_rate_P5"][1] == pytest.approx(20 / 50)
    assert df["zcontact_rate_P5"][1] == pytest.approx(12 / 15)
    assert df["bb_rate_P5"][1] == pytest.approx(1 / 4)


def test_contact_quality_rates_are_denominator_weighted_and_rolling():
    df = br.add_leakage_safe_k(
        _games(
            [
                _g(
                    1,
                    4,
                    1,
                    woba_num=1.2,
                    woba_den=4,
                    xwoba_num=1.6,
                    xba_num=1.5,
                    xba_den=3,
                    hard_hit=2,
                    barrels=1,
                    sweet_spot=2,
                    ev_num=285.0,
                    ev_den=3,
                    la_num=45.0,
                    la_den=3,
                    babip_num=1,
                    babip_den=3,
                    hr=1,
                    fb=2,
                    bip=3,
                    pull_air=1,
                    rv_num=0.4,
                    rv_den=20,
                ),
                _g(2, 4, 0),
            ]
        ),
        windows=(5,),
        shrink_pa=0,
    ).sort("game_date")
    assert df["wOBA_P5"][1] == pytest.approx(0.3)
    assert df["xwOBA_P5"][1] == pytest.approx(0.4)
    assert df["xBA_P5"][1] == pytest.approx(0.5)
    assert df["hard_hit_rate_P5"][1] == pytest.approx(2 / 3)
    assert df["barrel_rate_P5"][1] == pytest.approx(1 / 3)
    assert df["avg_exit_velocity_P5"][1] == pytest.approx(95.0)
    assert df["hr_fb_rate_P5"][1] == pytest.approx(0.5)
    assert df["pull_air_rate_P5"][1] == pytest.approx(1 / 3)
    assert df["rv_per_pitch_P5"][1] == pytest.approx(0.02)


def test_lineup_opportunity_weight_uses_prior_dates_only():
    games = _games(
        [
            _g(1, 5, 1, batter=1, gp=11, lineup_slot=1),
            _g(1, 3, 1, batter=2, gp=12, lineup_slot=9),
            _g(2, 4, 1, batter=1, gp=21, lineup_slot=1),
            _g(2, 4, 1, batter=2, gp=22, lineup_slot=9),
        ]
    )
    out = br.add_leakage_safe_k(games, windows=(5,), shrink_pa=0).sort(
        ["game_date", "lineup_slot"]
    )
    day_two = out.filter(pl.col("game_date") == dt.date(2024, 4, 2))
    assert day_two.filter(pl.col("lineup_slot") == 1)["lineup_pa_weight"][0] == 5
    assert day_two.filter(pl.col("lineup_slot") == 9)["lineup_pa_weight"][0] == 3


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
