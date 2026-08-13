from __future__ import annotations

import datetime as dt

import polars as pl

from Python.pipeline import rolling


def _games() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "game_pk": 1,
                "game_date": dt.date(2026, 8, 1),
                "season": 2026,
                "pitcher": 111,
                "player_name": "Pitcher A",
                "pitcher_name": "Pitcher A",
                "p_throws": "R",
                "home_team": "AAA",
                "away_team": "BBB",
                "is_home": True,
                "opp_team": "BBB",
                "K": 8.0,
                "PA": 20.0,
                "Outs": 15.0,
                "Pitches": 90.0,
                "k_rate": 0.4,
            },
            {
                "game_pk": 2,
                "game_date": dt.date(2026, 8, 8),
                "season": 2026,
                "pitcher": 111,
                "player_name": "Pitcher A",
                "pitcher_name": "Pitcher A",
                "p_throws": "R",
                "home_team": "AAA",
                "away_team": "BBB",
                "is_home": True,
                "opp_team": "BBB",
                "K": 4.0,
                "PA": 20.0,
                "Outs": 12.0,
                "Pitches": 85.0,
                "k_rate": 0.2,
            },
        ],
        schema_overrides={"game_date": pl.Date},
    )


def test_high_confidence_anomaly_excluded_from_rolling_updates(monkeypatch):
    games = _games()

    def _fake_apply(df: pl.DataFrame, *_args, **_kwargs) -> pl.DataFrame:
        return df.with_columns(
            pl.when(pl.col("game_pk") == 1).then(True).otherwise(False).alias("exit_anomaly_flag"),
            pl.when(pl.col("game_pk") == 1).then(pl.lit("high")).otherwise(None).alias("exit_anomaly_confidence"),
            pl.lit("manual_override").alias("exit_anomaly_source"),
        )

    monkeypatch.setattr(rolling, "apply_exit_anomaly_overrides", _fake_apply)

    baseline = rolling.build_pitcher_rolling(games, use_exit_anomaly_policy=False)
    policy = rolling.build_pitcher_rolling(games, use_exit_anomaly_policy=True)

    # Baseline second start sees first-start prior; policy excludes it.
    b2 = baseline.filter(pl.col("game_pk") == 2).row(0, named=True)
    p2 = policy.filter(pl.col("game_pk") == 2).row(0, named=True)
    assert b2["k_rate_P5"] == 0.4
    assert p2["k_rate_P5"] is None

    # Labels stay truthful (restored after policy feature computation).
    p1 = policy.filter(pl.col("game_pk") == 1).row(0, named=True)
    assert p1["K"] == 8.0
    assert p1["PA"] == 20.0
