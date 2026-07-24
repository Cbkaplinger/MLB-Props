"""Tests for the pitch-level -> per-start pitcher builder."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest
import Python.config as config

from Python import pitcher_features as pf


def _pitch(**over):
    """One pitch row with sensible defaults; override fields via kwargs."""
    base = dict(
        game_pk=5000, game_date=dt.date(2024, 4, 1), player_name="Test, Ace",
        pitcher=1, stand="R", p_throws="R", home_team="AAA", away_team="BBB",
        inning=1, inning_topbot="Top", at_bat_number=1, pitch_number=1,
        pitch_type="FF", type="X", description="hit_into_play", events=None,
        bb_type=None, release_speed=94.0, release_spin_rate=2300.0,
        pfx_x=-0.5, pfx_z=1.2, vy0=-130.0, vz0=-5.0, ay=27.0, az=-15.0,
        release_extension=6.5, release_pos_x=-1.5, release_pos_z=5.8,
        estimated_ba_using_speedangle=None, estimated_woba_using_speedangle=None,
        woba_value=0.0, woba_denom=1, bat_score=0, post_bat_score=0, zone=5,
    )
    base.update(over)
    return base


def _frame(rows):
    return pl.DataFrame(rows, schema_overrides={"game_date": pl.Date})


def test_starter_identified_and_reliever_excluded():
    rows = [
        # starter (pitcher 1) faces three batters
        _pitch(at_bat_number=1, type="S", description="swinging_strike", events="strikeout"),
        _pitch(at_bat_number=2, type="B", description="ball", events="walk"),
        _pitch(at_bat_number=3, inning=2, type="X", description="hit_into_play", events="single"),
        # reliever (pitcher 2) enters in the 6th, never pitched the 1st
        _pitch(pitcher=2, player_name="Test, Pen", inning=6, at_bat_number=20,
               type="X", events="field_out"),
    ]
    out = pf.build_pitcher_starts(_frame(rows), min_batters_faced=0)
    assert out.height == 1
    assert out["pitcher"][0] == 1


def test_outcome_counts():
    rows = [
        _pitch(at_bat_number=1, type="S", description="swinging_strike", events="strikeout"),
        _pitch(at_bat_number=2, type="B", description="ball", events="walk"),
        _pitch(at_bat_number=3, inning=2, type="X", description="hit_into_play",
               events="single", bb_type="ground_ball"),
    ]
    out = pf.build_pitcher_starts(_frame(rows), min_batters_faced=0).row(0, named=True)
    assert out["PA"] == 3
    assert out["K"] == 1
    assert out["BB"] == 1
    assert out["Hits"] == 1
    assert out["Pitches"] == 3
    assert out["Strikes"] == 1 and out["Balls"] == 1 and out["BIP"] == 1
    assert out["Whiffs"] == 1 and out["CS"] == 0
    assert out["CSW"] == out["CS"] + out["Whiffs"]
    assert out["GB"] == 1


def test_caught_stealing_and_pickoff_count_as_outs():
    rows = [
        _pitch(at_bat_number=1, type="X", description="hit_into_play", events="field_out"),
        # a caught stealing and a pickoff during the starter's outing -> +2 outs, 0 PA
        _pitch(at_bat_number=1, pitch_number=2, type="S", description="ball",
               events="caught_stealing_2b"),
        _pitch(at_bat_number=2, type="S", description="ball", events="pickoff_1b"),
    ]
    out = pf.build_pitcher_starts(_frame(rows), min_batters_faced=0).row(0, named=True)
    assert out["PA"] == 1          # baserunning events are not plate appearances
    assert out["Outs"] == 3        # 1 field_out + caught_stealing + pickoff


def test_plate_discipline_counts_and_rates():
    rows = [
        _pitch(at_bat_number=1, zone=5, type="S", description="swinging_strike", events="strikeout"),
        _pitch(at_bat_number=1, zone=13, pitch_number=2, type="X", description="hit_into_play",
               events="single"),   # chase (out of zone) that made contact
    ]
    out = pf.build_pitcher_starts(_frame(rows), min_batters_faced=0).row(0, named=True)
    assert out["Swings"] == 2 and out["Chases"] == 1
    assert out["ZSwings"] == 1 and out["Contacts"] == 1
    assert abs(out["chase_rate"] - 1.0) < 1e-9      # 1 chase / 1 out-of-zone pitch
    assert abs(out["contact_rate"] - 0.5) < 1e-9    # 1 contact / 2 swings
    assert abs(out["zone_rate"] - 0.5) < 1e-9       # 1 in-zone / 2 pitches


def test_popup_counts_as_fly_ball():
    rows = [_pitch(at_bat_number=1, type="X", description="hit_into_play",
                   events="field_out", bb_type="popup")]
    out = pf.build_pitcher_starts(_frame(rows), min_batters_faced=0).row(0, named=True)
    assert out["FB"] == 1


def test_home_starter_faces_away_lineup():
    # Defaults: inning_topbot="Top", home="AAA", away="BBB". The Top-inning
    # pitcher is the home team, so he faces the away lineup.
    rows = [
        _pitch(at_bat_number=1, type="X", description="hit_into_play", events="field_out"),
    ]
    out = pf.build_pitcher_starts(_frame(rows), min_batters_faced=0).row(0, named=True)
    assert out["is_home"] is True
    assert out["opp_team"] == "BBB"


def test_foul_tip_counts_as_whiff():
    rows = [
        _pitch(at_bat_number=1, type="S", description="foul_tip", events="strikeout"),
    ]
    out = pf.build_pitcher_starts(_frame(rows), min_batters_faced=0).row(0, named=True)
    assert out["Whiffs"] == 1
    assert out["CSW"] == 1


def test_opener_and_early_exit_filtered_out():
    # Pitcher faces only 4 batters -> dropped when min_batters_faced=9.
    rows = [
        _pitch(at_bat_number=n, type="X", description="hit_into_play", events="field_out")
        for n in range(1, 5)
    ]
    assert pf.build_pitcher_starts(_frame(rows), min_batters_faced=9).height == 0
    assert pf.build_pitcher_starts(_frame(rows), min_batters_faced=0).height == 1


def test_per_pitch_woba_allowed():
    # Two PAs ending on a four-seam: a strikeout (woba 0) and a HR (woba ~2.0).
    rows = [
        _pitch(at_bat_number=1, pitch_type="FF", type="S",
               description="swinging_strike", events="strikeout",
               woba_value=0.0, woba_denom=1),
        _pitch(at_bat_number=2, pitch_type="FF", type="X",
               description="hit_into_play", events="home_run",
               bb_type="fly_ball", woba_value=2.0, woba_denom=1,
               estimated_woba_using_speedangle=1.8),
    ]
    out = pf.build_pitcher_starts(_frame(rows), min_batters_faced=0).row(0, named=True)
    assert abs(out["ff_woba"] - 1.0) < 1e-9       # (0 + 2.0) / 2
    assert abs(out["ff_xwoba"] - 0.9) < 1e-9      # (0 + 1.8) / 2


def test_fip_xfip_added():
    rows = [
        _pitch(at_bat_number=n, type="X", description="hit_into_play", events="field_out")
        for n in range(1, 12)
    ]
    starts = pf.build_pitcher_starts(_frame(rows), min_batters_faced=9)
    out = pf.add_fip_xfip(starts)
    assert "FIP" in out.columns and "xFIP" in out.columns
    assert out["season"][0] == 2024


def _fip_start(**over):
    """A synthetic per-start row with just the columns add_fip_xfip reads."""
    base = dict(season=2024, Outs=27, HR=1, BB=2, HBP=0, K=9, FB=10, Runs=4)
    base.update(over)
    return base


def test_fip_core_only_when_constant_disabled():
    out = pf.add_fip_xfip(pl.DataFrame([_fip_start()]), include_constant=False).row(0, named=True)
    # core = (13*1 + 3*(2+0) - 2*9) / 9 IP = 1/9
    assert abs(out["FIP"] - (1.0 / 9.0)) < 1e-9
    assert abs(out["xFIP"] - (1.0 / 9.0)) < 1e-9   # FB*lgHR/FB == HR here


def test_fip_uses_published_constant_by_default():
    # Default constant for 2024 is FanGraphs cFIP = 3.166.
    out = pf.add_fip_xfip(pl.DataFrame([_fip_start()])).row(0, named=True)
    assert abs(out["FIP"] - (1.0 / 9.0 + 3.166)) < 1e-6
    assert pf.FANGRAPHS_FIP_CONSTANT[2024] == 3.166


def test_fip_constant_and_hr_fb_overrides():
    out = pf.add_fip_xfip(
        pl.DataFrame([_fip_start(FB=20, HR=1)]),
        fip_constant={2024: 3.50},
        league_hr_fb={2024: 0.12},
    ).row(0, named=True)
    assert abs(out["FIP"] - (1.0 / 9.0 + 3.50)) < 1e-6
    xcore = (13 * (20 * 0.12) + 3 * 2 - 2 * 9) / 9.0
    assert abs(out["xFIP"] - (xcore + 3.50)) < 1e-6


def test_league_hr_fb_from_pitches_uses_all_pitchers():
    rows = [
        # a reliever's fly ball + HR must count toward the league rate
        _pitch(pitcher=99, inning=8, bb_type="fly_ball", events="home_run", type="X"),
        _pitch(pitcher=99, inning=8, bb_type="fly_ball", events="field_out", type="X"),
    ]
    hr_fb = pf.league_hr_fb_from_pitches(_frame(rows))
    assert abs(hr_fb[2024] - 0.5) < 1e-9   # 1 HR / 2 FB


def test_prior_date_league_hr_fb_uses_prior_season_and_prior_dates():
    rows = [
        _pitch(game_date=dt.date(2023, 4, 1), events="home_run", bb_type="fly_ball"),
        _pitch(game_date=dt.date(2023, 4, 2), events="field_out", bb_type="fly_ball"),
        _pitch(game_date=dt.date(2024, 4, 1), events="field_out", bb_type="fly_ball"),
        _pitch(game_date=dt.date(2024, 4, 2), events="field_out", bb_type="fly_ball"),
    ]
    rates = pf.prior_date_league_hr_fb(
        _frame(rows),
        prior_strength_fb=2.0,
    ).sort("game_date")
    first_loaded = rates.filter(pl.col("game_date") == dt.date(2023, 4, 1))
    april_1 = rates.filter(pl.col("game_date") == dt.date(2024, 4, 1))
    april_2 = rates.filter(pl.col("game_date") == dt.date(2024, 4, 2))
    assert first_loaded["lg_hr_fb_prior"][0] is None
    assert april_1["lg_hr_fb_prior"][0] == pytest.approx(0.5)
    assert april_2["lg_hr_fb_prior"][0] == pytest.approx(1 / 3)


def test_vaa_sign_is_negative():
    # A normal downward-breaking fastball should have a negative approach angle.
    out = pf.build_pitcher_starts(_frame([_pitch(at_bat_number=1, events="field_out")]),
                                  min_batters_faced=0)
    assert out["ff_vaa"][0] is not None and out["ff_vaa"][0] < 0

def test_default_population_requires_nine_batters_faced():
    assert config.MIN_STARTER_BATTERS_FACED == 9
