"""Minimal baseline benchmark arms for the frozen count layer.

Implements the three-level baseline ladder as small prediction functions
over EXISTING machinery -- no new harness, no model search:

- Arm P (population): a shared empirical K-count distribution estimated
  from the declared training window's realized K outcomes. Answers:
  does ANY personalization add value?
- Arm S (simple pitcher): a shrunk historical pitcher K rate (the
  registered W_PRIOR=150 shrinkage form) mixed with the FIXED registered
  workload PMF through the registered `combine_count` machinery.
  Answers: does pitcher identity/history add value, holding workload
  fixed?
- Arm F (frozen incumbent): the registered count layer (existing
  `pmf_h3_raw` in the preserved ledger / registered machinery).

REGISTERED CONTRACT (fixed before any outcome scoring):

1. Population: identical eligible start keys across arms = the
   registered block_2025H1 eligible cohort (exclusion_reason null,
   hash `f77d7a66...`, n=2,509). Exclusions reported, never absorbed
   silently by any arm.
2. Time: every baseline parameter is estimated from block_2024H2
   outcomes ONLY (game_date <= 2024-12-31). The evaluation cohort
   (block_2025H1) outcomes never enter any estimate. confirm_2025H2 and
   2026 are never touched.
3. Prediction contract: identical 24-bucket support (k=0..23, last
   bucket absorbs K >= 23) and the registered tail/normalization
   conventions; capped bucket-23 mean is labeled separately from any
   uncapped expectation.
4. Scoring: ONE primary contrast -- paired count-RPS vs the frozen
   incumbent, per start on identical keys, resampled by the registered
   slate-date scheme (`batt_recency.load_registered_comparison().
   slate_date_draws`). Reliability/ECE/MCE and residual MAE/RMSE are
   diagnostics only; the winner is NOT chosen by ECE binning.
5. Provenance: code identity + input identities recorded in receipts
   (existing pattern).
6. Interpretation: all inspected development data remain development
   data; nothing here is a fresh final test.

Cold-start rule (declared): a pitcher with no training-window history
receives the population shrunk rate (the same fallback convention as
the frozen attach machinery's league-rate EW fallback).

Component isolation: P vs S vs F vary ONLY the K information while the
workload input is held fixed for S and F (registered BF). A workload
comparison (registered BF vs empirical BF) is a SEPARATE later arm and
is deliberately out of scope here.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import kcount_combiner as kc  # noqa: E402
from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402

TRAIN_BLOCK = "block_2024H2"
EVAL_BLOCK = "block_2025H1"
W_PRIOR = ad.W_PRIOR  # registered shrinkage weight (150) -- reuse
K_MAX = ad.K_MAX      # 24 buckets; last absorbs >= 23 -- reuse


class BaselineError(RuntimeError):
    """Baseline benchmark guards fail loud."""


def _sha_file(path) -> str:  # noqa: ANN001
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def empirical_k_pmf(k_values, k_max: int = K_MAX) -> np.ndarray:  # noqa: ANN001
    """Arm P: shared empirical K-count PMF from training-window realized
    K outcomes, on the registered 24-bucket support (bucket 23 absorbs
    K >= 23). Pure over injected values; no evaluation outcomes."""
    ks = np.asarray(list(k_values), dtype=np.int64)
    if ks.size == 0:
        raise BaselineError(
            "empirical_k_pmf: empty training values (cold population)")
    if ks.min() < 0:
        raise BaselineError("negative realized K in training values")
    counts = np.zeros(k_max)
    for k in ks:
        counts[min(int(k), k_max - 1)] += 1.0
    pmf = counts / counts.sum()
    return pmf


def empirical_bf37(bf_values) -> np.ndarray:  # noqa: ANN001
    """Arm-P/S workload reference: empirical BF distribution over the
    registered 37-category support (index 36 = P(N >= 37)) from
    training-window realized BF. Pure over injected values."""
    v = np.asarray(list(bf_values), dtype=np.int64)
    if v.size == 0:
        raise BaselineError(
            "empirical_bf37: empty training values (cold population)")
    if v.min() < 1:
        raise BaselineError("realized BF below 1 in training values")
    pmf = np.zeros(37)
    for b in v:
        pmf[min(int(b), 37) - 1] += 1.0
    return pmf / pmf.sum()


def shrunk_pitcher_rates(train_rows: pl.DataFrame,
                         w_prior: int = W_PRIOR) -> dict:
    """Arm S: per-pitcher K-per-BF probability, shrunk toward the
    training-window league rate with the registered w150 form
    ((k + W * lg) / (n + W) -- identical arithmetic to the frozen
    attach machinery). train_rows: training-window rows with pitcher,
    realized_k, realized_bf. Cold-start: pitchers absent from training
    receive the population rate at lookup time (declared fallback)."""
    if train_rows.height == 0:
        raise BaselineError("empty training window")
    g = train_rows.group_by("pitcher").agg(
        k=pl.col("realized_k").sum(), n=pl.col("realized_bf").sum())
    lg = (float(train_rows["realized_k"].sum())
          / float(train_rows["realized_bf"].sum()))
    rates = {}
    for r in g.iter_rows(named=True):
        rates[int(r["pitcher"])] = (
            (float(r["k"]) + w_prior * lg) / (float(r["n"]) + w_prior))
    return {"rates": rates, "population_rate": lg,
            "w_prior": w_prior}


def pitcher_arm_pmf(p_bar: float, bf37: np.ndarray) -> np.ndarray:
    """Arm S distribution: a single shrunk rate mixed over the FIXED
    workload PMF through the registered machinery (same support/tail
    conventions as the frozen layer)."""
    return kc.combine_count(ad.bf_pmf_from_37(np.asarray(bf37,
                                                        dtype=np.float64)),
                            float(p_bar), k_max=K_MAX)


def population_arm_pmf(k_values, k_max: int = K_MAX) -> np.ndarray:  # noqa: ANN001
    return empirical_k_pmf(k_values, k_max)


def mean_k_capped(pmf: np.ndarray) -> float:
    """Capped expectation over the 24-bucket support (bucket 23 counted
    as exactly 23) -- NOT the uncapped E[K]; label separately."""
    pk = np.asarray(pmf, dtype=np.float64)
    return float((np.arange(len(pk)) * pk).sum())


def build_arms(train_rows: pl.DataFrame, starts: pl.DataFrame,
               bf_lookup: dict) -> dict:
    """Fit the two reference arms on TRAINING rows only and emit per-start
    PMFs on the registered support for the given eligible starts.

    starts: eligible evaluation starts (game_pk, side, pitcher).
    bf_lookup: start key -> bf37 vector (the FIXED registered workload).
    Returns {arm: {start_key: pmf}} plus declared settings.
    """
    rates = shrunk_pitcher_rates(train_rows)
    pop_pmf = population_arm_pmf(
        train_rows["realized_k"].to_numpy())
    arms_p = {}
    arms_s = {}
    for key in starts.iter_rows():
        k = (int(key[0]), str(key[1]), int(key[2]))
        arms_p[k] = pop_pmf
        p_bar = rates["rates"].get(k[2], rates["population_rate"])
        arms_s[k] = pitcher_arm_pmf(p_bar, bf_lookup[k])
    return {"population": arms_p, "pitcher": arms_s,
            "settings": {
                "train_block": TRAIN_BLOCK,
                "w_prior": W_PRIOR,
                "support_buckets": K_MAX,
                "tail_bucket": K_MAX - 1,
                "cold_start_rule": "population_rate_fallback",
                "n_population_train_starts": int(train_rows.height),
                "population_rate": rates["population_rate"],
            }}


def paired_contrast(scores_a: dict, scores_b: dict, dates: dict,
                    blocks: list, *, n_boot: int = 2000,
                    seed: int = 20261001) -> dict:
    """Registered paired comparison: per-start score differences
    resampled by the slate-date scheme (existing machinery). scores_*:
    start key -> per-start score (e.g., count-RPS); dates: start key ->
    game_date; blocks: per-start block labels (same length as the key
    list, matching the registered slate_date_draws signature)."""
    keys = sorted(set(scores_a) & set(scores_b))
    if not keys:
        raise BaselineError("no common scored keys for the paired contrast")
    a = np.asarray([scores_a[k] for k in keys], dtype=np.float64)
    b = np.asarray([scores_b[k] for k in keys], dtype=np.float64)
    cmp_mod = br.load_registered_comparison()
    res = cmp_mod.slate_date_draws(
        {"a": a, "b": b}, [dates[k] for k in keys], blocks,
        n_boot=n_boot, seed=seed)
    delta = float(a.mean() - b.mean())
    reps = res[:, 0] - res[:, 1]
    ci = [float(np.percentile(reps, 2.5)),
          float(np.percentile(reps, 97.5))]
    return {"mean_a": float(a.mean()), "mean_b": float(b.mean()),
            "delta_a_minus_b": delta, "ci95": ci, "n_starts": len(keys),
            "n_boot": n_boot, "seed": seed}
