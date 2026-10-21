# PRE-REGISTRATION CARD (DESIGN ONLY) — Question B: workload–performance
# dependence in the count layer (pregame-pa-ext-v2 lane, 2026-10-20)

STATUS: PROPOSED DESIGN — NOT IMPLEMENTED, NOT EXECUTED, NO REAL OUTCOMES.
This card covers DESIGN ONLY per the owner's instruction (R3): for each
candidate workload–performance coupling it states the model structure, what
changes versus the frozen baseline, the primary metric, the paired
population, the stop condition, and the synthetic tests required.
Implementation requires Chat 2 review of this card plus explicit owner
authorization, and is sequenced AFTER the Question A report (R2).

## 0. Question B definition (from note_count_aggregation_future_2026-10-20.md)

The registered count layer generates
P(K=k) = sum_n P(N=n) * Binom(k; n, pbar_n), where pbar_n is the cycled
prefix mean of the nine slot probabilities. Separation tests
(test_count_aggregation_separation.py) pinned its actual assumptions:
homogenization within n (tail masses overstated for heterogeneous lineups),
order-awareness through the cycling, linearity in the BF workload measure,
no within-n outcome correlation, and no endogenous workload-performance
coupling (pbar_n is CONSTRAINED to prefix means of the slot probabilities —
a performance-exposure decline is structurally unrepresentable). Question B
asks whether relaxing that structural constraint improves the count
distributions.

## 1. Frozen baseline (unchanged comparison anchor)

The frozen count PMF for every eligible start: both registered arms
(H3-raw cycled-prefix-mean + LOG5 corrected) mixed over the registered BF
workload (bf_pmf_from_37, cap 60, tail absorbed at k=23), on the 4,823
eligible development starts of the preserved run ledger. Nothing about the
baseline changes in any Question B candidate.

## 2. Candidates (sequential; ONE implemented at a time; never simultaneous)

### C-B1 — Exposure-profile heterogeneity (FIRST/PRIMARY candidate)

- **Model structure:** per-BF-INDEX K probability profile q_j (j = batters-
  faced index 1..60), piecewise-constant on registered bands
  (j 1-9, 10-18, 19-27, 28-36, 37+). Each band's rate is estimated from the
  FROZEN realized-PA training lineage (same rows as the frozen recipe:
  2023-01-01..block cal_first, per dev block) with band-level shrinkage
  toward the frozen cycled prefix mean (w150 convention applied to band PA
  counts; the exact shrinkage formula is pre-registered before
  implementation). Count structure: P(K=k) = sum_n P(N=n) * PB(k; q_1..q_n)
  — the EXACT heterogeneous per-PA sequence.
- **Computational vehicle:** the Question A exact Poisson-Binomial
  aggregator (count_aggregation_exact.py), reused as machinery. DEPENDENCY:
  C-B1 requires the Question A aggregator to be merged.
- **What changes vs the frozen baseline:** ONLY the per-PA probability
  sequence generator (frozen: cycled prefix means; C-B1: estimated exposure
  profile). N (BF workload) unchanged; lineup construction unchanged; PA
  probability arms unchanged; eligibility unchanged.
- **Primary metric:** count-RPS (registered vocabulary) on the identical
  eligible dev population; paired slate-date bootstrap via the REGISTERED
  harness primitives (n=2000, seed 20261001, null-centered, Holm m=1).
- **Paired population:** the 4,823 eligible development starts with their
  realized K counts from frozen sources; identical keys both arms; the 43
  dev abstentions excluded (unchanged); confirmation untouched.
- **Stop conditions:** (a) ESTIMATION STOP: if every band's estimated rate
  is within a pre-declared material band of the frozen profile
  (|q_band - pbar_band| < 0.005 on all bands), stop and declare no
  exposure signal WITHOUT evaluation; (b) EVALUATION STOP: count-RPS delta
  CI including zero or favoring the baseline -> close the candidate;
  (c) any integrity/receipt failure -> stop.
- **Synthetic tests required:** band-profile recoverability (synthetic
  ground-truth profile estimated back within tolerance); shrinkage-to-
  frozen behavior at sparse bands; PMF normalization + tail-bucket
  correctness; strictly-prior construction (no same-day/future rows);
  block isolation (confirm untouched); unchanged eligibility; receipt
  completeness (mandatory provenance; MLflow transport optional).

### C-B2 — Exit-hazard coupling (SECOND candidate; heavier)

- **Model structure:** N becomes an OUTCOME of the same generative
  process: a per-BF continuation hazard h_j (j = BF index; registered
  monotone or banded form) with pitcher exit as a competing event; the K
  sequence and the exit event are generated jointly per start. The count
  PMF marginalizes the joint P(N=n, K=k).
- **What changes vs the frozen baseline:** the GENERATIVE STRUCTURE — N is
  no longer an exogenous input. The BF PMF becomes a VALIDATION target
  (the generated N distribution must calibrate against the registered BF
  workload — a new first-class check), not an input.
- **Primary metric:** count-RPS on the same paired population.
- **Supporting (not gated):** BF-distribution calibration of the generated
  N (reliability against the frozen BF PMF).
- **Paired population / stop conditions:** identical population rules;
  (a) hazard estimation shows no material departure from the empirical
  BF-derived hazard -> stop; (b) count-RPS delta CI including zero ->
  close; (c) generated-N calibration materially degrades -> close.
- **Synthetic tests required:** hazard identifiability on synthetic ground
  truth; joint (N, K) PMF normalization + tail-bucket correctness;
  generated-N calibration check behavior; strictly-prior; receipt.

### C-B3 — Within-game outcome feedback (DEPRIORITIZED; design note only)

Previous-PA outcomes alter subsequent q_j. LARGEST structural change;
weakest prior (C-B1's exposure profile captures much of the same signal);
NOT scheduled this cycle. Recorded so the candidate space is complete.

## 3. Discipline

- ONE candidate implemented at a time, each with ONE pre-declared contrast
  and Holm m=1 (family of one per card). Candidate selection on
  development data across candidates is FORBIDDEN without a new
  registration; sequential cards only.
- Question A (exact PB aggregator) is a PREREQUISITE for C-B1
  (computational machinery) and must be merged and reviewed first.
- The frozen harness is imported and called, never modified.

## 4. Boundaries

- This card is DESIGN ONLY: no code, no real outcomes, no production
  change. Implementation requires Chat 2 review of this card + explicit
  owner authorization. Confirmation untouched. The original prediction
  run remains UNACCEPTED. No historical extension, no coverage-policy
  change.
