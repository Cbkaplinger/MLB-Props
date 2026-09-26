"""Property tests over the financial core (decision #5, scoped to two modules).

Each property states what breaks in money terms if it fails. Deterministic
seeds are not stored: Hypothesis profiles run in CI with its own database;
failures print the falsifying example. Public APIs only:
``Python.market`` and ``Python.odds_ledger``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python.market import (  # noqa: E402
    american_to_decimal,
    american_to_implied_prob,
    bet_pnl,
    clv_pp,
    clv_pp_from_americans,
    decimal_to_american,
    devig_two_way,
    kelly_fraction,
)
from Python.odds_ledger import (  # noqa: E402
    apply_settle,
    dedupe_ledger_props,
)

AMERICANS = st.integers(min_value=-10000, max_value=10000).filter(
    lambda a: a != 0 and abs(a) >= 100
)
PROBS = st.floats(min_value=0.01, max_value=0.99)
LINES = st.sampled_from([2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5])
SIDES = st.sampled_from(["over", "under"])


@given(AMERICANS, AMERICANS)
@settings(max_examples=300, deadline=None)
def test_devig_two_way_sums_to_one(over: int, under: int) -> None:
    # If this fails, every edge and every CLV computed from a book pair is
    # denominated wrong — the whole money track shifts.
    p_over, p_under = devig_two_way(float(over), float(under))
    assert abs((p_over + p_under) - 1.0) < 1e-9
    assert 0.0 < p_over < 1.0 and 0.0 < p_under < 1.0


@given(AMERICANS)
@settings(max_examples=200, deadline=None)
def test_devig_symmetric_pair_is_fair(american: int) -> None:
    # If this fails, book-mix comparisons (DK vs BR) carry a phantom bias.
    p_over, p_under = devig_two_way(float(american), float(american))
    assert abs(p_over - 0.5) < 1e-9
    assert abs(p_under - 0.5) < 1e-9


@given(AMERICANS)
@settings(max_examples=200, deadline=None)
def test_implied_prob_always_valid(american: int) -> None:
    # If this fails, downstream probabilities can escape [0, 1] and Kelly,
    # devig, and calibration silently operate on nonsense.
    assert 0.0 < american_to_implied_prob(float(american)) < 1.0


@given(st.floats(min_value=1.1, max_value=10.0))
@settings(max_examples=200, deadline=None)
def test_odds_roundtrip(decimal_odds: float) -> None:
    # If this fails, price conversions leak cents on every ticket Paradise-side.
    back = american_to_decimal(decimal_to_american(decimal_odds))
    assert abs(back - decimal_odds) < 0.02


@given(PROBS, PROBS)
@settings(max_examples=200, deadline=None)
def test_clv_bounded(close_p: float, bet_p: float) -> None:
    # If this fails, CLV scale is corrupt and beat-rate denominators lie.
    assert -1.0 <= clv_pp(close_p, bet_p) <= 1.0


@given(AMERICANS, AMERICANS, AMERICANS, AMERICANS)
@settings(max_examples=200, deadline=None)
def test_devigged_clv_bounded(co: int, bo: int, cu: int, bu: int) -> None:
    # If this fails, same-book CLV can print impossible values on real pairs.
    val = clv_pp_from_americans(float(co), float(bo),
                                close_other=float(cu), bet_other=float(bu))
    assert -1.0 <= val <= 1.0


@given(AMERICANS, st.booleans())
@settings(max_examples=200, deadline=None)
def test_zero_stake_zero_pnl(american: int, won: bool) -> None:
    # If this fails, phantom money enters the ledger from stake-0 rows.
    assert bet_pnl(0.0, float(american), won=won) == 0.0


def test_kelly_breakeven_at_fair() -> None:
    # If this fails, sizing points the wrong way at the fair line.
    assert kelly_fraction(0.5, 100.0) == 0.0
    # Floored at zero: no edge means no stake, never a short.
    assert kelly_fraction(0.5, -110.0) == 0.0


@given(PROBS, AMERICANS)
@settings(max_examples=200, deadline=None)
def test_kelly_sign_follows_edge(p_model: float, american: int) -> None:
    # If this fails, the sizer stakes into negative expectation.
    implied = american_to_implied_prob(float(american))
    frac = kelly_fraction(p_model, float(american))
    assert frac >= 0.0
    if p_model > implied + 1e-9:
        assert frac > 0.0


def _ledger_frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "ticket_id": pl.String,
            "side": pl.String,
            "line": pl.Float64,
            "stake": pl.Float64,
            "bet_price": pl.Float64,
            "settle_value": pl.Float64,
            "settle_ip": pl.Float64,
            "settle_outs": pl.Float64,
            "settle_hits_allowed": pl.Float64,
            "settle_walks_allowed": pl.Float64,
            "settle_strikeouts": pl.Float64,
            "result": pl.String,
            "pnl": pl.Float64,
            "status": pl.String,
        },
    )


TICKET = st.fixed_dictionaries({
    "side": SIDES,
    "line": LINES,
    "stake": st.sampled_from([25.0, 50.0]),
    "bet_price": st.sampled_from([-110.0, -105.0, 100.0, 115.0]),
    "settle_k": st.integers(min_value=0, max_value=12),
})


@given(st.lists(TICKET, min_size=1, max_size=8))
@settings(max_examples=100, deadline=None)
def test_settle_idempotent_every_ticket(tickets: list[dict]) -> None:
    # If this fails, regrading duplicates PnL — the fastest way to fabricate ROI.
    rows = [{
        "ticket_id": f"t{i}",
        "side": t["side"],
        "line": float(t["line"]),
        "stake": float(t["stake"]),
        "bet_price": float(t["bet_price"]),
        "settle_value": None,
        "settle_ip": None,
        "settle_outs": None,
        "settle_hits_allowed": None,
        "settle_walks_allowed": None,
        "settle_strikeouts": None,
        "result": None,
        "pnl": 0.0,
        "status": "open",
    } for i, t in enumerate(tickets)]
    frame = _ledger_frame(rows)
    once = frame
    for i, t in enumerate(tickets):
        once = apply_settle(once, ticket_id=f"t{i}", settle_value=float(t["settle_k"]))
    twice = once
    for i, t in enumerate(tickets):
        twice = apply_settle(twice, ticket_id=f"t{i}", settle_value=float(t["settle_k"]))
    assert twice.height == once.height == len(tickets)
    assert twice.equals(once)
    assert set(twice["status"].to_list()) == {"settled"}
    assert float(twice["pnl"].sum()) == float(once["pnl"].sum())


def _prop_frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema={
        "game_date": pl.String,
        "player_name": pl.String,
        "line": pl.Float64,
        "side": pl.String,
        "edge": pl.Float64,
        "stake": pl.Float64,
    })


PROP = st.fixed_dictionaries({
    "game": st.integers(min_value=1, max_value=3),
    "player": st.integers(min_value=1, max_value=4),
    "line": LINES,
    "side": SIDES,
    "edge": st.floats(min_value=0.0, max_value=0.3),
})


@given(st.lists(PROP, min_size=1, max_size=12))
@settings(max_examples=100, deadline=None)
def test_dedupe_idempotent_and_keyed(props: list[dict]) -> None:
    # If this fails, DK+FD doubles leak into summary stats — the 844-class bug.
    rows = [{
        "game_date": f"2026-09-{p['game']:02d}",
        "player_name": f"Arm {p['player']}",
        "line": float(p["line"]),
        "side": p["side"],
        "edge": float(p["edge"]),
        "stake": 50.0,
    } for p in props]
    frame = _prop_frame(rows)
    once = dedupe_ledger_props(frame)
    twice = dedupe_ledger_props(once)
    assert twice.height == once.height
    keys = list(zip(
        twice["game_date"].to_list(),
        twice["player_name"].str.to_lowercase().to_list(),
        twice["line"].to_list(),
        twice["side"].to_list(),
    ))
    assert len(set(keys)) == len(keys)


@given(st.lists(PROP, min_size=1, max_size=12))
@settings(max_examples=100, deadline=None)
def test_roi_invariant_to_row_order(props: list[dict]) -> None:
    # If this fails, reported ROI depends on ingestion order, not economics.
    import random

    rows = [{
        "game_date": f"2026-09-{p['game']:02d}",
        "player_name": f"Arm {p['player']}",
        "line": float(p["line"]),
        "side": p["side"],
        "edge": float(p["edge"]),
        "stake": 50.0,
    } for p in props]
    base = float(dedupe_ledger_props(_prop_frame(rows))["stake"].sum())
    shuffled = list(rows)
    random.Random(7).shuffle(shuffled)
    other = float(dedupe_ledger_props(_prop_frame(shuffled))["stake"].sum())
    assert base == other


def test_rung_monotonicity_all_families() -> None:
    # Standing invariant (owner 2026-09-24): P(K > line) never rises with the
    # line, in any count family. A violation would misprice every ladder.
    import numpy as np

    from Python.count_layer import p_strikeouts_ge

    lines = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
    rate = np.array([0.28] * 4)
    tbf = np.array([24.0, 20.0, 27.0, 22.0])
    for family in ("binomial", "beta_binomial", "poisson"):
        kw: dict = {"family": family}
        if family == "beta_binomial":
            kw["kappa"] = 50.0
        prev = None
        for ln in lines:
            cur = p_strikeouts_ge(ln, k_rate=rate, projected_tbf=tbf, **kw)
            if prev is not None:
                assert bool((cur <= prev + 1e-12).all())
            prev = cur
