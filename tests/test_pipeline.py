"""Tests for the three-level pipeline transforms (no raw Savant needed)."""

from __future__ import annotations

import datetime as dt

import polars as pl

from mlb_props.pipeline import rolling, training


def _pitcher_games():
    rows = []
    for day, k, pa in [(1, 8, 24), (2, 6, 22), (3, 5, 20)]:
        rows.append(dict(
            game_pk=day, game_date=dt.date(2024, 4, day), season=2024,
            pitcher=1, player_name="Doe, J", p_throws="R",
            home_team="AAA", away_team="BBB", is_home=True, opp_team="BBB",
            K=k, PA=pa, Outs=18, k_rate=k / pa,
            Whiffs=12, ff_velo=95.0,   # raw same-game columns -> should be dropped
        ))
    return pl.DataFrame(rows, schema_overrides={"game_date": pl.Date})


def _batter_games():
    rows = []
    for day, k, pa in [(1, 1, 4), (2, 2, 4), (3, 0, 4)]:
        rows.append(dict(
            game_pk=day, game_date=dt.date(2024, 4, day), season=2024,
            batter=100, stand="L", bat_team="BBB", home_team="AAA",
            away_team="BBB", is_home=False, opp_team="AAA",
            PA=pa, K=k, PA_vL=0, K_vL=0, PA_vR=pa, K_vR=k,
            Whiffs=5, Pitches=60, Chases=3, OutZone=20,  # raw -> dropped
        ))
    return pl.DataFrame(rows, schema_overrides={"game_date": pl.Date})


def _park_factors():
    return pl.DataFrame([dict(season=2024, home_team="AAA", park_k_factor=1.05)])


def test_level2_keeps_static_and_rolling_drops_raw():
    out = rolling.build_pitcher_rolling(_pitcher_games())
    # statics + labels retained
    for col in ("game_pk", "game_date", "home_team", "away_team", "opp_team", "k_rate", "PA"):
        assert col in out.columns
    # rolling produced
    assert "k_rate_std" in out.columns and "k_rate_P5" in out.columns
    # raw same-game feature columns dropped
    assert "Whiffs" not in out.columns and "ff_velo" not in out.columns


def test_level2_batter_keeps_join_keys():
    out = rolling.build_batter_rolling(_batter_games())
    for col in (
        "game_pk", "game_date", "bat_team", "home_team", "away_team",
        "is_home", "opp_team", "k_rate_std",
    ):
        assert col in out.columns
    assert "whiff_rate_std" in out.columns  # extra rate stat produced
    assert "Whiffs" not in out.columns      # raw dropped


def test_lineup_aggregation_uses_opponent_and_pitcher_hand():
    starts = pl.DataFrame(
        [dict(game_pk=1, pitcher=10, p_throws="R", opp_team="BBB")]
    )
    batters = pl.DataFrame(
        [
            dict(game_pk=1, bat_team="BBB", k_rate_std=0.30, k_rate_std_vL=0.50,
                 k_rate_std_vR=0.40, whiff_rate_std=0.12, chase_rate_std=0.28),
            dict(game_pk=1, bat_team="BBB", k_rate_std=0.10, k_rate_std_vL=0.50,
                 k_rate_std_vR=0.20, whiff_rate_std=0.08, chase_rate_std=0.32),
            dict(game_pk=1, bat_team="AAA", k_rate_std=0.99, k_rate_std_vL=0.99,
                 k_rate_std_vR=0.99, whiff_rate_std=0.99, chase_rate_std=0.99),
        ]
    )
    out = training.opposing_lineup_features(starts, batters).row(0, named=True)
    assert abs(out["opp_lineup_k"] - 0.20) < 1e-9
    assert abs(out["opp_lineup_k_vs_hand"] - 0.30) < 1e-9
    assert abs(out["opp_lineup_whiff"] - 0.10) < 1e-9
    assert abs(out["opp_lineup_chase"] - 0.30) < 1e-9


def test_level3_pitcher_training_joins_lineup_and_park():
    pr = rolling.build_pitcher_rolling(_pitcher_games())
    br = rolling.build_batter_rolling(_batter_games())
    out = training.build_pitcher_training(pr, br, _park_factors())
    assert out.height == pr.height
    assert "opp_lineup_k" in out.columns
    assert "opp_lineup_k_vs_hand" in out.columns
    assert "park_k_factor" in out.columns
    assert out["park_k_factor"][0] == 1.05


def test_level3_batter_training_joins_park():
    br = rolling.build_batter_rolling(_batter_games())
    out = training.build_batter_training(br, _park_factors())
    assert "park_k_factor" in out.columns
    assert out["park_k_factor"][0] == 1.05


def test_round_trip_parquet(tmp_path):
    path = tmp_path / "pitcher_rolling.parquet"
    df = rolling.build_pitcher_rolling(_pitcher_games())
    df.write_parquet(path)
    assert pl.read_parquet(path).equals(df)
