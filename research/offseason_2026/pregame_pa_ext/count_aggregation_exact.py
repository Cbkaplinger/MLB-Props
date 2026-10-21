"""RESEARCH-ONLY exact count aggregator (Question A scoping).

NOT PRODUCTION: nothing in the frozen lane calls this module. It exists to
make the heterogeneous aggregation question concrete: the REGISTERED
machinery (adapter.cycled_cond_mean + count_pmf_from_mixture) models the
first n batters faced as i.i.d. Binomial(k; n, pbar_n) with pbar_n = mean
of the first n slot probabilities (cycled prefix mean). This module
computes the EXACT heterogeneous alternative: the Poisson-Binomial over
the individual cycled per-PA probabilities, mixed over the SAME BF
workload distribution with the SAME 24-bucket tail convention.

Conventions reused from the frozen recipe (adapter.py / kcount_combiner):
- cycling order: slot probabilities p1..p9 tiled and truncated to n
  (identical to cycled_cond_mean's tile);
- KCOUNT_CAP = 60 (BF support 1..60);
- K_MAX = 24 buckets (k = 0..22 exact, tail absorbed at k = 23).

No real data, no fitting, no production change. Synthetic-only callers.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pregame_pa_ext import adapter as ad  # noqa: E402


def cycled_probabilities(p9, n: int) -> np.ndarray:
    """The per-PA probabilities for the first n batters faced, in the
    registered cycling order (identical tile/truncate as
    adapter.cycled_cond_mean)."""
    p9 = np.asarray(p9, dtype=np.float64)
    if p9.shape != (9,):
        raise ValueError(f"expected 9 slot probabilities, got {p9.shape}")
    if not 1 <= n <= ad.KCOUNT_CAP:
        raise ValueError(f"n out of range 1..{ad.KCOUNT_CAP}: {n}")
    return np.tile(p9, ad.KCOUNT_CAP // 9 + 1)[:n]


def poisson_binomial_pmf_cycled(p9, n: int,
                                k_max: int = ad.K_MAX) -> np.ndarray:
    """Exact Poisson-Binomial count PMF for the first n cycled per-PA
    probabilities: k = 0..k_max-2 exact, tail (k >= k_max-1) absorbed into
    the last bucket - the registered bucket convention."""
    ps = cycled_probabilities(p9, n)
    dp = np.zeros(len(ps) + 1)
    dp[0] = 1.0
    for i, p in enumerate(ps, 1):
        nxt = np.zeros(i + 1)
        nxt[:i] += dp[:i] * (1.0 - p)
        nxt[1:i + 1] += dp[:i] * p
        dp = nxt
    out = np.zeros(k_max)
    top = min(len(dp), k_max - 1)
    out[:top] = dp[:top]
    out[k_max - 1] += dp[k_max - 1:].sum()
    return out


def exact_count_pmf(p9, bf_ext: np.ndarray,
                    k_max: int = ad.K_MAX) -> np.ndarray:
    """Exact heterogeneous aggregation over the BF workload:
    P(K=k) = sum_n bf_ext[n-1] * PB(p9, n). bf_ext: P(N=n) for n=1..60
    (same convention as the registered bf_pmf_from_37 extension)."""
    bf_ext = np.asarray(bf_ext, dtype=np.float64)
    if bf_ext.shape != (ad.KCOUNT_CAP,):
        raise ValueError(
            f"bf_ext must have {ad.KCOUNT_CAP} entries, got {bf_ext.shape}")
    if abs(float(bf_ext.sum()) - 1.0) > 1e-9:
        raise ValueError("bf_ext must sum to 1")
    out = np.zeros(k_max)
    for n in range(1, ad.KCOUNT_CAP + 1):
        w = bf_ext[n - 1]
        if w > 0:
            out += w * poisson_binomial_pmf_cycled(p9, n, k_max=k_max)
    return out
