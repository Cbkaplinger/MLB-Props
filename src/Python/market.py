"""Market math for prop betting: de-vig, edge, Kelly, CLV.

Product layer only — never feed book prices into the strikeout trainer.
See ``docs/reference/market_clv_gates.md`` for locked thresholds.
"""

from __future__ import annotations

from typing import Literal

BetSide = Literal["over", "under"]

# Pre-registered defaults (market_clv_gates.md)
DEFAULT_EDGE_FLOOR = 0.08
DEFAULT_KELLY_FRACTION = 0.25


def american_to_implied_prob(american: float) -> float:
    """Convert American odds to raw (vigged) implied win probability."""
    a = float(american)
    if a == 0:
        raise ValueError("American odds cannot be 0")
    if a > 0:
        return 100.0 / (a + 100.0)
    return (-a) / ((-a) + 100.0)


def american_to_decimal(american: float) -> float:
    """Convert American odds to decimal (European) odds."""
    a = float(american)
    if a == 0:
        raise ValueError("American odds cannot be 0")
    if a > 0:
        return 1.0 + a / 100.0
    return 1.0 + 100.0 / (-a)


def decimal_to_american(decimal_odds: float) -> int:
    """Convert decimal odds to American (rounded to nearest integer)."""
    d = float(decimal_odds)
    if d <= 1.0:
        raise ValueError("decimal odds must be > 1")
    if d >= 2.0:
        return int(round((d - 1.0) * 100.0))
    return int(round(-100.0 / (d - 1.0)))


def american_odds_from_prob(p: float) -> int:
    """Fair American odds from a win probability (no vig)."""
    prob = float(min(max(p, 1e-6), 1.0 - 1e-6))
    if prob >= 0.5:
        return int(round(-prob / (1.0 - prob) * 100.0))
    return int(round((1.0 - prob) / prob * 100.0))


def devig_two_way(
    over_american: float,
    under_american: float,
) -> tuple[float, float]:
    """Multiplicative de-vig of an over/under pair.

    Returns ``(p_over_fair, p_under_fair)`` summing to 1.
    """
    p_over = american_to_implied_prob(over_american)
    p_under = american_to_implied_prob(under_american)
    total = p_over + p_under
    if total <= 0:
        raise ValueError("implied probabilities must be positive")
    return p_over / total, p_under / total


def edge(
    p_model: float,
    p_market: float,
) -> float:
    """Model probability minus de-vigged market probability (bet side)."""
    return float(p_model) - float(p_market)


def kelly_fraction(
    p_model: float,
    american: float,
    *,
    fraction: float = DEFAULT_KELLY_FRACTION,
) -> float:
    """Fractional Kelly stake as a fraction of bankroll (floored at 0).

    ``f* = (p × decimal − 1) / (decimal − 1)``, then multiply by ``fraction``.
    """
    p = float(p_model)
    if not 0.0 <= p <= 1.0:
        raise ValueError("p_model must be in [0, 1]")
    frac = float(fraction)
    if frac < 0:
        raise ValueError("fraction must be non-negative")
    dec = american_to_decimal(american)
    full = (p * dec - 1.0) / (dec - 1.0)
    return frac * max(full, 0.0)


def kelly_stake(
    bankroll: float,
    p_model: float,
    american: float,
    *,
    fraction: float = DEFAULT_KELLY_FRACTION,
) -> float:
    """Dollar stake from fractional Kelly (0 if no edge at these odds)."""
    br = float(bankroll)
    if br < 0:
        raise ValueError("bankroll must be non-negative")
    return br * kelly_fraction(p_model, american, fraction=fraction)


def clv_pp(
    p_market_close: float,
    p_market_bet: float,
) -> float:
    """Closing-line value in probability points.

    ``CLV_pp = p_mkt(close, bet side) − p_mkt(price you bet)``.
    Positive means the market moved toward your side after the bet.
    """
    return float(p_market_close) - float(p_market_bet)


def clv_pp_from_americans(
    close_american: float,
    bet_american: float,
    *,
    close_other: float | None = None,
    bet_other: float | None = None,
) -> float:
    """CLV from American prices on the bet side.

    If the opposite-side price is provided for a snapshot, use multiplicative
    de-vig; otherwise use raw implied probability (single-price fallback).
    """
    p_close = _side_prob(close_american, close_other)
    p_bet = _side_prob(bet_american, bet_other)
    return clv_pp(p_close, p_bet)


def evaluate_side(
    p_model: float,
    over_american: float,
    under_american: float,
    side: BetSide,
    *,
    edge_floor: float = DEFAULT_EDGE_FLOOR,
    kelly_frac: float = DEFAULT_KELLY_FRACTION,
    bankroll: float = 1.0,
) -> dict[str, float | bool | str]:
    """Score one over/under quote against a model probability for ``side``.

    ``p_model`` is P(over wins) when ``side=="over"``, else P(under wins).
    """
    p_over_mkt, p_under_mkt = devig_two_way(over_american, under_american)
    if side == "over":
        p_mkt = p_over_mkt
        price = over_american
    elif side == "under":
        p_mkt = p_under_mkt
        price = under_american
    else:
        raise ValueError("side must be 'over' or 'under'")

    e = edge(p_model, p_mkt)
    stake_frac = kelly_fraction(p_model, price, fraction=kelly_frac)
    return {
        "side": side,
        "p_model": float(p_model),
        "p_market": float(p_mkt),
        "edge": float(e),
        "price_american": float(price),
        "passes_floor": bool(e >= edge_floor),
        "kelly_frac": float(stake_frac),
        "stake": float(bankroll) * stake_frac,
    }


def _side_prob(american: float, other: float | None) -> float:
    if other is None:
        return american_to_implied_prob(american)
    # ``american`` is the bet-side price; ``other`` is the opposite side.
    # Infer which is over/under is unnecessary — multiplicative de-vig is
    # symmetric; we need the fair share for the ``american`` side.
    p_side = american_to_implied_prob(american)
    p_other = american_to_implied_prob(other)
    total = p_side + p_other
    if total <= 0:
        raise ValueError("implied probabilities must be positive")
    return p_side / total


# --- Unit anchor (1u = ¼ Kelly on edge_floor @ reference American) -------------

DEFAULT_UNIT_REF_AMERICAN = -110.0


def unit_anchor_kelly_frac(
    *,
    edge_floor: float = DEFAULT_EDGE_FLOOR,
    ref_american: float = DEFAULT_UNIT_REF_AMERICAN,
    kelly_frac: float = DEFAULT_KELLY_FRACTION,
) -> float:
    """Bankroll fraction that defines 1 unit.

    Default: 8% edge at -110 → ~4.2% of bankroll under quarter-Kelly.
    """
    p_mkt = american_to_implied_prob(ref_american)
    p_model = min(max(p_mkt + float(edge_floor), 1e-6), 1.0 - 1e-6)
    return kelly_fraction(p_model, ref_american, fraction=kelly_frac)


def bankroll_from_unit(
    unit_dollars: float,
    *,
    edge_floor: float = DEFAULT_EDGE_FLOOR,
    ref_american: float = DEFAULT_UNIT_REF_AMERICAN,
    kelly_frac: float = DEFAULT_KELLY_FRACTION,
) -> float:
    """Implied bankroll so that 1u = unit_dollars at the anchor bet."""
    anchor = unit_anchor_kelly_frac(
        edge_floor=edge_floor,
        ref_american=ref_american,
        kelly_frac=kelly_frac,
    )
    if anchor <= 0:
        raise ValueError("unit anchor Kelly fraction must be positive")
    return float(unit_dollars) / anchor


def size_in_units(
    p_model: float,
    american: float,
    *,
    edge: float | None = None,
    edge_floor: float = DEFAULT_EDGE_FLOOR,
    unit_dollars: float = 50.0,
    kelly_frac: float = DEFAULT_KELLY_FRACTION,
    ref_american: float = DEFAULT_UNIT_REF_AMERICAN,
) -> dict[str, float | bool]:
    """Map a quote to unit count under the locked floor + unit-anchor rule.

    Below ``edge_floor`` → 0 units. Otherwise
    ``units = quarter_kelly_frac / anchor_frac``.
    """
    qk = kelly_fraction(p_model, american, fraction=kelly_frac)
    anchor = unit_anchor_kelly_frac(
        edge_floor=edge_floor,
        ref_american=ref_american,
        kelly_frac=kelly_frac,
    )
    br = bankroll_from_unit(
        unit_dollars,
        edge_floor=edge_floor,
        ref_american=ref_american,
        kelly_frac=kelly_frac,
    )
    e = float(edge) if edge is not None else float("nan")
    passes = True if edge is None else bool(e >= edge_floor)
    if edge is not None and not passes:
        units = 0.0
    else:
        units = qk / anchor if anchor > 0 else 0.0
    stake = units * float(unit_dollars)
    return {
        "passes_floor": passes,
        "kelly_frac": float(qk),
        "anchor_frac": float(anchor),
        "units": float(units),
        "unit_dollars": float(unit_dollars),
        "stake": float(stake),
        "bankroll": float(br),
    }


def bet_pnl(
    stake: float,
    american: float,
    *,
    won: bool,
) -> float:
    """Profit (positive) or loss (negative) for a risked ``stake``."""
    s = float(stake)
    if s < 0:
        raise ValueError("stake must be non-negative")
    if not won:
        return -s
    return s * (american_to_decimal(american) - 1.0)


def settle_side(side: BetSide, line: float, settle_value: float) -> bool:
    """Whether ``side`` wins for a half-line (no push on .5 lines)."""
    k = float(settle_value)
    L = float(line)
    if side == "over":
        return k > L
    if side == "under":
        return k < L
    raise ValueError("side must be 'over' or 'under'")


def threshold_curve(
    edges: list[float],
    pnls: list[float],
    stakes: list[float],
    *,
    clvs: list[float | None] | None = None,
    thresholds: list[float] | None = None,
) -> list[dict[str, float | int | None]]:
    """Accept/deny sweep: metrics for bets with edge >= each threshold.

    Exploratory only until n is large and a time-split freeze is applied.
    ``ROI = sum(pnl) / sum(stake)`` on accepted bets (0 stake → roi None).
    """
    if not (len(edges) == len(pnls) == len(stakes)):
        raise ValueError("edges, pnls, stakes must be the same length")
    if clvs is not None and len(clvs) != len(edges):
        raise ValueError("clvs length must match edges")
    if thresholds is None:
        thresholds = [i / 100.0 for i in range(0, 21)]  # 0% .. 20%

    out: list[dict[str, float | int | None]] = []
    for c in thresholds:
        idx = [i for i, e in enumerate(edges) if e >= c]
        n = len(idx)
        stake_sum = float(sum(stakes[i] for i in idx))
        pnl_sum = float(sum(pnls[i] for i in idx))
        roi = (pnl_sum / stake_sum) if stake_sum > 0 else None
        mean_clv = None
        if clvs is not None:
            vals = [float(clvs[i]) for i in idx if clvs[i] is not None]
            mean_clv = (sum(vals) / len(vals)) if vals else None
        out.append(
            {
                "edge_floor": float(c),
                "n": n,
                "stake_sum": stake_sum,
                "pnl_sum": pnl_sum,
                "roi": roi,
                "mean_clv_pp": mean_clv,
            }
        )
    return out


def bootstrap_mean_ci(
    values: list[float],
    *,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Return ``(mean, lo, hi)`` percentile bootstrap CI for the mean."""
    import random

    if not values:
        raise ValueError("values must be non-empty")
    rng = random.Random(seed)
    n = len(values)
    mean = sum(values) / n
    samples: list[float] = []
    for _ in range(n_boot):
        draw = [values[rng.randrange(n)] for _ in range(n)]
        samples.append(sum(draw) / n)
    samples.sort()
    lo_i = int((alpha / 2.0) * n_boot)
    hi_i = int((1.0 - alpha / 2.0) * n_boot) - 1
    lo_i = max(0, min(lo_i, n_boot - 1))
    hi_i = max(0, min(hi_i, n_boot - 1))
    return mean, samples[lo_i], samples[hi_i]
