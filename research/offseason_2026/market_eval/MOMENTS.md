# MOMENTS — mean/variance definitions per layer (market-eval-v1)

**Date:** 2026-10-14. What each layer's predicted mean and variance ARE, how
they are assessed, and what they cannot tell you. No formulas are new —
each restates an implemented construction (BUNDLE_EXTRACTION sections 3-4).

## BF layer (batters faced, N)

- Object: per-start 37-category BASE empirical BF PMF `pmf37_0..36`
  (index 36 = P(N >= 37)), extended by `bf_pmf_from_37(pmf37, cap=60)`:
  overflow mass P(N>=37) redistributed over n=37..60 with a geometric tail
  (per-step ratio `1 - mean_hazard`, mean of the last six implied hazards
  h(31..36)); asserts sum-to-1 within 1e-9.
- **Predicted mean:** `E[N] = sum_n n * P(N=n)` over the 1..60 support.
- **Predicted variance:** `Var(N) = sum_n n^2 P(N=n) - E[N]^2` (direct PMF
  moments of the extended distribution).
- Assessment upstream is by point error (e.g., RMSE of E[N]/E[K]) and
  interval/distribution calibration of the derived PMF — NOT by recovering a
  "true" per-start variance (a single start realizes one N, which identifies
  nothing about conditional spread).

## PA layer (per projected batter)

- Object: frozen per-PA probabilities `p_h3_raw_1..9`, `p_l5_raw_1..9`
  (projected nine-batter sequence, raw arms; calibrated variants carried for
  lineage only, unused here).
- **Predicted p:** the arm's strikeout probability for each projected
  batter-slot; binary-outcome variance is `p(1-p)` per slot.
- Distinction (important, easy to blur):
  - **K-rate uncertainty** = uncertainty about the pitcher's true K rate /
    quality (the thing H3 features estimate).
  - **Binary-outcome variance** = Bernoulli spread p(1-p) of a single PA
    GIVEN the rate. The first is parameter uncertainty; the second is
    outcome noise. The frozen arms carry only the second; nothing in the
    payload quantifies parameter uncertainty, and no layer below should be
    read as if it did.

## K-count layer (K in a start)

- Object: the mixture PMF frozen in the payload,
  `pmf_{h3,l5}_raw_0..23`:
  `P(K=k) = sum_n P(N=n) * Binom(k; n, pbar_n)`, k = 0..23 (last bucket
  absorbs >= 23), with `pbar_n` = mean of the nine projected per-PA
  probabilities CYCLED to n, n = 1..60 (KCOUNT_CAP 60).
- **Predicted mean:** `E[K] = sum_n P(N=n) * n * pbar_n` (payload
  `mean_k_h3_raw` / `mean_k_l5_raw`).
- **Predicted variance** (law of total variance, from the same mixture):
  `Var(K) = E[ n * pbar_n * (1 - pbar_n) ] + Var( n * pbar_n )`
  = within-workload binomial spread + between-workload (BF) spread. The
  count PMF therefore includes workload (N) uncertainty by construction.
- **Modeled-dependence caveat (documented approximation):** the combiner
  assumes N and the per-PA outcomes are INDEPENDENT, and the per-PA
  outcomes i.i.d. with common pbar_n. Real starts violate both (lineup
  quality varies, pitcher fatigue correlates outcomes within a start). The
  frozen PMF's variance is therefore an approximation; nothing downstream
  re-derives or corrects it.

## What single starts can and cannot reveal

One start yields ONE binary outcome per PA and ONE K — it cannot reveal the
true conditional variance of the generating process. Variance claims are
therefore never per-start; assessment is ACROSS forecasts, via:

- interval coverage / sharpness of PMF-derived central intervals (count
  layer) — NOTE: 50%/90% interval metrics are PROPOSED in METRIC_SCHEMA,
  not persisted in start_metrics_v2; today's persisted errors are RPS,
  log score, RMSE of E[K], and PMF-tail Brier (ge6/8/10/12);
- distribution scores (RPS/log score) over the full PMF;
- at the market layer, multi-class Brier over {win, push, lose} classes on
  matched contracts (the registered PIN), plus slate-date bootstrap CIs.

## Market layer moments (for completeness)

- `p_market` = proportional de-vig win probability from the PAIRED
  contemporaneous over/under prices (same book, same snapshot) — a point
  probability with no market variance model; `break_even = 1/decimal`;
  push mass 0 by the de-vig construction (this cohort has zero integer-line
  contracts, so the limitation is unexercised).
