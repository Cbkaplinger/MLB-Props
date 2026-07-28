"""Unit tests for live assembly helpers (no network)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import polars as pl
import pytest

from Python.live_assembly import historical_training_rows, normalize_team_code, score_frame


def test_normalize_team_code_ari_to_az() -> None:
    assert normalize_team_code("ARI") == "AZ"
    assert normalize_team_code("az") == "AZ"
    assert normalize_team_code("NYY") == "NYY"


def test_expand_dual_starter_slate_adds_mlb_row_on_disagreement() -> None:
    from Python.daily_lineups import DailySlate
    from Python.live_assembly import expand_dual_starter_slate

    starters = pl.DataFrame(
        {
            "game_pk": [1, 1],
            "team": ["PHI", "MIA"],
            "pitcher": [554430, 663969],
            "player_name": ["Zack Wheeler", "Tyler Phillips"],
            "official_probable_pitcher_id": [605400, 663969],
            "throws": ["R", "R"],
        }
    )
    slate = DailySlate(lineups=pl.DataFrame({"game_pk": [1]}), starters=starters)
    expanded = expand_dual_starter_slate(slate)
    assert expanded.starters.height == 3  # PHI dual + MIA single
    phi = expanded.starters.filter(pl.col("team") == "PHI").sort("starter_source")
    assert phi["starter_source"].to_list() == ["mlb_probable", "rotogrinders"]
    assert phi["is_preferred"].to_list() == [True, False]
    assert phi["pitcher"].to_list() == [605400, 554430]
    mia = expanded.starters.filter(pl.col("team") == "MIA")
    assert mia.height == 1
    assert mia["starter_disagreement"][0] is False
    assert mia["is_preferred"][0] is True
