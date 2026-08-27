"""CLV basis reconciliation: explain why external trackers differ from the ledger.

The ledger's authoritative ``clv_pp`` is stored on the *price* basis — the
de-vigged probability-point move ``p_mkt(close, side) - p_mkt(bet, side)`` on
the same ticket (see ``market.clv_pp`` / ``odds_ledger.apply_close``). On
strikeout props the closing line frequently does not move at all, so ``clv_pp``
clusters near zero and the strict ``> 0`` beat-close rate hovers near 50%.

External bet-tracking apps (e.g. pikkit) often report a "beating CLV" stat over
a tiny trailing window (e.g. the last 10 bets), or use a coarser "didn't get
worse" definition. This module exposes the reconciliation explicitly so those
numbers can be reproduced and explained rather than misinterpreted.

Pure math — no I/O. Ledger IO lives in
``production/ops/market_research/clv_basis_reconcile.py``.
"""

from __future__ import annotations

import polars as pl

# A close-then-bet gap smaller than this (probability points, i.e. fraction)
# is treated as "the market effectively did not move on this ticket".
NO_MOVE_EPS = 1e-6
# Probability-point threshold (fraction) used for magnitude buckets. 0.01 == 1pp.
ONE_PP = 0.01


def _count(vals: list[float], gt: float, ge: bool = False) -> int:
    return sum(1 for v in vals if (v >= gt if ge else v > gt))


def _beat_rate(vals: list[float], gt: float, ge: bool = False) -> float:
    if not vals:
        return 0.0
    return _count(vals, gt, ge=ge) / len(vals)


def implied_prob(american: float) -> float:
    """American odds -> implied win probability (fraction)."""
    a = float(american)
    return (-a / (-a + 100.0)) if a < 0 else (100.0 / (a + 100.0))

def compute_raw_close_diff(side: list[str], bet_price: list, close_side: list) -> list[float]:
    """Close-side implied probability minus bet-side implied probability.

    Like ``clv_pp`` but on the *raw* single-price implied basis (no de-vig).
    Coarser than the authoritative de-vigged basis and occasionally flips sign
    on thin prices; included so both the product and external trackers can be
    compared on the same tickets.
    """
    out: list[float] = []
    for s, bet, cls in zip(side, bet_price, close_side):
        if bet is None or cls is None:
            out.append(float("nan"))
            continue
        # close_side is the close price on the BET side (close_over if over,
        # close_under if under) — caller resolves which column to feed in.
        out.append(implied_prob(cls) - implied_prob(bet))
    return out


def basis_beat_rates(clv_pp: list[float], raw_close_diff: list[float]) -> dict[str, float]:
    """Beat-close rate under explicit bases, given both CLV vectors.

    Bases (as fractions of the closed population):
      - ``price_devig_gt0``: strict ledger basis, clv_pp > 0
      - ``price_devig_ge0``: lenient ledger basis, clv_pp >= 0 (didn't get worse)
      - ``raw_implied_gt0``: strict raw single-price basis, raw diff > 0
      - ``raw_implied_ge0``: lenient raw single-price basis, raw diff >= 0
    """
    clv = [float(v) for v in clv_pp]
    raw = [float(v) for v in raw_close_diff]
    out: dict[str, float] = {}
    out["n"] = float(len(clv))
    out["price_devig_gt0"] = _beat_rate(clv, 0.0)
    out["price_devig_ge0"] = _beat_rate(clv, -NO_MOVE_EPS, ge=True)
    rr = [v for v in raw if v == v]  # drop NaN
    if rr:
        out["raw_implied_gt0"] = _beat_rate(rr, 0.0)
        out["raw_implied_ge0"] = _beat_rate(rr, -NO_MOVE_EPS, ge=True)
    else:
        out["raw_implied_gt0"] = 0.0
        out["raw_implied_ge0"] = 0.0
    # Magnitude: how much of the population actually moved.
    out["n_no_move_pt1pp"] = float(sum(1 for v in clv if abs(v) <= ONE_PP))
    out["frac_no_move_pt1pp"] = (out["n_no_move_pt1pp"] / len(clv)) if clv else 0.0
    return out


def window_beat_rates(
    frame: pl.DataFrame,
    *,
    side_col: str = "side",
    bet_price_col: str = "bet_price",
    close_over_col: str = "close_over",
    close_under_col: str = "close_under",
    clv_col: str = "clv_pp",
) -> dict[str, float]:
    """Compute basis beat-rates for a ledger frame that already has closes.

    ``frame`` must contain rows with non-null ``clv_col`` and the close/bet
    price columns. Returns the same dict shape as :func:`basis_beat_rates`.
    """
    if frame.is_empty():
        return {
            "n": 0.0,
            "price_devig_gt0": 0.0,
            "price_devig_ge0": 0.0,
            "raw_implied_gt0": 0.0,
            "raw_implied_ge0": 0.0,
            "n_no_move_pt1pp": 0.0,
            "frac_no_move_pt1pp": 0.0,
        }
    df = frame.filter(pl.col(clv_col).is_not_null())
    side = df[side_col].to_list()
    bet = df[bet_price_col].to_list()
    cls = [
        c_over if s == "over" else c_under
        for s, c_over, c_under in zip(
            side, df[close_over_col].to_list(), df[close_under_col].to_list()
        )
    ]
    raw = compute_raw_close_diff(side, bet, cls)
    return basis_beat_rates(df[clv_col].to_list(), raw)


def trailing_window_beat_rates(
    frame: pl.DataFrame,
    *,
    window: int = 10,
    order_col: str = "closed_at_utc",
    clv_col: str = "clv_pp",
) -> dict[str, float]:
    """Beat-rate over the most recent ``window`` closed tickets (pikkit-style).

    External trackers report "x/y beating CLV" over e.g. the last 10 bets. This
    is a *statistically tiny* sample with high variance versus the full cohort;
    this helper exists to reproduce that number and to make the discrepancy
    explicit when compared against :func:`window_beat_rates` on the full frame.
    """
    df = frame.filter(pl.col(clv_col).is_not_null())
    if df.is_empty() or order_col not in df.columns:
        return {"window": window, "n": 0, "beat_n": 0, "beat_rate": 0.0}
    df = df.sort(order_col, descending=True)
    tail = df.head(window)[clv_col].to_list()
    return {
        "window": window,
        "n": len(tail),
        "beat_n": sum(1 for v in tail if v > 0),
        "beat_rate": _beat_rate(tail, 0.0),
    }

