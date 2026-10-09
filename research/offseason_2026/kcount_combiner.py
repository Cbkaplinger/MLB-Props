"""K-count combiner: BF distribution x per-PA K probability -> count PMF.

Implements the integration design in
`research/offseason_2026/kcount-integration-prereg-draft.md`.
Pure functions over injected arrays; NO file I/O, NO real-data scoring.

Conventions (frozen):
- BF PMF input: 37-vector, index 0..35 = P(BF=1..36), index 36 =
  P(BF>=37) overflow mass. Overflow is NEVER read as BF=37.
- Overflow extension: constant-hazard continuation h_n = h_36 for
  n = 37..KCOUNT_CAP (60), then truncation + renormalization.
- Count model: P(K=k) = sum_n P(N=n) * Binom(k; n, p_bar)
  (conditional independence of PAs declared as a v1 approximation).
- K support: 0..KCOUNT_CAP; exceedances P(K>=m) are structurally
  monotone (derived from one CDF).
"""

from __future__ import annotations

import numpy as np
from math import lgamma

KCOUNT_CAP = 60
N_MAX = 36


def extend_overflow_with_hazard(hazards36: np.ndarray,
                                cap: int = KCOUNT_CAP) -> np.ndarray:
    """Hazard vector (36,) -> full BF PMF over 1..cap.

    Body 1..36 from the hazards; the overflow mass P(N>=37) is
    REDISTRIBUTED over 37..cap proportionally to a geometric tail with
    ratio (1 - h_36), renormalized to sum exactly to the overflow.
    """
    hazards36 = np.asarray(hazards36, dtype=float)
    if hazards36.shape != (N_MAX,):
        raise ValueError("hazards must have length %d" % N_MAX)
    if bool(((hazards36 < 0) | (hazards36 > 1)).any()):
        raise ValueError("hazards must lie in [0, 1]")
    pmf = np.empty(cap)
    survival = 1.0
    for n in range(1, N_MAX + 1):
        pmf[n - 1] = survival * hazards36[n - 1]
        survival *= 1.0 - hazards36[n - 1]
    overflow = survival  # P(N >= 37)
    tail_h = float(hazards36[-1])
    shape = np.array([(1 - tail_h) ** (n - N_MAX - 1) * tail_h
                      for n in range(N_MAX + 1, cap + 1)])
    shape = shape / shape.sum()
    pmf[N_MAX:] = overflow * shape
    return pmf


def bf_pmf_from_37(bf_pmf37: np.ndarray, cap: int = KCOUNT_CAP
                   ) -> np.ndarray:
    """37-category PMF (index 36 = P(N>=37)) -> 1..cap PMF.

    The overflow mass is redistributed over 37..cap with a geometric
    tail whose per-step ratio is 1 minus the mean hazard implied by
    indices 31..36 (frozen, documented approximation for PMFs saved
    WITHOUT their hazard vectors).
    """
    pmf37 = np.asarray(bf_pmf37, dtype=float)
    if pmf37.shape != (37,):
        raise ValueError("expected 37-category BF PMF")
    out = np.zeros(cap)
    out[:36] = pmf37[:36]
    overflow = float(pmf37[36])
    surv = 1.0
    hs = []
    for n in range(1, 37):
        h = pmf37[n - 1] / surv if surv > 0 else 0.0
        hs.append(min(max(h, 0.0), 1.0))
        surv -= pmf37[n - 1]
    tail_h = float(np.mean(hs[-6:]))
    if overflow > 0.0 and tail_h > 0.0:
        shape = np.array([(1 - tail_h) ** (n - 37) * tail_h
                          for n in range(37, cap + 1)])
        shape = shape / shape.sum()
        out[36:] = overflow * shape
    else:
        out[36:] = 0.0  # zero overflow or zero tail hazard: nothing to place
    assert abs(out.sum() - 1.0) < 1e-9, "BF PMF does not sum to 1"
    return out


def binom_pmf(k_support: np.ndarray, n: int, p: float) -> np.ndarray:
    """P(K=k) for k in k_support given n trials, prob p (vectorized)."""
    ks = np.asarray(k_support, dtype=int)
    out = np.zeros(len(ks))
    if n == 0:
        out[ks == 0] = 1.0
        return out
    if p <= 0.0:
        out[ks == 0] = 1.0
        return out
    if p >= 1.0:
        out[ks == n] = 1.0
        return out
    log1m = np.log(1 - p)
    for i, k in enumerate(ks):
        if k > n:
            continue
        # log-space binomial coefficient (lgamma): math.comb overflows
        # int64 for n > ~66 and numpy then fails on object dtype
        log_coef = (lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1))
        out[i] = np.exp(log_coef + k * np.log(p)
                        + (n - k) * log1m)
    return out


def combine_count(bf_pmf: np.ndarray, p_bar: float,
                  k_max: int = 24) -> np.ndarray:
    """P(K=k) for k=0..k_max (k_max bucket absorbs >=k_max) from a BF
    PMF over 1..cap and a per-PA K probability. Conditional independence
    of PAs is the declared v1 approximation."""
    bf = np.asarray(bf_pmf, dtype=float)
    if p_bar < 0.0 or p_bar > 1.0:
        raise ValueError("p_bar must lie in [0, 1]")
    ks = np.arange(0, k_max)  # exact categories 0..k_max-1
    out = np.zeros(k_max)
    for n_idx, pn in enumerate(bf):
        if pn <= 0.0:
            continue
        n = n_idx + 1
        out += pn * binom_pmf(ks, n, p_bar)
    # tail: K >= k_max accumulates into the last bucket
    tail = max(0.0, 1.0 - out.sum())
    out[k_max - 1] += tail
    return out


def exceedance(p_k: np.ndarray, m: int) -> float:
    """P(K >= m) from the count PMF over 0..k_max-1 (last bucket =
    >= k_max-1). Structurally monotone in m."""
    pk = np.asarray(p_k, dtype=float)
    if m <= 0:
        return 1.0
    if m >= len(pk):
        return 0.0
    return float(pk[m:].sum())


def count_rps(p_k: np.ndarray, k: int) -> float:
    """Discrete RPS over the count support (summed convention, matching
    the BF lane's unnormalized RPS; last bucket absorbs the tail)."""
    pk = np.asarray(p_k, dtype=float)
    cdf = np.cumsum(pk)
    k = int(k)
    last = len(pk) - 1
    hit = min(k, last)
    total = 0.0
    for t in range(len(pk)):
        obs = 1.0 if t >= hit else 0.0
        if t == last and k > last:
            obs = 1.0
        total += (cdf[t] - obs) ** 2
    return float(total)


def count_logscore(p_k: np.ndarray, k: int, clip: float = 1e-12) -> float:
    pk = np.asarray(p_k, dtype=float)
    k = int(k)
    idx = min(k, len(pk) - 1)
    return float(-np.log(max(pk[idx], clip)))


def milestone_brier(p_k: np.ndarray, k: int, milestones=(6, 7, 8, 9, 10, 12)
                    ) -> dict:
    pk = np.asarray(p_k, dtype=float)
    out = {}
    for m in milestones:
        p_ge = exceedance(pk, m)
        y = 1.0 if k >= m else 0.0
        out["ge%d" % m] = (p_ge - y) ** 2
    return out


def expected_bf(bf_pmf_ext: np.ndarray) -> float:
    """E[N] under a BF PMF over 1..cap (extended vector, index 0 = BF 1)."""
    bf = np.asarray(bf_pmf_ext, dtype=float)
    return float((np.arange(1, len(bf) + 1) * bf).sum())


def point_exposure_n(bf_pmf37: np.ndarray) -> int:
    """C1 point exposure: E[N] from the EXTENDED BF PMF (overflow
    redistributed over 37..60 first), rounded to the nearest integer
    (ties away from zero), floored at 1. Frozen convention."""
    ext = bf_pmf_from_37(bf_pmf37)
    e = expected_bf(ext)
    n = int(np.floor(e + 0.5))  # round-half-up, deterministic
    return max(1, n)


def reassign_overflow(bf_pmf37: np.ndarray, lo: int, hi: int,
                      weights: np.ndarray) -> np.ndarray:
    """I5 deep-tail challenger: move the overflow mass P(N>=37)
    (index 36) into the prespecified exact-position interval
    [lo, hi] using the given weights (normalized internally).

    Frozen semantics (i5 prereg): body mass at BF 1..(hi) is RETAINED
    (the reassignment ADDS mass on top of existing body mass at the
    receiving positions); overflow beyond `hi` becomes zero. weights
    must have length hi - lo + 1; slots with zero weight receive no
    mass; the result sums to 1 and stays nonnegative. This is an
    ESTIMATED transformation (weights estimated from strictly
    pre-origin training data), not fit-free."""
    pmf37 = np.asarray(bf_pmf37, dtype=float)
    if pmf37.shape != (37,):
        raise ValueError("expected 37-category BF PMF")
    if not (1 <= lo <= hi <= 36):
        raise ValueError("interval must satisfy 1 <= lo <= hi <= 36")
    w = np.asarray(weights, dtype=float)
    if w.shape != (hi - lo + 1,):
        raise ValueError("weights must have length hi - lo + 1")
    if bool((w < 0).any()):
        raise ValueError("weights must be nonnegative")
    if w.sum() <= 0:
        raise ValueError("weights must sum to a positive mass")
    w = w / w.sum()
    out = np.array(pmf37, dtype=float)
    overflow = float(out[36])
    out[36] = 0.0
    for k, slot in enumerate(range(lo, hi + 1)):
        out[slot - 1] += overflow * w[k]
    assert abs(out.sum() - 1.0) < 1e-9, "mass not conserved"
    assert bool((out >= -1e-15).all()), "negative PMF entry"
    return out


def validate_provenance(provenance: dict) -> None:
    """Scored-run guard: every dependency provenance entry must be a real
    64-char sha256. The CI 'external-preserved (not available)' marker is
    NOT acceptable scientific provenance - a scored run with it fails."""
    if not isinstance(provenance, dict) or not provenance:
        raise ValueError(
            "scored-run provenance missing entirely: mandatory scientific "
            "evidence blocks the run")
    for name, entry in provenance.items():
        if (not isinstance(entry, str) or len(entry) != 64
                or any(c not in "0123456789abcdef" for c in entry.lower())):
            raise ValueError(
                "scored-run provenance invalid for %r: %r (missing "
                "mandatory scientific evidence blocks the run)"
                % (name, entry))
