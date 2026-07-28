"""Tests for Phase C bullpen team aggregates and lookbacks."""

from __future__ import annotations

import datetime as dt

import polars as pl

from Python.bullpen import (
    add_bullpen_lookback_features,
    build_bullpen_appearances,
    build_bullpen_team_games,
    bullpen_lookback_column_names,
)


def _pitch(
    *,
    game_pk: int,
    day: int,
    pitcher: int,
    team_side: str,
    p_throws: str = "R",
    home: str = "AAA",
    away: str = "BBB",
    inning: int = 1,
    n: int = 1,
) -> list[dict]:
    """``team_side`` is 'home' or 'away' (who is pitching)."""
    topbot = "Top" if team_side == "home" else "Bot"
    return [
        {
            "game_pk": game_pk,
            "game_date": dt.date(2024, 4, day),
            "pitcher": pitcher,
            "p_throws": p_throws,
            "home_team": home,
            "away_team": away,
            "inning": inning,
            "inning_topbot": topbot,
            "at_bat_number": i,
            "pitch_number": 1,
        }
        for i in range(n)
    ]


def test_build_bullpen_excludes_starters_hand_and_zeros_cg():
    # Game 1: home starter 10, L reliever 20 (3), R reliever 21 (30 heavy)
    #         away starter 30, no away bullpen
    rows = []
    rows += _pitch(game_pk=1, day=1, pitcher=10, team_side="home", n=5)
    rows += _pitch(
        game_pk=1, day=1, pitcher=20, team_side="home", p_throws="L", inning=6, n=3
    )
    rows += _pitch(
        game_pk=1, day=1, pitcher=21, team_side="home", p_throws="R", inning=7, n=30
    )
    rows += _pitch(game_pk=1, day=1, pitcher=30, team_side="away", n=4)
    raw = pl.DataFrame(rows, schema_overrides={"game_date": pl.Date})

    out = build_bullpen_team_games(raw).sort(["team", "game_pk"])
    home = out.filter(pl.col("team") == "AAA")
    away = out.filter(pl.col("team") == "BBB")
    assert home["bullpen_pitches"][0] == 33
    assert home["bullpen_pitchers_used"][0] == 2
    assert home["bullpen_appearances"][0] == 2
    assert home["bullpen_L_pitches"][0] == 3
    assert home["bullpen_R_pitches"][0] == 30
    assert home["bullpen_max_pitches"][0] == 30
    assert home["bullpen_heavy_outings"][0] == 1
    assert away["bullpen_pitches"][0] == 0
    assert away["bullpen_pitchers_used"][0] == 0

    apps = build_bullpen_appearances(raw)
    assert apps.height == 2
    assert set(apps["pitcher"].to_list()) == {20, 21}


def test_bullpen_lookback_excludes_same_game_and_fills_zero():
    bullpen = pl.DataFrame(
        [
            {
                "game_pk": 1,
                "game_date": dt.date(2024, 4, 1),
                "team": "AAA",
                "bullpen_pitches": 40,
                "bullpen_pitchers_used": 2,
                "bullpen_appearances": 2,
                "bullpen_L_pitches": 10,
                "bullpen_R_pitches": 30,
                "bullpen_b2b_arms": 0,
                "bullpen_max_pitches": 25,
                "bullpen_heavy_outings": 0,
                "season": 2024,
            },
            {
                "game_pk": 2,
                "game_date": dt.date(2024, 4, 2),
                "team": "AAA",
                "bullpen_pitches": 25,
                "bullpen_pitchers_used": 1,
                "bullpen_appearances": 1,
                "bullpen_L_pitches": 0,
                "bullpen_R_pitches": 25,
                "bullpen_b2b_arms": 1,
                "bullpen_max_pitches": 25,
                "bullpen_heavy_outings": 0,
                "season": 2024,
            },
            {
                "game_pk": 3,
                "game_date": dt.date(2024, 4, 3),
                "team": "AAA",
                "bullpen_pitches": 99,
                "bullpen_pitchers_used": 4,
                "bullpen_appearances": 4,
                "bullpen_L_pitches": 40,
                "bullpen_R_pitches": 59,
                "bullpen_b2b_arms": 2,
                "bullpen_max_pitches": 40,
                "bullpen_heavy_outings": 1,
                "season": 2024,
            },
        ],
        schema_overrides={"game_date": pl.Date},
    )
    starts = pl.DataFrame(
        [
            {
                "game_pk": 3,
                "game_date": dt.date(2024, 4, 3),
                "pitcher": 10,
                "home_team": "AAA",
                "away_team": "BBB",
                "is_home": True,
            },
            {
                "game_pk": 4,
                "game_date": dt.date(2024, 4, 10),
                "pitcher": 10,
                "home_team": "AAA",
                "away_team": "BBB",
                "is_home": True,
            },
        ],
        schema_overrides={"game_date": pl.Date},
    )

    out = add_bullpen_lookback_features(starts, bullpen).sort("game_date")
    # Apr 3 start: prior window includes Apr 1–2 only (not same-day 99).
    assert out["bullpen_pitches_L1d"][0] == 25
    assert out["bullpen_pitchers_used_L1d"][0] == 1
    assert out["bullpen_L_pitches_L2d"][0] == 10
    assert out["bullpen_R_pitches_L2d"][0] == 55
    assert out["bullpen_b2b_arms_L2d"][0] == 1
    assert out["bullpen_max_pitches_L2d"][0] == 25
    assert out["bullpen_pitches_L3d"][0] == 65
    # Apr 10: no team games in prior 3 days → zeros
    assert out["bullpen_pitches_L3d"][1] == 0
    assert out["bullpen_unique_arms_L3d"][1] == 0
    assert "pitcher_team" not in out.columns


def test_bullpen_unique_arms_from_appearances():
    bullpen = pl.DataFrame(
        [
            {
                "game_pk": 1,
                "game_date": dt.date(2024, 4, 1),
                "team": "AAA",
                "bullpen_pitches": 20,
                "bullpen_pitchers_used": 1,
                "bullpen_appearances": 1,
                "bullpen_L_pitches": 0,
                "bullpen_R_pitches": 20,
                "bullpen_b2b_arms": 0,
                "bullpen_max_pitches": 20,
                "bullpen_heavy_outings": 0,
            },
            {
                "game_pk": 2,
                "game_date": dt.date(2024, 4, 2),
                "team": "AAA",
                "bullpen_pitches": 15,
                "bullpen_pitchers_used": 1,
                "bullpen_appearances": 1,
                "bullpen_L_pitches": 0,
                "bullpen_R_pitches": 15,
                "bullpen_b2b_arms": 1,
                "bullpen_max_pitches": 15,
                "bullpen_heavy_outings": 0,
            },
        ],
        schema_overrides={"game_date": pl.Date},
    )
    # Same arm both days → unique=1, pitchers_used sum=2
    appearances = pl.DataFrame(
        [
            {
                "game_pk": 1,
                "game_date": dt.date(2024, 4, 1),
                "team": "AAA",
                "pitcher": 50,
                "p_throws": "R",
                "pitches": 20,
                "season": 2024,
            },
            {
                "game_pk": 2,
                "game_date": dt.date(2024, 4, 2),
                "team": "AAA",
                "pitcher": 50,
                "p_throws": "R",
                "pitches": 15,
                "season": 2024,
            },
        ],
        schema_overrides={"game_date": pl.Date},
    )
    starts = pl.DataFrame(
        [
            {
                "game_pk": 3,
                "game_date": dt.date(2024, 4, 3),
                "pitcher": 10,
                "home_team": "AAA",
                "away_team": "BBB",
                "is_home": True,
            }
        ],
        schema_overrides={"game_date": pl.Date},
    )
    out = add_bullpen_lookback_features(
        starts, bullpen, appearances=appearances
    )
    assert out["bullpen_pitchers_used_L2d"][0] == 2
    assert out["bullpen_unique_arms_L2d"][0] == 1
    assert out["bullpen_b2b_arms_L2d"][0] == 1


def test_bullpen_lookback_uses_pitcher_team_not_opp():
    bullpen = pl.DataFrame(
        [
            {
                "game_pk": 1,
                "game_date": dt.date(2024, 4, 1),
                "team": "BBB",
                "bullpen_pitches": 50,
                "bullpen_pitchers_used": 3,
                "bullpen_appearances": 3,
                "bullpen_L_pitches": 20,
                "bullpen_R_pitches": 30,
                "bullpen_b2b_arms": 0,
                "bullpen_max_pitches": 20,
                "bullpen_heavy_outings": 0,
            },
            {
                "game_pk": 2,
                "game_date": dt.date(2024, 4, 1),
                "team": "AAA",
                "bullpen_pitches": 10,
                "bullpen_pitchers_used": 1,
                "bullpen_appearances": 1,
                "bullpen_L_pitches": 10,
                "bullpen_R_pitches": 0,
                "bullpen_b2b_arms": 0,
                "bullpen_max_pitches": 10,
                "bullpen_heavy_outings": 0,
            },
        ],
        schema_overrides={"game_date": pl.Date},
    )
    starts = pl.DataFrame(
        [
            {
                "game_pk": 3,
                "game_date": dt.date(2024, 4, 2),
                "pitcher": 99,
                "home_team": "AAA",
                "away_team": "BBB",
                "is_home": False,
            }
        ],
        schema_overrides={"game_date": pl.Date},
    )
    out = add_bullpen_lookback_features(starts, bullpen)
    assert out["bullpen_pitches_L1d"][0] == 50
    assert out["bullpen_L_pitches_L1d"][0] == 20


def test_bullpen_lookback_column_names_cover_metrics():
    names = bullpen_lookback_column_names((1, 3))
    assert "bullpen_pitches_L1d" in names
    assert "bullpen_unique_arms_L3d" in names
    assert "bullpen_b2b_arms_L1d" in names
    assert "bullpen_pitches_L2d" not in names
