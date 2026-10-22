"""C-B1: exposure-profile heterogeneity (Question B, candidate 1).

RESEARCH-ONLY, synthetic-first. Implements the FIRST candidate of
card_workload_dependence_B_2026-10-20.md: per-BF-INDEX K probability
profile q_j, piecewise-constant on registered bands, estimated from the
FROZEN realized-PA training lineage with band-level shrinkage toward
the frozen cycled prefix mean, aggregated through the MERGED Question A
exact Poisson-Binomial machinery mixed over the REGISTERED BF workload.

What changes vs the frozen baseline: ONLY the per-PA probability
sequence generator (frozen cycled prefix means -> estimated exposure
profile). N unchanged; lineup construction unchanged; eligibility
unchanged. Count-RPS is the primary metric; Holm m=1.

The K label is the pa_table's frozen binary y (1 = strikeout event);
the M0 v2 receipt verified label-integrity (y == 1 iff taxonomy
class_label == 0) across the whole table, so the frozen y IS the M0
class-0 label.

No real-data execution without --i-accept-outcome-evaluation and
explicit owner authorization (same gate pattern as M0 v2).
"""
from __future__ import annotations

import numpy as np

from pregame_pa_ext import adapter as ad  # noqa: F401
from pregame_pa_ext import count_aggregation_exact as ex

# registered bands (BF index 1..60, inclusive bounds)
BANDS = ((1, 9), (10, 18), (19, 27), (28, 36), (37, 60))
N_BANDS = len(BANDS)

# pre-registered shrinkage weight (w150 convention): the band rate is
# pulled toward the frozen profile with the weight of 150 pseudo-PAs
SHRINKAGE_N = 150

# pre-registered estimation-stop tolerance (card C-B1 stop condition a)
ESTIMATION_TOLERANCE = 0.005

K_MAX = ex.ad.K_MAX
KCOUNT_CAP = ad.KCOUNT_CAP


def band_for_bf(j: int) -> int:
    """Band index (0-based) for a 1-based BF index."""
    if not 1 <= j <= KCOUNT_CAP:
        raise ValueError(f"BF index out of range 1..{KCOUNT_CAP}: {j}")
    for b, (lo, hi) in enumerate(BANDS):
        if lo <= j <= hi:
            return b
    raise AssertionError("unreachable band lookup")


def assign_bf_bands(pa: "pl.DataFrame") -> "pl.DataFrame":
    """Attach bf_index (1-based position of the PA within its pitcher's
    start, ordered by at_bat_number) and band (0-based) to realized PA
    rows. Identity grain: (game_pk, pitcher) - a starting pitcher's PAs
    all belong to one side of one game, so this IS the start's PA
    sequence."""
    import polars as pl

    need = {"game_pk", "pitcher", "at_bat_number"}
    if not need.issubset(set(pa.columns)):
        raise ValueError(f"pa frame missing columns: {sorted(need)}")
    return pa.sort("at_bat_number").with_columns(
        pl.int_range(pl.len()).over("game_pk", "pitcher")
        .add(1).alias("bf_index")
    ).with_columns(
        pl.col("bf_index").map_elements(
            lambda j: band_for_bf(int(j)), return_dtype=pl.Int8)
        .alias("band")
    )


def frozen_band_prior(pa_bands: "pl.DataFrame", slot_col: str = "p_slot",
                      ) -> np.ndarray:
    """The FROZEN cycled prefix-mean profile: per band, the mean over
    the band's lineage PAs of the frozen cycled slot probability at
    that PA's position (p_slot = the cycled tile value for the PA's
    BF index, supplied by the caller from the preserved ledger's slot
    probabilities). Returns the 5-band prior rate vector."""
    import polars as pl

    rates = np.zeros(N_BANDS)
    for b in range(N_BANDS):
        sub = pa_bands.filter(pl.col("band") == b)
        if sub.height == 0:
            raise ValueError(f"band {b} has no lineage rows: the frozen "
                             "prior is undefined (stop condition c)")
        rates[b] = float(sub[slot_col].mean())
    return rates


def shrink_band_rates(k_counts: np.ndarray, n_counts: np.ndarray,
                      prior: np.ndarray,
                      w: int = SHRINKAGE_N) -> np.ndarray:
    """q_band = (w * prior + k) / (w + n) - the pre-registered w150
    shrinkage of the empirical band K rate toward the frozen profile."""
    k_counts = np.asarray(k_counts, dtype=np.float64)
    n_counts = np.asarray(n_counts, dtype=np.float64)
    prior = np.asarray(prior, dtype=np.float64)
    if k_counts.shape != (N_BANDS,) or n_counts.shape != (N_BANDS,) \
            or prior.shape != (N_BANDS,):
        raise ValueError("band vectors must be length 5")
    if np.any(n_counts < 0) or np.any(k_counts > n_counts):
        raise ValueError("invalid band counts")
    if np.any((prior < 0) | (prior > 1)):
        raise ValueError("prior rates out of [0, 1]")
    return (w * prior + k_counts) / (w + n_counts)


def band_counts(pa_bands: "pl.DataFrame", label_col: str = "y",
                ) -> tuple[np.ndarray, np.ndarray]:
    """Per-band (K successes, total PAs) from the labeled lineage."""
    import polars as pl

    k = np.zeros(N_BANDS)
    n = np.zeros(N_BANDS)
    for b in range(N_BANDS):
        sub = pa_bands.filter(pl.col("band") == b)
        n[b] = sub.height
        k[b] = int(sub[label_col].sum())
    return k, n


def profile_from_bands(band_rates: np.ndarray) -> np.ndarray:
    """Expand the 5 band rates to the 60-slot per-BF-index profile
    (piecewise-constant on the registered bands)."""
    band_rates = np.asarray(band_rates, dtype=np.float64)
    if band_rates.shape != (N_BANDS,):
        raise ValueError("band rate vector must be length 5")
    q = np.zeros(KCOUNT_CAP)
    for b, (lo, hi) in enumerate(BANDS):
        q[lo - 1:hi] = band_rates[b]
    return q


def poisson_binomial_pmf_profile(q: np.ndarray, n: int,
                                 k_max: int = K_MAX) -> np.ndarray:
    """Exact Poisson-Binomial count PMF over the FIRST n entries of the
    exposure profile (NO cycling - the profile is already per-BF-index),
    with the registered bucket convention: k = 0..k_max-2 exact, tail
    absorbed at k = k_max-1."""
    q = np.asarray(q, dtype=np.float64)
    if q.shape != (KCOUNT_CAP,):
        raise ValueError(f"profile must have {KCOUNT_CAP} slots")
    if not 1 <= n <= KCOUNT_CAP:
        raise ValueError(f"n out of range 1..{KCOUNT_CAP}: {n}")
    if np.any((q < 0) | (q > 1)):
        raise ValueError("profile rates out of [0, 1]")
    ps = q[:n]
    dp = np.zeros(n + 1)
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


def profile_count_pmf(q: np.ndarray, bf_ext: np.ndarray,
                      k_max: int = K_MAX) -> np.ndarray:
    """C-B1 count PMF: P(K=k) = sum_n bf_ext[n-1] * PB(q_1..q_n).
    bf_ext: P(N=n) for n=1..60 (registered bf_pmf_from_37 extension)."""
    bf_ext = np.asarray(bf_ext, dtype=np.float64)
    if bf_ext.shape != (KCOUNT_CAP,):
        raise ValueError(
            f"bf_ext must have {KCOUNT_CAP} entries, got {bf_ext.shape}")
    if abs(float(bf_ext.sum()) - 1.0) > 1e-9:
        raise ValueError("bf_ext must sum to 1")
    out = np.zeros(k_max)
    for n in range(1, KCOUNT_CAP + 1):
        w = bf_ext[n - 1]
        if w > 0:
            out += w * poisson_binomial_pmf_profile(q, n, k_max=k_max)
    return out


def estimation_stop(q: np.ndarray, prior: np.ndarray,
                    tol: float = ESTIMATION_TOLERANCE) -> bool:
    """Card stop condition (a): every band within tol of the frozen
    profile -> declare no exposure signal WITHOUT evaluation."""
    q = np.asarray(q, dtype=np.float64)
    prior = np.asarray(prior, dtype=np.float64)
    if q.shape != (N_BANDS,) or prior.shape != (N_BANDS,):
        raise ValueError("band vectors must be length 5")
    return bool(np.all(np.abs(q - prior) < tol))
