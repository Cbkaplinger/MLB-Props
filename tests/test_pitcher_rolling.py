"""Tests for leakage-safe rolling / season-to-date pitcher features."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from Python import pitcher_rolling as pr


def _starts(rows):
    return pl.DataFrame(rows, schema_overrides={"game_date": pl.Date})


def _s(day, k, pa, *, pitcher=1, gp=None, year=2024, ff_velo=95.0, pitches=90, **over):
    row = dict(
        pitcher=pitcher,
        game_pk=gp if gp is not None else day,
        game_date=dt.date(year, 4, day),
        K=k, PA=pa, Pitches=pitches, ff_velo=ff_velo,
    )
    row.update(over)
    return row


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


def test_pitcher_whiff_swstr_and_ball_rate_names_match_denominators():
    df = pr.add_rolling_pitcher_features(
        _starts(
            [
                _s(
                    1, 5, 20, Whiffs=9, Swings=30, Balls=36, pitches=90,
                ),
                _s(
                    2, 5, 20, Whiffs=0, Swings=20, Balls=20, pitches=80,
                ),
            ]
        ),
        rate_stats={
            "whiff_rate": ("Whiffs", "Swings"),
            "swstr_rate": ("Whiffs", "Pitches"),
            "ball_rate": ("Balls", "Pitches"),
        },
        mean_cols=[],
        rate_windows=(5,),
    ).sort("game_date")
    assert df["whiff_rate_std"][1] == pytest.approx(9 / 30)
    assert df["swstr_rate_std"][1] == pytest.approx(9 / 90)
    assert df["ball_rate_std"][1] == pytest.approx(36 / 90)


def test_mean_column_rolls_and_shifts():
    df = pr.add_rolling_pitcher_features(
        _starts([_s(1, 0, 20, ff_velo=96.0), _s(2, 0, 20, ff_velo=94.0)]),
        rate_stats={}, mean_cols=["ff_velo"], mean_windows=(5,),
    ).sort("game_date")
    assert df["ff_velo_P5"][0] is None
    assert abs(df["ff_velo_P5"][1] - 96.0) < 1e-9   # only the prior start


def test_expected_stats_are_denominator_weighted():
    df = pr.add_rolling_pitcher_features(
        _starts(
            [
                _s(
                    1, 0, 20, wOBA_num=1.0, wOBA_den=1,
                    xwOBA_num=0.8, xBA_num=0.7, xBA_den=1,
                ),
                _s(
                    2, 0, 20, wOBA_num=0.0, wOBA_den=9,
                    xwOBA_num=0.9, xBA_num=1.8, xBA_den=9,
                ),
                _s(
                    3, 0, 20, wOBA_num=0.0, wOBA_den=1,
                    xwOBA_num=0.0, xBA_num=0.0, xBA_den=1,
                ),
            ]
        ),
        rate_stats={
            "wOBA": ("wOBA_num", "wOBA_den"),
            "xwOBA": ("xwOBA_num", "wOBA_den"),
            "xBA": ("xBA_num", "xBA_den"),
        },
        mean_cols=[],
        rate_windows=(5,),
    ).sort("game_date")
    assert df["wOBA_P5"][2] == pytest.approx(1 / 10)
    assert df["xwOBA_P5"][2] == pytest.approx(1.7 / 10)
    assert df["xBA_P5"][2] == pytest.approx(2.5 / 10)


def test_splitter_physics_propagate_to_rolling_features():
    df = pr.add_rolling_pitcher_features(
        _starts(
            [
                _s(1, 0, 20, fs_velo=89.0),
                _s(2, 0, 20, fs_velo=91.0),
            ]
        ),
        rate_stats={},
        mean_cols=pr.DEFAULT_MEAN_COLS,
        mean_windows=(3,),
    ).sort("game_date")
    assert df["fs_velo_P3"][1] == pytest.approx(89.0)


def test_same_date_starts_do_not_feed_each_other():
    df = pr.add_rolling_pitcher_features(
        _starts([
            _s(1, 8, 20, gp=100),
            _s(1, 0, 20, gp=200),
            _s(2, 4, 20, gp=300),
        ]),
        rate_stats={"k_rate": ("K", "PA")},
        mean_cols=[],
        rate_windows=(5,),
    ).sort("game_pk")
    assert df["k_rate_P5"][0] is None
    assert df["k_rate_P5"][1] is None
    assert df["k_rate_P5"][2] == pytest.approx(8 / 40)


def test_fip_and_xfip_use_aggregated_prior_counts():
    df = pr.add_rolling_pitcher_features(
        _starts([
            _s(1, 9, 27, HR=1, BB=2, HBP=0, FB=10, Outs=27, lg_hr_fb_prior=0.10),
            _s(2, 6, 20, HR=0, BB=1, HBP=0, FB=8, Outs=18, lg_hr_fb_prior=0.10),
            _s(3, 0, 20, HR=0, BB=0, HBP=0, FB=0, Outs=0, lg_hr_fb_prior=0.10),
        ]),
        rate_stats={},
        mean_cols=[],
        mean_windows=(3,),
    ).sort("game_date")
    assert df["FIP_P3"][2] == pytest.approx((-8 / 15) + 3.166)
    assert df["xFIP_P3"][2] == pytest.approx((2.4 / 15) + 3.166)


def test_missing_columns_are_skipped():
    # No 'Swings' column -> whiff_rate is silently skipped, no crash.
    df = pr.add_rolling_pitcher_features(
        _starts([_s(1, 5, 20), _s(2, 5, 20)]),
        rate_stats={"whiff_rate": ("Whiffs", "Swings")},
        mean_cols=[], rate_windows=(5,),
    )
    assert not any(c.startswith("whiff_rate") for c in df.columns)


def test_shrunk_k_uses_pitchers_previous_season_rate():
    starts = _starts(
        [
            _s(1, 10, 40, year=2023, gp=202301),
            _s(1, 0, 20, year=2024, gp=202401),
        ]
    )
    out = pr.add_prior_season_shrunk_k(
        starts,
        prior_strength_pa=200.0,
        fallback_league_k_rate=0.21,
    )
    first_2024 = out.filter(pl.col("game_pk") == 202401).row(0, named=True)
    assert first_2024["k_rate_std_shrunk"] == pytest.approx(10 / 40)


def test_shrunk_k_uses_previous_league_rate_for_debut():
    starts = _starts(
        [
            _s(1, 10, 40, year=2023, gp=202301, pitcher=1),
            _s(1, 0, 20, year=2024, gp=202401, pitcher=2),
        ]
    )
    out = pr.add_prior_season_shrunk_k(
        starts,
        prior_strength_pa=200.0,
        fallback_league_k_rate=0.21,
    )
    debut = out.filter(pl.col("game_pk") == 202401).row(0, named=True)
    assert debut["k_rate_std_shrunk"] == pytest.approx(10 / 40)


def test_shrunk_k_uses_explicit_fallback_for_first_loaded_season():
    starts = _starts([_s(1, 5, 20, year=2023, gp=202301)])
    out = pr.add_prior_season_shrunk_k(
        starts,
        prior_strength_pa=200.0,
        fallback_league_k_rate=0.21,
    )
    assert out["k_rate_std_shrunk"][0] == pytest.approx(0.21)


def test_shrunk_k_prior_weight_decays_with_current_season_pa():
    starts = _starts(
        [
            _s(1, 10, 40, year=2023, gp=202301),
            _s(1, 0, 20, year=2024, gp=202401),
            _s(2, 5, 20, year=2024, gp=202402),
        ]
    )
    out = pr.add_prior_season_shrunk_k(
        starts,
        prior_strength_pa=20.0,
        fallback_league_k_rate=0.21,
    ).sort("game_date")
    assert out.filter(pl.col("game_pk") == 202401)["k_rate_std_shrunk"][0] == (
        pytest.approx(0.25)
    )
    assert out.filter(pl.col("game_pk") == 202402)["k_rate_std_shrunk"][0] == (
        pytest.approx((0 + 20 * 0.25) / (20 + 20))
    )


def test_shrunk_k_does_not_use_future_current_season_starts():
    history = [
        _s(1, 10, 40, year=2023, gp=202301),
        _s(1, 0, 20, year=2024, gp=202401),
        _s(2, 5, 20, year=2024, gp=202402),
    ]
    base = pr.add_prior_season_shrunk_k(
        _starts(history),
        prior_strength_pa=20.0,
        fallback_league_k_rate=0.21,
    )
    with_future = pr.add_prior_season_shrunk_k(
        _starts([*history, _s(3, 20, 20, year=2024, gp=202403)]),
        prior_strength_pa=20.0,
        fallback_league_k_rate=0.21,
    )
    base_value = base.filter(pl.col("game_pk") == 202402)["k_rate_std_shrunk"][0]
    future_value = with_future.filter(
        pl.col("game_pk") == 202402
    )["k_rate_std_shrunk"][0]
    assert future_value == pytest.approx(base_value)


def test_duplicate_pitcher_game_keys_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        pr.add_rolling_pitcher_features(
            _starts([_s(1, 5, 20), _s(1, 5, 20)]),
            rate_stats={"k_rate": ("K", "PA")},
            mean_cols=[],
        )
