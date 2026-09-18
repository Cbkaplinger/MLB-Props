"""September safety package TEST-1: five dangerous invariants (owner 2026-09-17).

Each test guards a failure mode capable of silently corrupting headline
results. All hermetic (synthetic frames, tmp policy files, monkeypatched
fetchers) — no network, no ledger writes, no alerts.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python import odds_board as ob  # noqa: E402
from Python.odds_ledger import apply_settle  # noqa: E402
from Python.pipeline.training import opposing_lineup_features  # noqa: E402
from Python.sharp_odds import StrikeoutQuote  # noqa: E402


def _load_grading():
    spec = importlib.util.spec_from_file_location(
        "send_daily_grading",
        ROOT / "production" / "ops" / "send_daily_grading.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["send_daily_grading"] = mod
    spec.loader.exec_module(mod)
    return mod


def _probation_rules() -> dict:
    """Champion-shaped gate rules (values, not the live file)."""
    return {
        "probation_edge_floor": 0.18,
        "side_line_probation": [{"side": "over", "line": 3.5}],
        "under_lean_premium": 0.04,
    }


def _policy_file(tmp_path: Path) -> Path:
    payload = {"quality_gate": {"rules": _probation_rules()}}
    path = tmp_path / "kpi_policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_probation_then_lean_order_matters() -> None:
    """Swapping the two floors changes the verdict — order is load-bearing."""
    rules = _probation_rules()
    canonical = ob._probation_edge_floor("over", 3.5, rules, 0.12) \
        + ob._lean_premium(rules)
    swapped = ob._probation_edge_floor("over", 3.5, rules, 0.12 + ob._lean_premium(rules))
    assert canonical == 0.22
    assert swapped == 0.18
    # An over edge of 0.20 passes under the swapped order but not canonical.
    assert swapped < 0.20 < canonical


def test_board_applies_probation_before_lean(tmp_path: Path) -> None:
    """End-to-end pin: over@3.5 edge 0.20 is held at the lean floor.

    Reordering score_quote_against_board's floor composition flips this
    ticket to a pass, failing the test.
    """
    policy_path = _policy_file(tmp_path)
    board_row = {
        "player_name": "Test Arm",
        "game_date": "2026-09-17",
        "p_over_3_5": 0.70,
        "maturity_bucket": "established",
        "projected_tbf": 20.0,
        "expected_K": 6.0,
        "days_rest": 5,
    }
    quote = StrikeoutQuote(
        player_name="Test Arm",
        line=3.5,
        over_american=-110.0,
        under_american=-110.0,
        sportsbook="draftkings",
        home_team="HOME",
        away_team="AWAY",
        event_id=None,
        event_start_time=None,
        is_main_line=True,
    )
    scored = ob.score_quote_against_board(
        board_row, quote, edge_floor=0.12, kpi_policy_path=policy_path
    )
    assert scored is not None
    assert scored["best_side"] == "over"
    assert abs(scored["edge"] - 0.20) < 1e-9
    assert scored["edge_floor_effective"] == 0.22
    assert scored["passes_floor"] is False
    assert scored["policy_reason"] == "below_lean_floor"
    assert scored["recommendation"] == "skip"
    assert scored["units"] == 0.0


def test_double_settle_counts_once() -> None:
    """Settling the same ticket twice yields one settlement, no dup PnL.

    Same-K re-settle is byte-identical; a changed K overwrites in place
    (the versioned-correction path — CLI still refuses settled rows).
    """
    frame = pl.DataFrame([{
        "ticket_id": "t1",
        "side": "under",
        "line": 6.5,
        "stake": 50.0,
        "bet_price": -110.0,
        "settle_value": None,
        "settle_ip": None,
        "settle_outs": None,
        "settle_hits_allowed": None,
        "settle_walks_allowed": None,
        "settle_strikeouts": None,
        "result": None,
        "pnl": 0.0,
        "status": "open",
    }])
    once = apply_settle(frame, ticket_id="t1", settle_value=5.0)
    assert once.height == 1
    assert once["status"].to_list() == ["settled"]
    assert once["result"].to_list() == ["win"]
    pnl_once = float(once["pnl"].sum())
    assert pnl_once > 0
    twice = apply_settle(once, ticket_id="t1", settle_value=5.0)
    assert twice.height == 1
    assert float(twice["pnl"].sum()) == pnl_once
    corrected = apply_settle(once, ticket_id="t1", settle_value=8.0)
    assert corrected.height == 1
    assert corrected["result"].to_list() == ["loss"]
    assert float(corrected["pnl"].sum()) == -50.0


def test_missing_close_never_enters_clv_denominator() -> None:
    """Null/unavailable closes shrink coverage, never the CLV mean."""
    grading = _load_grading()
    frame = pl.DataFrame([
        {"stake": 50.0, "pnl": 45.45, "edge": 0.15, "result": "win", "clv_pp": 0.02},
        {"stake": 50.0, "pnl": -50.0, "edge": 0.13, "result": "loss", "clv_pp": -0.01},
        {"stake": 50.0, "pnl": 45.0, "edge": 0.20, "result": "win", "clv_pp": None},
    ])
    out = grading.summarize(frame)
    assert out["n"] == 3
    assert out["n_clv"] == 2
    assert out["beat_rate"] == 0.5
    assert out["mean_clv_pp"] == 0.5
    # Win rate still covers all settled tickets; CLV covers measured only.
    assert out["wr"] == round(2 / 3, 4)


def test_lineup_join_uses_pregame_nine_only() -> None:
    """A late substitute (non-initial lineup) must not move L3 features."""
    starts = pl.DataFrame([{
        "game_pk": 1, "pitcher": "Ace", "p_throws": "R", "opp_team": "NYA",
    }])
    base = {
        "game_pk": 1,
        "bat_team": "NYA",
        "k_rate_std": 0.20,
        "k_rate_std_vL": 0.25,
        "k_rate_std_vR": 0.20,
        "whiff_rate_std": 0.10,
        "swstr_rate_std": 0.10,
        "chase_rate_std": 0.10,
        "zswing_rate_std": 0.10,
        "swing_rate_std": 0.10,
        "zcontact_rate_std": 0.10,
        "bb_rate_std": 0.10,
        "zswing_rate_P5": 0.10,
        "zswing_rate_P10": 0.10,
        "zswing_rate_P20": 0.10,
        "swing_rate_P5": 0.10,
        "swing_rate_P10": 0.10,
        "swing_rate_P20": 0.10,
        "zcontact_rate_P5": 0.10,
        "zcontact_rate_P10": 0.10,
        "zcontact_rate_P20": 0.10,
        "bb_rate_P5": 0.10,
        "bb_rate_P10": 0.10,
        "bb_rate_P20": 0.10,
    }
    rows = [{**base, "batter": f"Bat{i}", "is_initial_lineup": True} for i in range(9)]
    rows.append({**base, "batter": "Sub", "is_initial_lineup": False,
                 "k_rate_std": 0.99, "k_rate_std_vR": 0.99})
    batters = pl.DataFrame(rows)
    out = opposing_lineup_features(starts, batters)
    assert out.height == 1
    row = out.row(0, named=True)
    assert row["opp_lineup_size"] == 9
    assert abs(float(row["opp_lineup_k"]) - 0.20) < 1e-12
    assert abs(float(row["opp_lineup_k_vs_hand"]) - 0.20) < 1e-12


def test_live_board_drops_non_allowlisted_books(monkeypatch) -> None:
    """Intraday flow cannot smuggle a non-DK/FD quote past the board.

    Pinned against the live fill_books universe: any legitimate universe
    change must update this test + test_live_stack_pin together.
    """
    board = pl.DataFrame([{
        "game_date": "2026-09-17",
        "player_name": "Test Arm",
        "p_over_6_5": 0.65,
        "maturity_bucket": "established",
        "projected_tbf": 20.0,
        "expected_K": 6.0,
        "days_rest": 5,
    }])

    def _quotes(**kwargs):
        return [
            StrikeoutQuote("Test Arm", 6.5, -110.0, -110.0, book,
                           "HOME", "AWAY", None, None, True)
            for book in ("draftkings", "betrivers", "betmgm")
        ]

    monkeypatch.setattr(ob, "load_projection_board", lambda *a, **k: board)
    monkeypatch.setattr(ob, "fetch_mlb_strikeout_quotes", _quotes)
    frame, meta = ob.build_recommendations()
    # meta n_quotes counts post-filter rows; the drop is counted separately.
    assert meta["n_quotes"] == 1
    assert meta["n_book_filtered_out"] == 2
    assert not frame.is_empty()
    assert set(frame["book"].to_list()) <= {"draftkings", "fanduel"}
