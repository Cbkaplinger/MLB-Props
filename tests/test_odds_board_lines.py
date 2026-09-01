"""Tests for odds board line scoring (incl. off-grid fallback)."""

from __future__ import annotations

from Python.count_layer import PROJECTION_K_LINES, p_strikeouts_ge
import polars as pl

from Python.odds_board import (
    _line_to_col,
    apply_quality_gate,
    p_model_over_for_line,
    quality_gate_hold_reason,
    score_quote_against_board,
)
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


def test_quality_gate_holds_risky_rows_when_enabled() -> None:
    frame = pl.DataFrame(
        [
            {
                "recommendation": "BET",
                "side": "under",
                "edge": 0.13,
                "days_rest": 12.0,
                "opp_lineup_k_vs_hand": 0.24,
                "passes_floor": True,
            },
            {
                "recommendation": "BET",
                "side": "over",
                "edge": 0.16,
                "days_rest": 5.0,
                "opp_lineup_k_vs_hand": 0.18,
                "passes_floor": True,
            },
        ]
    )
    out, meta = apply_quality_gate(frame, enabled=True)
    assert meta["quality_gate_enabled"] is True
    assert out.filter(pl.col("recommendation") == "HOLD").height >= 1
    assert "quality_gate_reason" in out.columns


def test_quality_gate_hard_vetoes_4_5_over() -> None:
    frame = pl.DataFrame(
        [
            {
                "recommendation": "BET",
                "best_side": "over",
                "line": 4.5,
                "edge": 0.25,
                "days_rest": 5.0,
                "opp_lineup_k_vs_hand": 0.18,
                "passes_floor": True,
            },
            {
                "recommendation": "BET",
                "best_side": "under",
                "line": 4.5,
                "edge": 0.25,
                "days_rest": 5.0,
                "opp_lineup_k_vs_hand": 0.18,
                "passes_floor": True,
            },
        ]
    )
    out, _meta = apply_quality_gate(frame, enabled=True)
    over = out.filter(pl.col("best_side") == "over")
    under = out.filter(pl.col("best_side") == "under")
    assert over["recommendation"][0] == "HOLD"
    assert "veto_4_5_over" in over["quality_gate_reason"][0]
    assert under["recommendation"][0] == "BET"


def test_quality_gate_noop_when_disabled() -> None:
    frame = pl.DataFrame(
        [
            {
                "recommendation": "BET",
                "side": "under",
                "edge": 0.20,
                "days_rest": 5.0,
                "opp_lineup_k_vs_hand": 0.20,
                "passes_floor": True,
            }
        ]
    )
    out, meta = apply_quality_gate(frame, enabled=False)
    assert meta["quality_gate_enabled"] is False
    assert out["recommendation"][0] == "BET"


def test_quality_gate_hold_reason_rules() -> None:
    # dynamic min edge via explicit n_warn
    reason = quality_gate_hold_reason(
        edge=0.13,
        side="under",
        days_rest=12.0,
        matchup_tier="avg_matchup",
        n_warn=3,
    )
    assert reason is not None
    assert "matchup_tier_risk" in reason
    assert "under_long_rest_risk" in reason
    assert "edge_below_dynamic_min" in reason
