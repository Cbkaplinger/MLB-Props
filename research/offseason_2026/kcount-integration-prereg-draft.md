# DRAFT prereg — K-count integration (2026-10-07)

> **Status: DRAFT.** Not frozen, not authorized, not scored. Frozen prereg
> authored from this draft only after owner authorization. Origin: owner
> order 2026-10-07 ("K-Count Integration + Challenger Roadmap").

## Question

Does the factorized K-count distribution (expanding-BF distribution x
log5 PA-K probability) produce calibrated full-count and upper-tail
probabilities on the developmental 2023 windows — and does the full BF
distribution add value over a point-exposure binomial?

## Combination (frozen)

P(K=k | X) = sum_n P(N=n | X) * BinomPMF(k; n, p_bar)

- **BF distribution:** expanding-training termination hazard (the
  training-policy research comparator). Eval-row PMFs are reused from
  the saved `workload-training-policy-20261007_090000` pmfs (frozen
  artifacts, no refit); overflow extended by the frozen redistribution
  rule over BF=37..60 (geometric tail, ratio 1−h_36; junction step
  documented). K-count support 0..24 with an absorbing >=24 bucket.
- **p_bar (per pitcher-game, pregame):** log5 benchmark (PA-K arm A),
  w=150, from strictly-prior first-pitcher PA tables (2023 train rows +
  2022 prior-season aggregates). Two frozen lineup assumptions:
  - **L1 league-average batter:** p_b = league rate -> p_bar = pitcher
    shrunk rate blended to lg (fully deployable).
  - **L2 opposing-team aggregate:** p_b = opposing team's shrunk K rate
    (roster-level, strictly prior; team identity from the spine keys'
    home/away + is_home). Also fully deployable.
- **Independence:** PAs conditionally independent given inputs — declared
  v1 approximation; dispersion checked diagnostically (variance ratio
  vs binomial), never tuned on eval outcomes.
- **NOT deployable inputs (prohibited):** realized lineup/order, realized
  BF, realized per-PA outcomes. A realized-lineup arm may exist ONLY as a
  labeled non-deployable diagnostic ceiling.

## Arms on identical rows (the 4,446 training-policy eval pitcher-games)

| Arm | Exposure | p_bar source | Deployable |
| --- | --- | --- | --- |
| **I1** | full expanding BF distribution | L1 league-average | yes |
| **I2** | full expanding BF distribution | L2 team aggregate | yes |
| **C1 comparator** | point exposure E[N] (from the same BF PMF) | same as paired I-arm | yes |
| **C2 oracle** | realized BF (binomial) | realized-lineup p_bar | **NO — diagnostic ceiling** |

Primary comparison: I1 vs C1 (does the distribution beat point exposure?).
I2 vs I1 (does team-level batter info help?). C2 labeled non-deployable.

## Scores (frozen)

- **Primary:** pooled paired count-RPS (I1 − C1), date-clustered
  bootstrap 2,000 resamples, seed 20261001. **Gate (pass/fail): 95% CI
  entirely below 0.**
- **Secondary (prespecified):** count log score; MAE of the declared
  functional (mean of the count PMF); per-milestone Brier + reliability
  bands for K≥6/7/8/9/10/12 (minimum_k convention; over x.5 ≡ K≥x+1);
  dispersion diagnostic (observed count variance vs binomial variance
  by p_bar band); monotonicity check (structural, asserted).
- Row-identity hash across arms; 2023 DEVELOPMENTAL; no market inputs in
  the independent-baseball arm; no promotion claim.

## Known assumptions / blockers (disclosed, not hidden)

1. Lineup: L1/L2 are assumptions; realized lineups are NOT used for any
   deployable arm (lineup source acquisition = future lane).
2. BF overflow: redistribution rule is an approximation; junction step
   documented; K-count tail beyond BF=60 truncated (structurally zero).
3. Dependence: workload and K-rate are modeled independent given inputs;
   pitch-efficiency feedback (K-heavy outings shorten/lengthen BF) is
   NOT modeled — factorization is an assumption under test, and the C2
   oracle quantifies its ceiling.
4. PA independence: binomial dispersion may understate tails; the
   dispersion diagnostic measures this before any beta-binomial v2.

## Benchmark matrix (bounded FUTURE work — not scored in this run)

Chronological inner tuning (pre-origin only) + fixed outer scoring on the
declared development windows; 2023 is DEVELOPMENTAL EXPOSURE already.

| # | Challenger | Tuning budget | Notes |
| --- | --- | --- | --- |
| 1 | Same-feature tuned logistic (PA lane) | C grid {0.03,0.1,0.3,1,3} inner-chrono | tests the PA result's specification, not handedness |
| 2 | Same-feature LightGBM (PA lane) | Optuna ~25 trials, inner-chrono, frozen space | first flexible tabular challenger |
| 3 | Same-feature tuned logistic (BF hazard lane) | L2 grid, inner-chrono | pairs with #1 |
| 4 | Same-features LightGBM hazard (BF lane) | ~25 trials | distribution-objective declared (hazard classification) |
| 5 | Feature-block ablations (both lanes) | none (remove-and-retrain) | recency block; team-rate block; handedness block; depth block |
| 6 | Hierarchical log5 (partial pooling) | weakly-informative priors, inner-chrono | literature-informed extension, not a generic classifier |
| 7 | Beta-binomial dispersion v2 | only if the dispersion diagnostic fires | replaces independent-Bernoulli approximation |

Compute caps: challenger runs <= ~2h total; no overnight sweeps; all
2023-24 windows remain developmental; transfer/prospective evidence
required before any production claim.
