"""Tests for the pitch-level -> per-batter-per-game builder."""

from __future__ import annotations

import datetime as dt

import polars as pl

from Python import batter_features as bf


def _pitch(**over):
    base = dict(
        game_pk=5000, game_date=dt.date(2024, 4, 1), batter=100, stand="L",
        p_throws="R", home_team="AAA", away_team="BBB", inning_topbot="Top",
        at_bat_number=1,
        events=None, description="hit_into_play", type="X", zone=5,
        estimated_woba_using_speedangle=None, woba_value=0.0, woba_denom=1,
    )
    base.update(over)
    return base


def _frame(rows):
    return pl.DataFrame(rows, schema_overrides={"game_date": pl.Date})


def test_batter_line_and_hand_splits():
    rows = [
        _pitch(p_throws="L", type="S", description="swinging_strike", events="strikeout"),
        _pitch(p_throws="R", type="X", description="hit_into_play", events="single"),
    ]
    out = bf.build_batter_games(_frame(rows)).row(0, named=True)
    assert out["PA"] == 2
    assert out["K"] == 1
    assert out["Hits"] == 1
    assert out["K_vL"] == 1 and out["PA_vL"] == 1
    assert out["K_vR"] == 0 and out["PA_vR"] == 1
    # Top of the inning -> the away team is batting.
    assert out["bat_team"] == "BBB"
    assert out["home_team"] == "AAA" and out["away_team"] == "BBB"
    assert out["is_home"] is False and out["opp_team"] == "AAA"


def test_batter_plate_discipline():
    rows = [
        _pitch(zone=5, type="S", description="swinging_strike", events="strikeout"),   # Z-swing, whiff
        _pitch(zone=13, type="X", description="hit_into_play", events="single"),        # chase, contact
        _pitch(zone=12, type="B", description="ball", events="walk"),                   # out-of-zone take
    ]
    out = bf.build_batter_games(_frame(rows)).row(0, named=True)
    assert out["Swings"] == 2 and out["Chases"] == 1 and out["ZSwings"] == 1
    assert out["OutZone"] == 2 and out["InZone"] == 1
    assert abs(out["chase_rate"] - 0.5) < 1e-9      # 1 chase / 2 out-of-zone
    assert abs(out["contact_rate"] - 0.5) < 1e-9    # 1 contact / 2 swings


def test_one_row_per_batter_game():
    rows = [
        _pitch(batter=100, events="strikeout", type="S", description="swinging_strike"),
        _pitch(batter=100, events="walk", type="B", description="ball"),
        _pitch(batter=200, events="single"),
    ]
    out = bf.build_batter_games(_frame(rows))
    assert out.height == 2
    b100 = out.filter(pl.col("batter") == 100).row(0, named=True)
    assert b100["PA"] == 2 and b100["K"] == 1 and b100["BB"] == 1


def test_first_nine_batters_are_marked_as_initial_lineup():
    rows = [
        _pitch(batter=100 + n, at_bat_number=n, events="field_out")
        for n in range(1, 11)
    ]
    out = bf.build_batter_games(_frame(rows)).sort("batter")
    assert out["is_initial_lineup"].to_list() == [True] * 9 + [False]
