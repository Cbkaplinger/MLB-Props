"""Tests for odds board line scoring (incl. off-grid fallback)."""

from __future__ import annotations

from Python.count_layer import PROJECTION_K_LINES, p_strikeouts_ge
from Python.odds_board import _line_to_col, p_model_over_for_line, score_quote_against_board
from Python.sharp_odds import StrikeoutQuote


def test_projection_k_lines_include_soft_and_long() -> None:
    assert 2.5 in PROJECTION_K_LINES
    assert 9.5 in PROJECTION_K_LINES
    assert _line_to_col(2.5) == "p_over_2_5"
    assert _line_to_col(9.5) == "p_over_9_5"


def test_p_model_over_uses_column_when_present() -> None:
    row = {"p_over_3_5": 0.42, "k_rate_pred": 0.2, "projected_tbf": 20.0}
    assert p_model_over_for_line(row, 3.5) == 0.42


def test_p_model_over_prefers_calibrated_column() -> None:
    row = {
        "p_over_4_5": 0.66,
        "p_over_4_5_cal": 0.54,
        "k_rate_pred": 0.22,
        "projected_tbf": 22.0,
    }
    assert p_model_over_for_line(row, 4.5) == 0.54


def test_p_model_over_falls_back_for_missing_line() -> None:
    # Assad-style: logged slate without p_over_2_5
    rate, tbf = 0.173, 19.14
    row = {"k_rate_pred": rate, "projected_tbf": tbf, "expected_K": rate * tbf}
    got = p_model_over_for_line(row, 2.5)
    expected = float(
        p_strikeouts_ge(2.5, k_rate=[rate], projected_tbf=[tbf], family="binomial")[0]
    )
    assert got == expected


def test_score_quote_accepts_line_2_5_via_fallback() -> None:
    brow = {
        "game_date": "2026-07-30",
        "game_pk": 1,
        "pitcher_team": "CHC",
        "player_name": "Javier Assad",
        "pitcher": 665871,
        "venue": "away",
        "away_team": "CHC",
        "home_team": "STL",
        "expected_K": 3.31,
        "projected_tbf": 19.14,
        "k_rate_pred": 3.31 / 19.14,
        "days_rest": 5.0,
    }
    q = StrikeoutQuote(
        player_name="Javier Assad",
        line=2.5,
        over_american=-110,
        under_american=-110,
        sportsbook="fanduel",
        home_team="STL",
        away_team="CHC",
        event_id="evt",
        event_start_time="2026-07-30T18:15:00Z",
        is_main_line=True,
    )
    scored = score_quote_against_board(brow, q, unit_dollars=50.0)
    assert scored is not None
    assert scored["line"] == 2.5
    assert scored["player_name"] == "Javier Assad"
    assert 0.0 < scored["p_model_over"] < 1.0
