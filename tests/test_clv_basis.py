"""Unit tests for CLV basis reconciliation math.

These validate the pure-math layer that explains why external bet-trackers
(pikkit-style "9/10 beating CLV") diverge from the authoritative ledger
``clv_pp`` (de-vigged probability-point move).
"""

from __future__ import annotations

import polars as pl
import pytest

from Python.clv_basis import (
    ONE_PP,
    basis_beat_rates,
    compute_raw_close_diff,
    implied_prob,
    trailing_window_beat_rates,
    window_beat_rates,
)


def test_implied_prob_known() -> None:
    assert implied_prob(-110) == pytest.approx(110 / 210)
    assert implied_prob(120) == pytest.approx(100 / 220)
    assert implied_prob(100) == pytest.approx(0.5)


def test_compute_raw_close_diff_over() -> None:
    # Over bet at +120, close -105: raw implied diff
    side = ["over"]
    out = compute_raw_close_diff(side, [120], [-105])
    assert out[0] == pytest.approx(implied_prob(-105) - implied_prob(120))


def test_basis_beat_rates_matches_hand_count() -> None:
    # 10 tickets: 4 strictly positive, 2 zero, 4 negative
    clv = [0.02, -0.01, 0.0, 0.05, 0.0, -0.03, 0.015, -0.02, 0.01, 0.0]
    raw = list(clv)  # same distribution for the raw basis
    got = basis_beat_rates(clv, raw)
    assert got["n"] == 10
    # strict price > 0: {0.02, 0.05, 0.015, 0.01} = 4
    assert got["price_devig_gt0"] == pytest.approx(0.4)
    # lenient >= 0: plus the 3 zeros = 7
    assert got["price_devig_ge0"] == pytest.approx(0.7)
    # all but the two -0.02/-0.03 within 1pp, plus make sure magnitude bucket works
    n_no_move = sum(1 for v in clv if abs(v) <= ONE_PP)
    assert got["n_no_move_pt1pp"] == n_no_move


def test_window_beat_rates_resolves_side() -> None:
    ledger = pl.DataFrame(
        {
            "side": ["over", "under"],
            "bet_price": [120.0, -140.0],
            "over_price": [120.0, 102.0],
            "under_price": [-140.0, -140.0],
            "close_over": [-105.0, 102.0],
            "close_under": [-115.0, -166.0],
            "clv_pp": [0.0, 0.0],
        }
    )
    got = window_beat_rates(ledger)
    assert got["n"] == 2
    # over closed -105 (better for over than +120) -> raw diff > 0
    # under closed -166 (better for under than -140) -> raw diff > 0
    assert got["raw_implied_gt0"] == pytest.approx(1.0)


def test_trailing_window_reproduces_sampling_illusion() -> None:
    """Document the pikkit "x/y beating CLV" small-sample phenomenon.

    The *full cohort* has a ~50% strict beat rate, but the last-10 window — the
    exact basis an external tracker reports — can show 90% (9/10) purely from
    sampling variance. The point of this test is to demonstrate that the module
    surfaces both numbers so the gap is explained, not error or cherry-pick.
    """
    # 50 "old" tickets split ~50/50 around zero + 10 trailing tickets of which 9 are >0
    old = [0.01 if i % 2 == 0 else -0.01 for i in range(50)]  # 25 pos / 25 neg
    trailing = [0.03, 0.02, 0.05, -0.01, 0.01, 0.02, 0.04, 0.03, 0.02, 0.01]
    clv = old + trailing
    # Strictly increasing close timestamps so the trailing (positive-heavy)
    # block is the true last-10 after descending sort.
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    closes = [(base + timedelta(minutes=i)).isoformat() for i in range(len(clv))]
    df = pl.DataFrame(
        {
            "ticket_id": [f"t{i}" for i in range(len(clv))],
            "closed_at_utc": closes,
            "clv_pp": clv,
        }
    )
    cohort = trailing_window_beat_rates(df, window=10)
    # cohort beat rate on the strict price basis (>0):
    strict = basis_beat_rates(clv, clv)["price_devig_gt0"]
    assert strict == pytest.approx((25 + 9) / len(clv))
    # trailing-10 shows 9/10
    assert cohort["beat_n"] == 9
    assert cohort["beat_rate"] == pytest.approx(0.9)
    # The module makes the two unambiguous: trailing window != full cohort.
    assert cohort["beat_rate"] != pytest.approx(strict)
