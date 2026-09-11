"""Tests for odds board line scoring (incl. off-grid fallback)."""

from __future__ import annotations

from Python.count_layer import (
    COUNT_LAYER_FAMILY_DEFAULT,
    PROJECTION_K_LINES,
    p_strikeouts_ge,
)
import polars as pl

from Python.odds_board import (
    _clip_offset,
    _edge_cap_reason,
    _line_to_col,
    _postseason_hold_reason,
    _robust_refusal_reason,
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
        p_strikeouts_ge(2.5, k_rate=[rate], projected_tbf=[tbf],
                        family=COUNT_LAYER_FAMILY_DEFAULT)[0]
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
    # Edges kept below the 0.20 edge cap so this test isolates the veto.
    frame = pl.DataFrame(
        [
            {
                "recommendation": "BET",
                "best_side": "over",
                "line": 4.5,
                "edge": 0.15,
                "days_rest": 5.0,
                "opp_lineup_k_vs_hand": 0.18,
                "passes_floor": True,
            },
            {
                "recommendation": "BET",
                "best_side": "under",
                "line": 4.5,
                "edge": 0.15,
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


def test_postseason_hold_fires_past_cutoff() -> None:
    rules = {"season": {"regular_end": "2026-09-27"}}
    assert _postseason_hold_reason({"game_date": "2026-09-20"}, rules) is None
    assert _postseason_hold_reason({"game_date": "2026-09-27"}, rules) is None
    assert _postseason_hold_reason({"game_date": "2026-10-03"}, rules) == "postseason_hold"


def test_postseason_hold_absent_without_key() -> None:
    assert _postseason_hold_reason({"game_date": "2026-10-03"}, {}) is None
    assert _postseason_hold_reason(
        {"game_date": "2026-10-03"}, {"season": {}}) is None
    assert _postseason_hold_reason(
        {}, {"season": {"regular_end": "2026-09-27"}}) is None


def _quote(player: str, line: float, over: float, under: float) -> StrikeoutQuote:
    return StrikeoutQuote(
        player_name=player, line=line, over_american=over, under_american=under,
        sportsbook="fanduel", home_team="NYM", away_team="PHI",
        event_id="evt", event_start_time="2026-09-20T23:10:00Z", is_main_line=True)


def _brow(p_over: float, line: float, tbf: float = 22.0) -> dict:
    col = _line_to_col(line)
    return {"game_date": "2026-09-20", "player_name": "Test Arm",
            "expected_K": 6.0, "projected_tbf": tbf,
            "maturity_bucket": "early_lt10", col: p_over - 0.06,
            f"{col}_cal": p_over}


def test_step2_columns_flag_gilbert_class() -> None:
    # Map kept below the live 0.02 offset cap so this tests share math, not
    # the clip (see test_offset_cap_clips_gilbert_class below).
    omap = {(6.5, "fav_-169_to_-140", "early_lt10"): 0.015}
    s = score_quote_against_board(
        _brow(0.70, 6.5), _quote("Test Arm", 6.5, -142, 112),
        unit_dollars=50.0, edge_floor=0.01, prob_offset_map=omap)
    assert s is not None
    assert s["offset_value"] == 0.015
    assert abs(s["offset_share_of_edge"] - 0.015 / s["edge"]) < 1e-4  # stored round(4)
    assert s["offset_gt_half_edge"] == (abs(0.015 / s["edge"]) > 0.5)
    assert s["opener_flag"] is False
    assert "postseason" not in s["policy_reason"]


def test_offset_cap_clips_gilbert_class() -> None:
    # Owner-directed 2026-09-11: ±0.02 clip in the live edge calc.
    omap = {(6.5, "fav_-169_to_-140", "early_lt10"): 0.06}
    s = score_quote_against_board(
        _brow(0.70, 6.5), _quote("Test Arm", 6.5, -142, 112),
        unit_dollars=50.0, edge_floor=0.01, prob_offset_map=omap)
    assert s is not None
    assert s["offset_value"] == 0.02
    assert _clip_offset(0.06, {}) == 0.06  # missing key = legacy passthrough
    assert _clip_offset(-0.06, {"offset_cap": 0.02}) == -0.02


def test_step2_opener_flag_short_outing() -> None:
    s = score_quote_against_board(
        _brow(0.80, 2.5, tbf=23.0), _quote("Test Arm", 2.5, -110, -110),
        unit_dollars=50.0, edge_floor=0.01, prob_offset_map={})
    assert s is not None
    assert s["opener_flag"] is True
    assert s["offset_share_of_edge"] == 0.0
    assert s["offset_gt_half_edge"] is False


def test_step2_no_map_leaves_bet_logic_untouched() -> None:
    a = score_quote_against_board(
        _brow(0.70, 6.5), _quote("Test Arm", 6.5, -126, -104),
        unit_dollars=50.0, edge_floor=0.12)
    b = score_quote_against_board(
        _brow(0.70, 6.5), _quote("Test Arm", 6.5, -126, -104),
        unit_dollars=50.0, edge_floor=0.12, prob_offset_map={})
    assert a is not None and b is not None
    assert a["recommendation"] == b["recommendation"]
    assert a["edge"] == b["edge"]
    assert b["offset_share_of_edge"] == 0.0


def test_edge_cap_reason_fires_and_fail_open() -> None:
    rules = {"block_edge_above_cap": True, "edge_cap": 0.20}
    assert _edge_cap_reason(0.25, rules) == "edge_cap"
    assert _edge_cap_reason(0.20, rules) == "edge_cap"
    assert _edge_cap_reason(0.19, rules) is None
    assert _edge_cap_reason(0.25, {}) is None
    assert _edge_cap_reason(
        0.25, {"block_edge_above_cap": False, "edge_cap": 0.20}) is None


def test_robust_refusal_reason() -> None:
    rules = {"robust_shrink_refusal": True}
    # edge 0.15 on p=0.70 → shrunk 0.05 < floor 0.12 → refuse
    assert _robust_refusal_reason(0.70, 0.15, 0.12, rules) == "robust_refusal"
    # edge 0.19 on p=0.60 → shrunk 0.14 ≥ floor → survives
    assert _robust_refusal_reason(0.60, 0.19, 0.12, rules) is None
    # raw edge below floor belongs to below_floor, not refusal
    assert _robust_refusal_reason(0.60, 0.10, 0.12, rules) is None
    assert _robust_refusal_reason(0.70, 0.15, 0.12, {}) is None


def test_quality_gate_holds_edge_above_cap() -> None:
    frame = pl.DataFrame(
        [
            {
                "recommendation": "BET",
                "best_side": "over",
                "line": 6.5,
                "edge": 0.25,
                "days_rest": 5.0,
                "opp_lineup_k_vs_hand": 0.18,
                "passes_floor": True,
            },
            {
                "recommendation": "BET",
                "best_side": "under",
                "line": 6.5,
                "edge": 0.15,
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
    assert "edge_cap" in over["quality_gate_reason"][0]
    assert under["recommendation"][0] == "BET"


def _tmp_policy_with_refusal(tmp_path) -> str:
    import json as _json

    p = tmp_path / "kpi_refusal.json"
    p.write_text(
        _json.dumps(
            {
                "quality_gate": {
                    "rules": {"robust_shrink_refusal": True},
                    "dynamic_min_edge": {
                        "base": 0.12,
                        "elevated": 0.14,
                        "elevated_when_n_warn_gte": 2,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return str(p)


def test_quality_gate_robust_refusal_needs_columns(tmp_path) -> None:
    # p=0.70 edge=0.15 floor 0.12 → shrunk 0.05 → HOLD robust_refusal.
    # Refusal is OFF in live policy (reverted 2026-09-11); this test drives
    # it through an explicit policy file. Mirror is fail-open without the
    # p_model / edge_floor_effective columns.
    frame = pl.DataFrame(
        [
            {
                "recommendation": "BET",
                "best_side": "over",
                "line": 6.5,
                "edge": 0.15,
                "p_model": 0.70,
                "edge_floor_effective": 0.12,
                "days_rest": 5.0,
                "opp_lineup_k_vs_hand": 0.18,
                "passes_floor": True,
            },
        ]
    )
    out, _meta = apply_quality_gate(
        frame, enabled=True, kpi_policy_path=_tmp_policy_with_refusal(tmp_path)
    )
    assert out["recommendation"][0] == "HOLD"
    assert "robust_refusal" in out["quality_gate_reason"][0]


def test_score_quote_holds_edge_above_cap() -> None:
    s = score_quote_against_board(
        _brow(0.95, 6.5), _quote("Test Arm", 6.5, -110, -110),
        unit_dollars=50.0, edge_floor=0.12, prob_offset_map={})
    assert s is not None
    assert s["recommendation"] == "HOLD"
    assert "edge_cap" in s["policy_reason"]
    assert s["stake"] == 0.0


def test_score_quote_holds_robust_refusal(tmp_path) -> None:
    # Refusal is OFF in live policy (reverted 2026-09-11); driven here
    # through an explicit policy file to keep the code path tested for the
    # October family dimension.
    s = score_quote_against_board(
        _brow(0.65, 6.5), _quote("Test Arm", 6.5, -110, -110),
        unit_dollars=50.0, edge_floor=0.12, prob_offset_map={},
        kpi_policy_path=_tmp_policy_with_refusal(tmp_path))
    assert s is not None
    assert s["recommendation"] == "HOLD"
    assert "robust_refusal" in s["policy_reason"]
    assert s["stake"] == 0.0
