"""Tests for denominator-aware stabilization (numpy-only path, no SciPy)."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from mlb_props import reliability as rel


def _panel(rate_by_player, starts=4, pa=10, denom_col="PA", stat="K", mean_val=None):
    """Build a per-start panel: each player repeats a fixed value across starts."""
    rows = []
    for pid, val in rate_by_player.items():
        for g in range(starts):
            row = {
                "player_name": pid,
                "game_date": dt.date(2024, 4, 1) + dt.timedelta(days=g),
                "Pitches": pa,
                denom_col: pa,
            }
            row[stat] = mean_val if mean_val is not None else int(round(val * pa))
            rows.append(row)
    return pd.DataFrame(rows)


def test_rate_stat_perfectly_consistent_gives_r_one():
    # Each player has a distinct, constant K rate -> split halves match exactly.
    df = _panel({f"p{i}": (i % 5) / 10.0 for i in range(8)})
    out = rel.stabilization_by_denominator(
        df, plan=[("K", "PA", True)], targets=[10], min_players=2
    )
    assert abs(out.loc[10, "K"] - 1.0) < 1e-9


def test_insufficient_denominator_returns_nan():
    df = _panel({f"p{i}": (i % 5) / 10.0 for i in range(8)}, starts=2, pa=10)
    # target=100 needs 200 denom units per player; only 20 available.
    out = rel.stabilization_by_denominator(
        df, plan=[("K", "PA", True)], targets=[100], min_players=2
    )
    assert pd.isna(out.loc[100, "K"])


def test_mean_stat_uses_denominator_weighting():
    # Distinct constant velocities per player -> consistent halves -> r == 1.
    df = _panel(
        {f"p{i}": 0 for i in range(8)}, stat="ff_velo",
        mean_val=None, denom_col="Pitches",
    )
    # give each player a distinct constant velocity
    df["ff_velo"] = df["player_name"].str[1:].astype(int) + 90.0
    out = rel.stabilization_by_denominator(
        df, plan=[("ff_velo", "Pitches", False)], targets=[10], min_players=2
    )
    assert abs(out.loc[10, "ff_velo"] - 1.0) < 1e-9
