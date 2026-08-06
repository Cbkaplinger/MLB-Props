"""Statistical skill checks for the CLV oracle and bet ledger.

These are model-agnostic skill checks that sit on top of
`src/Python/market.py` (which owns the de-vig / edge / Kelly / CLV formulas).
The notebook and the weekly CLV-reliability artifact both draw from here so
the math has one home and one test suite.

Scope:
- ``two_proportion_z_test``: the head-to-head win-rate comparison used to
  check whether CLV-positive bets win at a different rate than CLV-non-positive
  bets (the 53.8% / 39.0% headline finding). This is the right test for two
  independent binomial proportions.
- ``bootstrap_mean_ci`` (BCa): a bias-corrected-and-accelerated bootstrap CI.
  ``market.bootstrap_mean_ci`` stays percentile-only for back-compat; this is
  the upgrade that should be used at n=30-80 where percentile intervals are
  biased and narrow.
- ``stake_weighted_bootstrap_ci``: ``sum(clv * stake) / sum(stake)`` and its
  bootstrap. Production risk is Kelly-sized, so the operating skill claim
  should be stake-weighted — this is the metric that actually scales to
  bankroll.
- ``rolling_stat_with_se``: rolling-window mean with a ±2 SE (normal
  approximation) ribbon so the dashboard can show whether the CLV signal is
  steady or dominated by 2-3 hot days.

Conventions:
- All exports are pure-Python (no numpy/scipy import required at module import
  time — keep the notebook import path light); numpy is imported lazily inside
  the bootstrap helpers only when the percentile/BCa machinery actually needs
  array operations. This matches the rest of the codebase where
  ``market.bootstrap_mean_ci`` is pure-Python too.
- CLV inputs are in **probability points** (e.g. 0.005 means +0.5pp). The
  notebook multiplies by 100 for display; tests assert the pp contract.
"""

from __future__ import annotations

import math
import random
from typing import Callable, Sequence

__all__ = [
    "two_proportion_z_test",
    "bootstrap_bca_ci",
    "stake_weighted_bootstrap_ci",
    "rolling_stat_with_se",
]


def two_proportion_z_test(
    successes_a: int,
    n_a: int,
    successes_b: int,
    n_b: int,
) -> dict[str, float]:
    """Two-proportion z-test for the difference in win rates.

    Pooled-variance z (the standard textbook form for H0: p_a == p_b).
    Returns ``(z, p_two_sided, p_a, p_b, diff)``.

    Use this to test whether ``successes_a / n_a`` differs from
    ``successes_b / n_b`` at conventional alpha levels. The headline CLV
    split (CLV≥+1.0pp win rate vs CLV<+1.0pp win rate) is exactly this case.

    The pooled estimator is appropriate under H0 (equal proportions); the
    unpooled version is only preferred for confidence intervals on the
    difference, which we report separately as the bootstrap on the diff if
    needed.
    """
    n_a = int(n_a)
    n_b = int(n_b)
    if n_a <= 0 or n_b <= 0:
        raise ValueError("n_a and n_b must be positive")
    s_a = int(successes_a)
    s_b = int(successes_b)
    if not (0 <= s_a <= n_a and 0 <= s_b <= n_b):
        raise ValueError("successes must be in [0, n]")

    p_a = s_a / n_a
    p_b = s_b / n_b
    diff = p_a - p_b

    # Pooled proportion under H0: p_a == p_b == p_pool.
    p_pool = (s_a + s_b) / (n_a + n_b)
    # Guard the degenerate cases where the SE collapses (both 0 or both 1).
    se_pool = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n_a + 1.0 / n_b))

    if se_pool == 0.0:
        # Both groups all-win or all-loss: no variance under H0. z is undefined.
        z = 0.0 if diff == 0.0 else float("inf") * math.copysign(1.0, diff)
        p_two = 0.0 if diff != 0.0 else 1.0
    else:
        z = diff / se_pool
        # Two-sided p via standard normal CDF approx (|z| -> p).
        p_two = 2.0 * (1.0 - _std_normal_cdf(abs(z)))

    return {
        "z": float(z),
        "p_two_sided": float(p_two),
        "p_a": float(p_a),
        "p_b": float(p_b),
        "diff": float(diff),
        "n_a": int(n_a),
        "n_b": int(n_b),
    }


def _std_normal_cdf(x: float) -> float:
    """Standard normal CDF via the erf identity (no scipy dependency)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bootstrap_bca_ci(
    values: Sequence[float],
    *,
    n_boot: int = 5000,
    alpha: float = 0.05,
    seed: int = 0,
    statistic: Callable[[Sequence[float]], float] | None = None,
) -> tuple[float, float, float]:
    """Return ``(mean, lo, hi)`` BCa bootstrap CI.

    BCa = bias-corrected and accelerated. At n=30-80 the percentile interval
    is biased and narrow; BCa widens the floor>=20% CI by ~25% in our use
    case and is what kills the "20% tail = real edge" hypothesis before you
    act on it.

    The acceleration ``a`` is estimated from jackknife leave-one-out means
    (the standard BCa estimator); if jackknife is degenerate (constant
    values) we fall back to the percentile interval with a warning flag set
    via the SE-computation path.

    Default ``statistic`` is the mean; pass a custom callable (e.g. median,
    stake-weighted mean) to BCa-ize any estimator.
    """
    if not values:
        raise ValueError("values must be non-empty")
    if n_boot < 10:
        raise ValueError("n_boot must be >= 10 for BCa")
    rng = random.Random(int(seed))
    n = len(values)
    stat = statistic if statistic is not None else _mean
    theta_hat = stat(values)

    # ---- Bootstrap resamples ----
    idx_cache = list(range(n))
    boot_stats: list[float] = []
    for _ in range(n_boot):
        draw = [values[rng.choice(idx_cache)] for _ in range(n)]
        boot_stats.append(stat(draw))
    boot_stats.sort()

    # ---- Bias-correction z0 ----
    # z0 = Phi^{-1}(F_hat(theta_hat)) where F_hat is the bootstrap CDF. With
    # ties (common for median/statistics with discrete support, e.g. median
    # of [1..10] resamples lands on a small set of values) the strict-less
    # count drives z0 to a degenerate extreme and inverts the BCa interval.
    # Use the mid-rank convention: (n_below + 0.5 * n_equal) / n_boot.
    n_below = sum(1 for s in boot_stats if s < theta_hat)
    n_equal = sum(1 for s in boot_stats if s == theta_hat)
    prop_below = (n_below + 0.5 * n_equal) / n_boot
    # Clamp away from 0 / 1 so the inverse-CDF is finite.
    prop_below = min(max(prop_below, 1e-6), 1.0 - 1e-6)
    z0 = _inverse_std_normal_cdf(prop_below)

    # ---- Acceleration a via jackknife ----
    a = _jackknife_acceleration(values, statistic=stat)

    # ---- BCa-adjusted quantiles ----
    def bca_quantile(p: float) -> float:
        # BCa formula: adjust the nominal quantile p by z0 and a.
        denom = 1.0 - a * (z0 + _inverse_std_normal_cdf(p))
        if denom == 0.0:
            return p  # fall back to percentile
        adj = _std_normal_cdf(z0 + (z0 + _inverse_std_normal_cdf(p)) / denom)
        # Clamp to [0, 1] and map to bootstrap array index.
        adj = min(max(adj, 0.0), 1.0)
        idx = int(round(adj * (n_boot - 1)))
        idx = min(max(idx, 0), n_boot - 1)
        return boot_stats[idx]

    lo = bca_quantile(alpha / 2.0)
    hi = bca_quantile(1.0 - alpha / 2.0)

    # Defensive monotonicity: BCa can invert at the extreme tails on degenerate
    # statistics (e.g. all-tie medians). The notebook consumes (lo, hi) for
    # error bars, so guarantee lo <= hi by construction.
    if lo > hi:
        lo, hi = hi, lo
    return float(theta_hat), float(lo), float(hi)


def stake_weighted_bootstrap_ci(
    values: Sequence[float],
    weights: Sequence[float],
    *,
    n_boot: int = 5000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float, float]:
    """BCa bootstrap CI for ``sum(values * weights) / sum(weights)``.

    Production risk is Kelly-sized, so the operating skill claim should be
    stake-weighted. Equal-weighted CLV isn't the metric that governs bankroll
    outcomes — a 5u bet with +0.3pp CLV contributes far more to realized
    edge than a 0.5u bet with the same CLV.

    ``weights`` is typically the per-bet stake; both sequences must share
    length. Weights must be non-negative and not all-zero (else undefined).
    """
    if len(values) != len(weights):
        raise ValueError("values and weights must have the same length")
    if not values:
        raise ValueError("values must be non-empty")
    w = [float(x) for x in weights]
    if any(x < 0 for x in w):
        raise ValueError("weights must be non-negative")
    if sum(w) == 0.0:
        raise ValueError("sum of weights must be positive")

    pairs = list(zip(values, w))

    def stat(sample_pairs: list[tuple[float, float]]) -> float:
        num = sum(v * wi for v, wi in sample_pairs)
        den = sum(wi for _, wi in sample_pairs)
        if den == 0.0:
            return float("nan")
        return num / den

    theta_hat = stat(pairs)

    rng = random.Random(int(seed))
    n = len(pairs)
    idx_cache = list(range(n))
    boot_stats: list[float] = []
    for _ in range(n_boot):
        draw = [pairs[rng.choice(idx_cache)] for _ in range(n)]
        boot_stats.append(stat(draw))
    boot_stats.sort()

    # Bias-correction with mid-rank ties (see bootstrap_bca_ci for rationale).
    n_below = sum(1 for s in boot_stats if s < theta_hat)
    n_equal = sum(1 for s in boot_stats if s == theta_hat)
    prop_below = (n_below + 0.5 * n_equal) / n_boot
    prop_below = min(max(prop_below, 1e-6), 1.0 - 1e-6)
    z0 = _inverse_std_normal_cdf(prop_below)
    a = _jackknife_acceleration_weighted(pairs)

    def bca_quantile(p: float) -> float:
        denom = 1.0 - a * (z0 + _inverse_std_normal_cdf(p))
        if denom == 0.0:
            return p
        adj = _std_normal_cdf(z0 + (z0 + _inverse_std_normal_cdf(p)) / denom)
        adj = min(max(adj, 0.0), 1.0)
        idx = int(round(adj * (n_boot - 1)))
        idx = min(max(idx, 0), n_boot - 1)
        return boot_stats[idx]

    lo = bca_quantile(alpha / 2.0)
    hi = bca_quantile(1.0 - alpha / 2.0)
    if lo > hi:
        lo, hi = hi, lo
    return float(theta_hat), float(lo), float(hi)


def rolling_stat_with_se(
    values: Sequence[float],
    window: int = 30,
    *,
    se_scale: float = 2.0,
) -> list[dict[str, float | None]]:
    """Rolling mean of ``values`` with a ``±se_scale × SE`` ribbon.

    SE uses the normal approximation: ``SE = std / sqrt(n_in_window)``. This is
    the day-stability check — the question is whether the CLV signal is steady
    or dominated by 2-3 hot days. A rolling 30-bet CLV chart with a ±2 SE
    ribbon resolves most of the variance-vs-skill ambiguity.

    Returns one row per bet (chronological) with keys ``idx``, ``mean``,
    ``se``, ``lo``, ``hi``, ``n``. Rows where ``n < 2`` carry ``None`` for the
    band (can't compute an SE with one observation).
    """
    if window < 2:
        raise ValueError("window must be >= 2")
    vals = [float(v) for v in values]
    out: list[dict[str, float | None]] = []
    for i in range(len(vals)):
        lo_i = max(0, i - window + 1)
        chunk = vals[lo_i : i + 1]
        n = len(chunk)
        if n == 0:
            out.append({"idx": i, "mean": None, "se": None, "lo": None, "hi": None, "n": 0})
            continue
        mean = sum(chunk) / n
        if n >= 2:
            var = sum((x - mean) ** 2 for x in chunk) / (n - 1)
            se = math.sqrt(var / n)
            out.append(
                {
                    "idx": i,
                    "mean": mean,
                    "se": se,
                    "lo": mean - se_scale * se,
                    "hi": mean + se_scale * se,
                    "n": n,
                }
            )
        else:
            out.append({"idx": i, "mean": mean, "se": None, "lo": None, "hi": None, "n": 1})
    return out


# --- internals ------------------------------------------------------------


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _jackknife_acceleration(
    values: Sequence[float],
    *,
    statistic: Callable[[Sequence[float]], float],
) -> float:
    """Standard BCa acceleration via leave-one-out jackknife.

    ``a = sum((mean_jack - jack_i)^3) / (6 * (sum((mean_jack - jack_i)^2))^1.5)``.
    Returns 0.0 if the denominator is degenerate (constant values).
    """
    n = len(values)
    if n < 3:
        return 0.0
    jack: list[float] = []
    for i in range(n):
        leave = [values[j] for j in range(n) if j != i]
        jack.append(statistic(leave))
    mean_jack = sum(jack) / n
    diffs = [mean_jack - j for j in jack]
    num = sum(d ** 3 for d in diffs)
    den_sum = sum(d ** 2 for d in diffs)
    if den_sum == 0.0:
        return 0.0
    denom = 6.0 * (den_sum ** 1.5)
    if denom == 0.0:
        return 0.0
    return num / denom


def _jackknife_acceleration_weighted(pairs: list[tuple[float, float]]) -> float:
    """Jackknife acceleration for the stake-weighted mean."""
    n = len(pairs)
    if n < 3:
        return 0.0

    def weighted_mean(sample: list[tuple[float, float]]) -> float:
        den = sum(w for _, w in sample)
        if den == 0.0:
            return float("nan")
        return sum(v * w for v, w in sample) / den

    jack: list[float] = []
    for i in range(n):
        leave = [pairs[j] for j in range(n) if j != i]
        jack.append(weighted_mean(leave))
    mean_jack = sum(jack) / n
    diffs = [mean_jack - j for j in jack]
    num = sum(d ** 3 for d in diffs)
    den_sum = sum(d ** 2 for d in diffs)
    if den_sum == 0.0:
        return 0.0
    denom = 6.0 * (den_sum ** 1.5)
    if denom == 0.0:
        return 0.0
    return num / denom


def _inverse_std_normal_cdf(p: float) -> float:
    """Inverse standard-normal CDF via bisection on ``_std_normal_cdf``.

    Pure Python (no scipy). We need correctness across (0, 1) for BCa quantile
    adjustment, and prior approximation-based attempts (Acklam, Wichura AS241)
    both had transcription bugs in the constants. Bisection converges to
    ~1e-9 in <40 evaluations; negligible against a 5000-draw bootstrap, and
    immune to constant typos. Reliability beats throughput here — the BCa
    interval validity depends on the inverse-CDF being exact, not fast.
    """
    if not (0.0 < p < 1.0):
        raise ValueError("p must be in (0, 1)")
    lo, hi = -37.0, 37.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _std_normal_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
