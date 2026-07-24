"""Tests for the three-level pipeline transforms (no raw Savant needed)."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from Python.pipeline import games, rolling, training


def _pitcher_games():
    rows = []
    for day, k, pa in [(1, 8, 24), (2, 6, 22), (3, 5, 20)]:
        rows.append(dict(
            game_pk=day, game_date=dt.date(2024, 4, day), season=2024,
            pitcher=1, player_name="Doe, J", pitcher_name="J Doe", p_throws="R",
            home_team="AAA", away_team="BBB", is_home=True, opp_team="BBB",
            K=k, PA=pa, Outs=18, k_rate=k / pa,
            Whiffs=12, ff_velo=95.0,   # raw same-game columns -> should be dropped
        ))
    return pl.DataFrame(rows, schema_overrides={"game_date": pl.Date})


def _batter_games():
    rows = []
    for day, k, pa in [(1, 1, 4), (2, 2, 4), (3, 0, 4)]:
        for batter in range(100, 109):
            rows.append(dict(
                game_pk=day, game_date=dt.date(2024, 4, day), season=2024,
                batter=batter, batter_name=f"Hitter {batter}", stand="L",
                bat_team="BBB", home_team="AAA", away_team="BBB",
                is_home=False, opp_team="AAA", is_initial_lineup=True,
                PA=pa, K=k, PA_vL=0, K_vL=0, PA_vR=pa, K_vR=k,
                Whiffs=5, Swings=20, Pitches=60,
                Chases=3, OutZone=20,  # raw -> dropped
            ))
    return pl.DataFrame(rows, schema_overrides={"game_date": pl.Date})


def _park_factors():
    return pl.DataFrame([dict(season=2024, home_team="AAA", park_k_factor=1.05)])


def test_level1_validates_requested_season_game_ids(monkeypatch):
    raw = pl.DataFrame(
        {
            "game_pk": [100],
            "game_date": [dt.date(2025, 4, 1)],
            "game_year": [2025],
        },
        schema_overrides={"game_date": pl.Date},
    )
    monkeypatch.setattr(
        games,
        "regular_season_schedule",
        lambda _year: (
            dt.date(2025, 3, 18),
            dt.date(2025, 9, 28),
            frozenset({100}),
        ),
    )

    games._validate_raw_seasons(raw, (2025,))


def test_level1_park_factors_use_prior_only_history():
    def pitch(year, game_pk, home_team, event):
        return {
            "game_pk": game_pk,
            "game_date": dt.date(year, 4, 1),
            "home_team": home_team,
            "at_bat_number": game_pk,
            "pitch_number": 1,
            "events": event,
        }

    prior = pl.DataFrame(
        [
            pitch(2022, 1, "AAA", "strikeout"),
            pitch(2022, 2, "BBB", "field_out"),
        ],
        schema_overrides={"game_date": pl.Date},
    )
    current = pl.DataFrame(
        [
            pitch(2023, 3, "AAA", "field_out"),
            pitch(2023, 4, "BBB", "strikeout"),
        ],
        schema_overrides={"game_date": pl.Date},
    )

    out = games.build_park_factors(current, (2023,), prior)
    factors = out.filter(pl.col("season") == 2023)
    assert factors.filter(pl.col("home_team") == "AAA")["park_k_factor"][0] > 1
    assert factors.filter(pl.col("home_team") == "BBB")["park_k_factor"][0] < 1


def test_level2_keeps_static_and_rolling_drops_raw():
    out = rolling.build_pitcher_rolling(_pitcher_games())
    # statics + labels retained
    for col in (
        "game_pk", "game_date", "player_name", "pitcher_name", "home_team",
        "away_team", "opp_team", "k_rate", "PA",
    ):
        assert col in out.columns
    # rolling produced
    assert "k_rate_std" in out.columns and "k_rate_P5" in out.columns
    # raw same-game feature columns dropped
    assert "Whiffs" not in out.columns and "ff_velo" not in out.columns


def test_level2_batter_keeps_join_keys():
    out = rolling.build_batter_rolling(_batter_games())
    for col in (
        "game_pk", "game_date", "batter_name", "bat_team", "home_team", "away_team",
        "is_home", "opp_team", "k_rate_std",
    ):
        assert col in out.columns
    assert "whiff_rate_std" in out.columns  # whiffs / swings
    assert "swstr_rate_std" in out.columns  # whiffs / pitches
    assert "Whiffs" not in out.columns      # raw dropped


def test_lineup_aggregation_uses_opponent_and_pitcher_hand():
    starts = pl.DataFrame(
        [dict(game_pk=1, pitcher=10, p_throws="R", opp_team="BBB")]
    )
    batters = pl.DataFrame(
        [
            dict(game_pk=1, batter=1, bat_team="BBB", is_initial_lineup=True,
                 k_rate_std=0.30, k_rate_std_vL=0.50,
                 k_rate_std_vR=0.40, whiff_rate_std=0.25,
                 swstr_rate_std=0.12, chase_rate_std=0.28),
            dict(game_pk=1, batter=2, bat_team="BBB", is_initial_lineup=True,
                 k_rate_std=0.10, k_rate_std_vL=0.50,
                 k_rate_std_vR=0.20, whiff_rate_std=0.15,
                 swstr_rate_std=0.08, chase_rate_std=0.32),
            dict(game_pk=1, batter=3, bat_team="AAA", is_initial_lineup=True,
                 k_rate_std=0.99, k_rate_std_vL=0.99,
                 k_rate_std_vR=0.99, whiff_rate_std=0.99,
                 swstr_rate_std=0.99, chase_rate_std=0.99),
            dict(game_pk=1, batter=4, bat_team="BBB", is_initial_lineup=False,
                 k_rate_std=0.99, k_rate_std_vL=0.99,
                 k_rate_std_vR=0.99, whiff_rate_std=0.99,
                 swstr_rate_std=0.99, chase_rate_std=0.99),
        ]
    )
    out = training.opposing_lineup_features(starts, batters).row(0, named=True)
    assert abs(out["opp_lineup_k"] - 0.20) < 1e-9
    assert abs(out["opp_lineup_k_vs_hand"] - 0.30) < 1e-9
    assert abs(out["opp_lineup_whiff"] - 0.20) < 1e-9
    assert abs(out["opp_lineup_swstr"] - 0.10) < 1e-9
    assert abs(out["opp_lineup_chase"] - 0.30) < 1e-9
    assert out["opp_lineup_size"] == 2


def test_lineup_aggregation_preserves_season_opening_nulls():
    starts = pl.DataFrame(
        [dict(game_pk=1, pitcher=10, p_throws="R", opp_team="BBB")]
    )
    batters = pl.DataFrame(
        [
            dict(
                game_pk=1,
                batter=1,
                bat_team="BBB",
                is_initial_lineup=True,
                k_rate_std=None,
                k_rate_std_vL=None,
                k_rate_std_vR=None,
                whiff_rate_std=None,
                swstr_rate_std=None,
                chase_rate_std=None,
            )
        ],
        schema_overrides={
            "k_rate_std": pl.Float64,
            "k_rate_std_vL": pl.Float64,
            "k_rate_std_vR": pl.Float64,
            "whiff_rate_std": pl.Float64,
            "swstr_rate_std": pl.Float64,
            "chase_rate_std": pl.Float64,
        },
    )

    out = training.opposing_lineup_features(starts, batters)
    assert out["opp_lineup_k"][0] is None
    assert out["opp_lineup_k_vs_hand"][0] is None
    assert out["opp_lineup_whiff"][0] is None
    assert out["opp_lineup_swstr"][0] is None
    assert out["opp_lineup_chase"][0] is None


def test_pitcher_training_rejects_duplicate_lineup_keys(monkeypatch):
    pr = rolling.build_pitcher_rolling(_pitcher_games())
    br = rolling.build_batter_rolling(_batter_games())
    lineup = training.opposing_lineup_features(pr, br)
    duplicated = pl.concat([lineup, lineup.head(1)])
    monkeypatch.setattr(
        training,
        "opposing_lineup_features",
        lambda *_args: duplicated,
    )

    with pytest.raises(ValueError, match="duplicate"):
        training.build_pitcher_training(pr, br)


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


def test_level3_rejects_missing_park_season():
    pr = rolling.build_pitcher_rolling(_pitcher_games())
    br = rolling.build_batter_rolling(_batter_games())
    wrong_season = pl.DataFrame(
        [dict(season=2023, home_team="AAA", park_k_factor=1.05)]
    )

    with pytest.raises(ValueError, match="missing rolling-data seasons"):
        training.build_pitcher_training(pr, br, wrong_season)


def test_level3_rejects_missing_park_team_key():
    br = rolling.build_batter_rolling(_batter_games())
    wrong_team = pl.DataFrame(
        [dict(season=2024, home_team="BBB", park_k_factor=1.05)]
    )

    with pytest.raises(ValueError, match=r"missing \(season, home_team\) keys"):
        training.build_batter_training(br, wrong_team)


def test_level3_rejects_duplicate_park_keys():
    pr = rolling.build_pitcher_rolling(_pitcher_games())
    br = rolling.build_batter_rolling(_batter_games())
    duplicated = pl.concat([_park_factors(), _park_factors()])

    with pytest.raises(ValueError, match="duplicate"):
        training.build_pitcher_training(pr, br, duplicated)


def test_level3_run_requires_park_dimension(tmp_path, monkeypatch):
    pitcher_path = tmp_path / "pitcher_rolling.parquet"
    batter_path = tmp_path / "batter_rolling.parquet"
    rolling.build_pitcher_rolling(_pitcher_games()).write_parquet(pitcher_path)
    rolling.build_batter_rolling(_batter_games()).write_parquet(batter_path)

    monkeypatch.setattr(training.config, "PITCHER_ROLLING_PATH", pitcher_path)
    monkeypatch.setattr(training.config, "BATTER_ROLLING_PATH", batter_path)
    monkeypatch.setattr(
        training.config,
        "PARK_FACTORS_PATH",
        tmp_path / "missing_park_factors.parquet",
    )

    with pytest.raises(FileNotFoundError, match="Missing park-factor dimension"):
        training.run()


def test_round_trip_parquet(tmp_path):
    path = tmp_path / "pitcher_rolling.parquet"
    df = rolling.build_pitcher_rolling(_pitcher_games())
    df.write_parquet(path)
    assert pl.read_parquet(path).equals(df)
