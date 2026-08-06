"""Unit tests for market de-vig / edge / Kelly / CLV math."""

from __future__ import annotations

import pytest

from Python.market import (
    DEFAULT_EDGE_FLOOR,
    DEFAULT_KELLY_FRACTION,
    american_odds_from_prob,
    american_to_decimal,
    american_to_implied_prob,
    bankroll_from_unit,
    bet_pnl,
    clv_pp,
    clv_pp_from_americans,
    devig_two_way,
    edge,
    evaluate_side,
    kelly_fraction,
    kelly_stake,
    settle_side,
    size_in_units,
    threshold_curve,
    unit_anchor_kelly_frac,
)


def test_american_to_implied_prob_known() -> None:
    assert american_to_implied_prob(-110) == pytest.approx(110 / 210)
    assert american_to_implied_prob(120) == pytest.approx(100 / 220)
    assert american_to_implied_prob(100) == pytest.approx(0.5)


def test_american_decimal_round_trip_positive() -> None:
    assert american_to_decimal(150) == pytest.approx(2.5)
    assert american_to_implied_prob(150) == pytest.approx(1.0 / 2.5)


def test_american_odds_from_prob_round_trip() -> None:
    for p in (0.4, 0.5, 0.6, 0.75):
        a = american_odds_from_prob(p)
        assert american_to_implied_prob(a) == pytest.approx(p, abs=0.01)


def test_devig_two_way_sums_to_one() -> None:
    # Classic -110 / -110 juice
    p_over, p_under = devig_two_way(-110, -110)
    assert p_over + p_under == pytest.approx(1.0)
    assert p_over == pytest.approx(0.5)
    assert p_under == pytest.approx(0.5)


def test_devig_removes_vig() -> None:
    # +120 / -140: raw sum > 1; fair probs sum to 1 and favor under
    p_over, p_under = devig_two_way(120, -140)
    assert p_over + p_under == pytest.approx(1.0)
    raw = american_to_implied_prob(120) + american_to_implied_prob(-140)
    assert raw > 1.0
    assert p_under > p_over


def test_edge_and_evaluate_side_example() -> None:
    # Model 58% on over at +120 / -140 → ~8.9 pt edge vs de-vig over
    p_over_mkt, _ = devig_two_way(120, -140)
    e = edge(0.58, p_over_mkt)
    assert e == pytest.approx(0.58 - p_over_mkt)
    assert e > 0.08

    got = evaluate_side(0.58, 120, -140, "over", bankroll=1000.0)
    assert got["passes_floor"] is True
    assert got["edge"] == pytest.approx(e)
    assert got["stake"] == pytest.approx(
        kelly_stake(1000.0, 0.58, 120),
    )
    assert got["kelly_frac"] == pytest.approx(
        kelly_fraction(0.58, 120, fraction=DEFAULT_KELLY_FRACTION),
    )


def test_evaluate_side_fails_floor_when_no_edge() -> None:
    got = evaluate_side(0.48, 120, -140, "over", edge_floor=DEFAULT_EDGE_FLOOR)
    assert got["passes_floor"] is False
    assert got["edge"] < DEFAULT_EDGE_FLOOR


def test_kelly_zero_when_no_value() -> None:
    # Fair coin at +100 → f* = 0
    assert kelly_fraction(0.5, 100) == pytest.approx(0.0)
    assert kelly_stake(1000.0, 0.5, 100) == pytest.approx(0.0)


def test_kelly_positive_with_edge() -> None:
    # p=0.6 at +100 even money → full Kelly 0.2 → quarter = 0.05
    assert kelly_fraction(0.6, 100, fraction=1.0) == pytest.approx(0.2)
    assert kelly_fraction(0.6, 100, fraction=0.25) == pytest.approx(0.05)
    assert kelly_stake(1000.0, 0.6, 100, fraction=0.25) == pytest.approx(50.0)


def test_clv_pp_positive_when_market_moves_toward_bet() -> None:
    # Bet over at +120; close tightens to +100 → CLV positive
    clv = clv_pp_from_americans(100, 120)
    assert clv == pytest.approx(
        american_to_implied_prob(100) - american_to_implied_prob(120),
    )
    assert clv > 0
    assert clv_pp(0.55, 0.50) == pytest.approx(0.05)


def test_clv_with_devig_pair() -> None:
    # Same juice both sides at close vs open: beat close on over
    clv = clv_pp_from_americans(
        close_american=-110,
        bet_american=120,
        close_other=-110,
        bet_other=-140,
    )
    p_close, _ = devig_two_way(-110, -110)
    p_bet, _ = devig_two_way(120, -140)
    assert clv == pytest.approx(p_close - p_bet)


def test_unit_anchor_reflects_current_floor() -> None:
    # Anchor = eighth-Kelly on the active edge_floor @ -110 (currently 12%).
    # Re-pin against DEFAULT_EDGE_FLOOR / DEFAULT_KELLY_FRACTION so the test
    # doesn't drift stale if the floor moves again (was 0.042 under the old
    # 8% / quarter-Kelly anchors; those were retired by the 2026-08-06 freeze).
    from Python.market import unit_anchor_kelly_frac  # local import keeps this test self-pinning

    anchor = unit_anchor_kelly_frac(
        edge_floor=DEFAULT_EDGE_FLOOR,
        kelly_frac=DEFAULT_KELLY_FRACTION,
    )
    assert anchor > 0.0
    assert bankroll_from_unit(50.0, edge_floor=DEFAULT_EDGE_FLOOR, kelly_frac=DEFAULT_KELLY_FRACTION) == pytest.approx(50.0 / anchor, rel=1e-6)


def test_size_in_units_zero_below_floor() -> None:
    got = size_in_units(0.55, -110, edge=0.03, unit_dollars=50.0)
    assert got["passes_floor"] is False
    assert got["units"] == 0.0
    assert got["stake"] == 0.0


def test_size_in_units_one_at_anchor() -> None:
    # Exactly the current-floor anchor bet: DEFAULT_EDGE_FLOOR over implied -110.
    p = american_to_implied_prob(-110) + DEFAULT_EDGE_FLOOR
    got = size_in_units(p, -110, edge=DEFAULT_EDGE_FLOOR, unit_dollars=50.0)
    assert got["passes_floor"] is True
    assert got["units"] == pytest.approx(1.0, abs=1e-6)
    assert got["stake"] == pytest.approx(50.0, abs=1e-4)


def test_bet_pnl_and_settle_side() -> None:
    assert settle_side("over", 4.5, 5) is True
    assert settle_side("under", 5.5, 4) is True
    assert settle_side("under", 5.5, 6) is False
    assert bet_pnl(75.0, -120, won=True) == pytest.approx(62.5)
    assert bet_pnl(75.0, -120, won=False) == pytest.approx(-75.0)


def test_threshold_curve_monotonic_n() -> None:
    edges = [0.05, 0.10, 0.15, 0.20]
    pnls = [10.0, 20.0, -5.0, 40.0]
    stakes = [50.0, 50.0, 50.0, 50.0]
    curve = threshold_curve(edges, pnls, stakes, thresholds=[0.0, 0.08, 0.12, 0.25])
    ns = [row["n"] for row in curve]
    assert ns == [4, 3, 2, 0]
    assert curve[1]["roi"] == pytest.approx((20 - 5 + 40) / 150)
