# FROZEN prereg - K-count integration (frozen 2026-10-08)

> **Status: FROZEN 2026-10-08** (owner-authorized ONE scored diagnostic run).
> Authored from the 2026-10-07 draft + pre-freeze owner round 2; all 12
> conventions frozen before scoring. Origin: owner order 2026-10-07 and
> authorization 2026-10-08.
> **Pre-scoring clarification (2026-10-08, before any scoring):** the
> K-count support wording below originally read "support 0..24 with an
> absorbing >=24 bucket"; the frozen combiner
> (`kcount_combiner.combine_count`, committed + tested BEFORE this
> prereg) implements 24 categories = exact K=0..22 plus ONE absorbing
> bucket "K>=23". The implementation is the frozen contract; wording
> corrected here, no convention changed.

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
  documented). K-count support (clarified): 24 categories = exact K=0..22 plus ONE absorbing bucket K>=23.
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

## Finalized conventions (amended 2026-10-07, owner round — all resolved)

1. **C1 point exposure (frozen):** n_C1 = max(1, round-half-up(E[N]))
   where E[N] is computed from the EXTENDED BF PMF (overflow
   redistributed over 37..60 first, so tail mass raises the mean) of the
   SAME arm-B BF distribution the I-arm uses. Ties round up
   (deterministic floor(e+0.5)). No optimization against eval outcomes.
2. **Overflow tail (frozen):** mass P(N>=37) redistributed over 37..60
   proportional to a geometric tail with per-step ratio (1 - h_36)
   (bf_pmf_from_37: mean implied hazard of indices 31..36). The 36->37
   junction may step UP when overflow is large —    documented artifact of
   a bounded cap, not a model claim. **Beyond BF=60: zero model
   support by construction** (mass fully conserved within 1..60) — a
   SUPPORT/TRUNCATION ASSUMPTION of the model, not a claim that BF>60
   is impossible in reality (see convention 6). Prespecified
   sensitivity diagnostic (never a tuning knob): recompute E[N] with
   cap=120 and report the delta; if |delta| > 0.1 BF on any origin, the
   sensitivity is flagged in the report.
3. **Comparator parity (frozen):** C1 is computed PER ARM — C1(L1) uses
   exactly I1's p_bar (league-average), C1(L2) uses exactly I2's p_bar
   (team aggregate). Each I-vs-C1 pair therefore isolates exposure-
   distribution value at fixed p_bar. Primary gate uses the L1 pair
   (I1 − C1(L1)); the L2 pair is a prespecified secondary.
4. **Opposing-team aggregate (frozen):** population = ALL first-pitcher
   PAs in the prior pool (2022 full season + 2023 rows strictly before
   the origin cutoff); batting team = the team whose batters faced each
   pitcher (spine keys: home_team/away_team + is_home); denominator =
   that team's prior PAs; shrinkage w = 150 (same as log5, frozen);
   league fallback when prior n = 0. Strict cutoff: game_date < origin.
5. **Provenance guard (frozen):** the scored K-count runner must embed
   REAL 64-char sha256 provenance for every dependency (prereg, code,
   saved PMF artifacts, inputs). `validate_provenance` REJECTS the CI
   "external-preserved (not available)" marker and any non-sha entry —
   portable-CI tolerance never downgrades scientific provenance
   requirements. Tested.

## Frozen scoring conventions (pre-freeze owner round 2, 2026-10-08)

6. **BF>60 is a model-support assumption, NOT a factual impossibility.**
   The model's count support truncates at BF=60 (24 categories: exact K=0..22 plus ONE absorbing bucket K>=23). Real BF>60 is possible in principle; the
   model assigns it zero probability by construction. Stated as a
   support/truncation assumption wherever reported.
7. **Count log-score floor (frozen):** an observed K bucket with zero
   predicted probability is scored at -log(1e-12) (numerical floor);
   the raw zero is NEVER silently converted to a finite score without
   accounting — the runner reports, per arm, the number of rows where
   the predicted bucket probability was below the floor (would be
   infinite without it). The floor is fixed BEFORE scoring and is not
   tuned.
8. **Cap-120 sensitivity (prespecified, matched):** recompute with
   cap=120: (a) E[N] per origin; (b) the point-exposure comparator
   n_C1 = max(1, round-half-up(E[N_120])) — the comparator is
   recomputed under the SAME cap so the sensitivity is apples-to-
   apples; (c) all I/C count PMFs and their pooled count-RPS /
   log-score / ladder P(K>=6/8/10/12) means. Report deltas. If
   |delta E[N]| > 0.1 BF on any origin the sensitivity is FLAGGED in
   the report. The cap is never selected from these scores.
9. **Declared point functional (frozen):** the mean of the count
   distribution is computed ANALYTICALLY: I arms E[K] = p_bar *
   E[N_ext]; C arms E[K] = n * p_bar. (The count-PMF mean with the
   >=23 bucket valued at 23 differs only by the tail-bucket
   valuation; the analytic form avoids that artifact.) MAE of this
   functional is the reported point-error metric; it is aligned with
   squared error, NOT claimed as the optimal point forecast under
   absolute loss.
10. **Reliability bands (frozen):** per milestone m in
    {6,7,8,9,10,12}, predicted P(K>=m) bucketed into
    [0,.05), [.05,.10), [.10,.20), [.20,.30), [.30,1.0]; per band:
    n, mean predicted, observed frequency. Dispersion diagnostic
    bands on p_bar: [0,.18), [.18,.21), [.21,.24), [.24,.28),
    [.28,1.0]; per band: n, observed variance of K, mean point-
    exposure binomial variance n_C1 * p_bar * (1 - p_bar), ratio.
    Diagnostic only — never tuned.
11. **C2 realized-lineup p_bar (frozen, non-deployable):** per eval
    pitcher-game, the PA-weighted mean of per-batter log5
    probabilities (pitcher shrunk rate x each ACTUAL batter's shrunk
    rate, w=150, same prior pool) over the realized batters faced.
    Uses realized lineup identity — labeled non-deployable oracle
    diagnostic; realized per-PA OUTCOMES are never used in any arm's
    p_bar.
12. **Saved-artifact alignment (frozen):** the runner consumes the
    frozen training-policy artifact PAIR positionally and PROVES the
    alignment from the artifacts alone before use: for every row,
    bf.rps_score(saved_pmfB_row, PA) must reproduce the saved rps_B
    and saved_pmfB[:, :8].sum() must reproduce saved q_B (tol 1e-8).
    Any mismatch blocks the run. No refit of the BF lane.

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
