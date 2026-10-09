"""Ordered starter-only opportunity layer (I3 experiment machinery).

Implements the frozen arm definitions in
`research/offseason_2026/pregame-opportunity-contract-draft.md`
(I3 readiness pass, 2026-10-08). Pure functions over injected arrays;
NO file I/O, NO real-data scoring.

Conventions (frozen):
- Starter faces the opposing order starting at slot 1; potential
  opportunity t (BF position t) faces slot ((t-1) mod 9) + 1.
- Survival S(t) = P(N >= t) from the EXTENDED BF PMF (1..cap).
- Conditional count given N=n: Poisson-binomial over the first n
  cycled slot probabilities, with the same absorbing >=23 bucket as
  `kcount_combiner.combine_count` (K_MAX = 24 categories).
- I3b comparator: homogeneous binomial at
  p* = sum_t S(t) p_t / E[N]  (expected-K parity with I3a by
  construction; asserted by callers).
- The starter's own removal is carried entirely by the BF PMF (no
  joint workload-performance feedback - declared v1 approximation).
"""

from __future__ import annotations

import numpy as np

import kcount_combiner as kc

K_MAX = 24
SLOT_COUNT = 9


def bf_survival(bf_ext: np.ndarray) -> np.ndarray:
    """S(t) = P(N >= t) for t = 1..cap from an extended BF PMF
    (index i = BF i+1). S(1) = 1; S is non-increasing."""
    pmf = np.asarray(bf_ext, dtype=float)
    s = np.cumsum(pmf[::-1])[::-1]
    return s


def card_first_nine(pa_rows: list[int], slot_count: int = SLOT_COUNT
                    ) -> list[int]:
    """First `slot_count` DISTINCT batters in first-plate-appearance
    order (the frozen Statcast proxy for the carded nine).

    pa_rows: batter ids ordered by first-PA appearance (caller sorts
    by at_bat_number). Raises if fewer than slot_count distinct
    batters appear (fail-loud; never silently short-slot).
    """
    seen: list[int] = []
    for b in pa_rows:
        if b not in seen:
            seen.append(b)
        if len(seen) == slot_count:
            return seen
    raise ValueError("fewer than %d distinct batters in prior game "
                     "(got %d)" % (slot_count, len(seen)))


def slot_probs(card: list[int], p_pitcher: float, batter_rates: dict,
               lg: float, w: float) -> np.ndarray:
    """Per-slot log5 K probabilities for the ordered card.

    batter_rates: dict batter_id -> (shrunk_rate, prior_n) from the
    frozen strictly-prior pools (cold start -> league rate). Same
    clipping as the PA-K lane."""
    lg_safe = lg if lg == lg else 0.2
    z_p = float(np.log(max(p_pitcher, 1e-9) / (1 - max(p_pitcher, 1e-9))))
    z_lg = float(np.log(lg_safe / (1 - lg_safe)))
    out = np.empty(len(card), dtype=float)
    for i, b in enumerate(card):
        r = batter_rates.get(b, (lg_safe, 0))[0]
        z = z_p + float(np.log(max(r, 1e-9) / (1 - max(r, 1e-9)))) - z_lg
        out[i] = 1.0 / (1.0 + np.exp(-z))
    return np.clip(out, 1e-6, 1 - 1e-6)


def opportunity_sequence(slot_p: np.ndarray, cap: int) -> np.ndarray:
    """p_t for potential opportunities t = 1..cap: the starter faces
    slots in order, cycling every 9."""
    slot_p = np.asarray(slot_p, dtype=float)
    if len(slot_p) != SLOT_COUNT:
        raise ValueError("expected %d slot probabilities" % SLOT_COUNT)
    idx = (np.arange(cap) % SLOT_COUNT)
    return slot_p[idx]


def pb_prefix_dists(seq_p: np.ndarray, k_max: int = K_MAX
                    ) -> np.ndarray:
    """Incremental Poisson-binomial prefix count distributions.

    Returns an (len(seq_p), k_max) array: row n-1 = P(K=k | first n
    Bernoulli(p_t) outcomes) for k = 0..k_max-1, with bucket k_max-1
    absorbing the >= (k_max-1) tail (same convention as
    kc.combine_count)."""
    seq = np.asarray(seq_p, dtype=float)
    if seq.ndim != 1 or len(seq) == 0:
        raise ValueError("seq_p must be a non-empty 1-D array")
    if ((seq < 0) | (seq > 1)).any():
        raise ValueError("probabilities must lie in [0, 1]")
    last = k_max - 1
    d = np.zeros(k_max)
    d[0] = 1.0
    out = np.empty((len(seq), k_max))
    for n, p in enumerate(seq):
        nd = np.empty(k_max)
        nd[0] = (1.0 - p) * d[0]
        for k in range(1, last):
            nd[k] = (1.0 - p) * d[k] + p * d[k - 1]
        # absorbing bucket: stay (1-p) or arrive from below, plus
        # mass that would exceed the bucket under an unbounded count
        nd[last] = (1.0 - p) * d[last] + p * (d[last - 1] + d[last])
        d = nd
        out[n] = d
    return out


def mixture_ordered(bf_ext: np.ndarray, slot_p: np.ndarray,
                    k_max: int = K_MAX) -> np.ndarray:
    """P(K=k) = sum_n P(N=n) * PB_prefix_n  over the ordered slots.

    bf_ext: extended BF PMF over 1..cap (index i = BF i+1)."""
    bf = np.asarray(bf_ext, dtype=float)
    seq = opportunity_sequence(slot_p, len(bf))
    pre = pb_prefix_dists(seq, k_max)
    out = (bf[:, None] * pre).sum(axis=0)
    tail = max(0.0, 1.0 - out.sum())
    out[k_max - 1] += tail
    return out


def expected_k_ordered(bf_ext: np.ndarray, slot_p: np.ndarray) -> float:
    """E[K] = sum_t S(t) * p_t  (t = 1..cap; frozen factorized form)."""
    s = bf_survival(bf_ext)
    seq = opportunity_sequence(slot_p, len(bf_ext))
    return float((s * seq).sum())


def p_star(bf_ext: np.ndarray, slot_p: np.ndarray) -> float:
    """Homogeneous-probability comparator rate: p* = E[K]/E[N]."""
    en = kc.expected_bf(bf_ext)
    if en <= 0:
        raise ValueError("E[N] must be positive")
    return expected_k_ordered(bf_ext, slot_p) / en
