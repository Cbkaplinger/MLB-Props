# BF Workload Distribution — Frozen Design (no scoring in this task)

Status: FROZEN DESIGN BEFORE ANY SCORED DIAGNOSTIC. One
probabilistic workload challenger on corrected-history inputs.
No real-data distribution fitting or scoring until a separate
one-run authorization.

## 1. Target (exact contract)

Total realized BF for the retained first-pitcher diagnostic
population (BF>=1, canonical keys, both team sides).

- Observed completed workload (including completed short
  outings): the modeled outcome. A completed short outing is an
  observed BF value, NOT censored merely because the pitcher could
  have continued.
- Incomplete/corrupt observation: truncated PAs, failed joins,
  quarantined games — excluded with counts, never imputed, never
  silently merged into the modeled population.
- Retrospective eligibility: actual first-pitcher identity, labels
  UNVERIFIED, eligible=False. Diagnostic, not pregame availability.
- Hypothetical removal mechanism (hook/injury/opener intent): NOT
  modeled and NOT identified. The model predicts termination
  probabilities, never the reason an outing ended.

## 2. Model: discrete termination hazard (one candidate)

Grid: BF index n = 1..36 with overflow bucket 37+ (support rule
from the committed D0-D5 spec: N_max = 36 + overflow, tail mass
reported, never silently truncated).

Parameterization (frozen): L2-regularized logistic hazard,
C = 1.0, on [BF-index one-hot dummies (36 levels) + the 10 frozen
corrected-history features]. Shared slopes, per-index intercepts.
Fitted on training-partition risk sets only (see below).

Risk set at index j: training starts with realized BF >= j-1
(completed games fully observed; no censoring within completed
games). Likelihood: Bernoulli(y_j = 1{N == j}) over
start-by-index rows, j = 1..min(N, 36); starts with N > 36
contribute y_j = 0 for j <= 36 plus overflow mass.

Conversion: P(N=n) = h_n * prod_{j<n}(1 - h_j) for n <= 36;
P(N>=37) = prod_{j<=36}(1 - h_j). Assert per-start mass sums to
1 within 1e-9. Within-overflow allocation (if ever needed for a
downstream K calculation) requires a separately frozen assumption,
declared at that time — not here.

Preprocessing (training-only): median imputation + standard
scaling fitted on training risk-set rows, applied unchanged to
evaluation. Cold start: null histories imputed from training
medians; all-null-history rows fall back toward the population
hazard through the same pipeline (no special-case path).

Overflow aggregation disclosure: any metric or downstream K
calculation conditioned on N >= 37 must state its within-overflow
assumption explicitly.

## 3. Comparators (specified before fitting)

- Train-only probabilistic baseline: empirical BF distribution
  over 1..36 + overflow from the training partition, add-one
  (Laplace) smoothed over the 37 categories so log scores stay
  finite. Specified here, fitted at execution, never tuned.
- Preserved Ridge point forecasts: point-performance references
  only (MAE comparison against distribution means is descriptive;
  a point forecast alone is not a distribution baseline).

## 4. Evaluation (frozen; 2023 origins incl. April extension)

- Primary: RPS (discrete CRPS over 0..maxK grid per count_metrics).
- Secondary: count NLL (clip 1e-12 with counter).
- Short-outing event: Brier score on P(BF < 9) vs realized indicator.
- Intervals: central 50/80% coverage AND mean width.
- Pooled + per-origin + mandatory slices (BF strata, month,
  experience, missing-history, fallback, per-origin coverage).
- Paired date-clustered uncertainty on score differences
  (same frozen bootstrap: 2000 resamples, seed 20261001).
- Existing decision rules recovered: kill-rule structure and
  tail-flag discipline carry over with distribution-appropriate
  thresholds left as EXPLICIT owner fields (no invented promotion
  rule is claimed approved).

No feature search, no architecture race, no post-score
calibration. Post-hoc Platt/temperature layers are NOT part of
this diagnostic.

## 5. Support and overflow accounting

All outputs carry per-start category masses on 1..36 + overflow
mass. Mass-sum and nonnegativity asserted on every output batch.
BF = 1 rows are first-class outcomes (hazard grid starts at 1;
no special-casing). Missing/corrupt observations error loudly,
never become benign missingness.

## 6. Provenance and stop conditions

Manifest records code/dependency/plan hashes, input identities,
seeds, and per-check statuses. Stop on hash/period/population/
duplicate/nonfinite/incomplete-manifest violations, or any
2024+ access in this design task. Single-run policy applies at
execution.
