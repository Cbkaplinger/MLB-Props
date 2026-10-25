# PRE-REGISTRATION CARD — count-PMF calibration vs identity
# (pregame-pa-ext-v2 lane, 2026-10-24; REVISED per owner review; DRAFT, not executed)

## 1. Question

Can one fixed calibration method improve the frozen K-count
distribution on the later development block (2025H1), without changing
the PA model, workload forecast, or feature set?

## 2. Target layer: count-PMF (not PA)

The calibrator operates on the FINAL count distribution per start
(the 24-bucket PMF), not on per-PA probabilities. PA-level calibration
followed by re-aggregation is a DIFFERENT experiment and is not part
of this card.

## 3. Method: one-parameter linear CDF recalibration

### Mathematical definition

The model's count CDF is F(k) = sum_{j=0..k} p(j), with F(-1) = 0 and
F(23) = 1. The calibrated CDF is:

    F_cal(k) = 1 - a * (1 - F(k)),   for k = 0, 1, ..., 23

where a is the single calibration parameter. This is equivalent to
F_cal(k) = clip(a * F(k) + 1 - a, 0, 1) for a ≥ 0 (the clip is
inactive for k = 23 since F(23) = 1 gives F_cal(23) = 1 exactly).

### Parameter domain

a ∈ [0.5, 2.0]. Values outside this range trigger the stop condition.
a = 1 is the identity (no calibration). a > 1 stretches the CDF
(moves mass away from the mode); a < 1 compresses it (moves mass
toward the mode).

### Boundary behavior

- F_cal(-1) = 0 by definition (no outcomes below K = 0).
- F_cal(23) = 1 is AUTOMATICALLY enforced: F(23) = 1 in the input PMF,
  so F_cal(23) = 1 - a * (1 - 1) = 1 regardless of a.
- Monotonicity: F_cal(k) is nondecreasing in k because
  1 - a * (1 - F(k)) is nondecreasing when F(k) is nondecreasing
  and a ≥ 0.

### PMF reconstruction

    p_cal(k) = F_cal(k) - F_cal(k - 1),   for k = 0, 1, ..., 23
    p_cal(0) = F_cal(0) - F_cal(-1) = F_cal(0)

This guarantees nonnegativity (because F_cal is nondecreasing) and
normalization (because F_cal(23) = 1 and F_cal(-1) = 0).

### Zero-K bucket

When a > 1 and F(0) > 0: F_cal(0) = 1 - a * (1 - F(0)) < F(0) if
a > 1 / (1 - F(0)), so the zero-K probability can be REDUCED (mass
transferred to K ≥ 1). When a < 1: F_cal(0) = 1 - a * (1 - F(0)) >
F(0), so the zero-K probability is INCREASED. This is a real effect —
the card does not prevent it, but the secondary diagnostics will
report whether the zero-K bucket is distorted.

### Tail

The tail bucket (k ≥ 23) is handled identically: F(23) = 1 in the
input PMF, so F_cal(23) = 1, and the tail probability is
F_cal(23) - F_cal(22), which can be zero (if F_cal(22) = 1) or
positive. The registered tail interpretation is unchanged.

## 4. Fitting algorithm

- Objective: minimize mean count-RPS on the calibration window
  (block_2024H2 scored starts, n=2,314).
- Parameter: a (scalar).
- Optimizer: bounded scalar minimization
  (scipy.optimize.minimize_scalar, method='bounded',
  bounds=[0.5, 2.0], xatol=1e-6).
- Initialization: the bounded search does not require an initial
  point; it evaluates the full range.
- Convergence: scipy's default xatol=1e-6 (the fitted a is determined
  to 6 decimal places).
- Non-unique solutions: if two values of a produce count-RPS within
  1e-10, the one closer to 1 (identity) is selected. The fitted value
  and the objective value are both recorded.
- The fitted a is FROZEN before any block_2025H1 outcome is accessed.

## 5. Inputs and keys (pinned, separate fit/evaluation hashes)

### Calibration input (fitting)

- PMFs: count_agg_eval_v1.parquet pmf_baseline, filtered to
  block_2024H2 scored starts (n=2,314).
- Realized K: start_metrics_v2.parquet for the same starts.
- Calibration cohort key hash: computed and recorded.

### Evaluation input (scoring)

- PMFs: count_agg_eval_v1.parquet pmf_baseline, filtered to
  block_2025H1 scored starts (n=2,509).
- Realized K: start_metrics_v2.parquet for the same starts.
- Evaluation cohort key hash: computed and recorded.

### Frozen PMF lineage

The consumed PMFs (pmf_baseline in count_agg_eval_v1) were produced by
the frozen recipe's serialized checkpoint (pin `176fb18b…`), which was
built from build_checkpoint.build_feature_frame on the realized-PA
lineage. The checkpoint's training window is the registered
build_feature_frame construction (2023-01-01..block cal_first per
block), NOT the ablation convention. The exact lineage is documented
in the M0 v2 execution receipt.

### NOT consumed

- PA-level keys (82,817): not consumed by this experiment.
- BF PMFs (bf37): not consumed (the count PMF is already aggregated).
- Projected lineup features: not consumed.
- confirm_2025H2 outcomes: not consumed.

## 6. Evaluation protocol

- Fit: compute (a) on block_2024H2 scored starts by minimizing
  count-RPS. FREEZE (a) before accessing any block_2025H1 outcome.
- Evaluate: apply F_cal to each block_2025H1 start's PMF and compute
  count-RPS. ONE evaluation pass. No refit, no parameter movement
  check, no walk-forward stability test.
- The 2025H1 outcomes are accessed EXACTLY ONCE, for the final
  evaluation. They are not used for fitting, parameter selection, or
  convergence checking.

## 7. Primary metric

Paired count-RPS difference: Δ = RPS_calibrated − RPS_frozen, on the
identical block_2025H1 scored starts, with the registered slate-date
bootstrap (n=2000, seed 20261001, Holm m=1).

## 8. Acceptance rule

- ACCEPT if the upper paired 95% CI bound < 0 (the calibrated PMF is
  genuinely better on block_2025H1).
- CLOSE if the CI includes zero or favors the frozen PMF.
- PASS means improvement on this later development block. It does NOT
  mean practical betting value or confirmation performance. Both
  blocks have already informed project development; they are not an
  untouched holdout.

## 9. Secondary reporting

- Calibration reliability: predicted threshold probabilities vs
  observed threshold frequencies, at each of the model's own quoted
  lines (own-line LL/Brier).
- Count-PMF calibration: predicted CDF vs empirical CDF at each
  bucket k = 0..23 (the full PMF, not just the mean).
- MAE/RMSE of the point summary (mean of the PMF) vs actual K.
- The fitted a value.
- No selecting the method by sportsbook gap.

## 10. Stop conditions

- Calibration sample < 1,000 starts -> STOP.
- Fitted a outside [0.5, 2.0] -> STOP.
- Any PMF invariant violated after calibration -> STOP.
- The evaluation outcomes are accessed before the fitted a is frozen
  -> protocol violation, STOP.

## 11. Execution contract

Real-data execution requires the registered gate
(--i-accept-outcome-evaluation or the equivalent) AND explicit owner
authorization. Write-once outputs; receipts initial-first; failure
records preserved. No 2025H2 confirmation fitting; no 2026 access.

## 12. Synthetic tests required

1. Identity: a=1 reproduces the input PMF exactly.
2. Boundaries: a=0.5 and a=2.0 produce valid PMFs.
3. Extreme PMFs: all mass at k=0; all mass at k=23.
4. Tail mass: a PMF with heavy tail (mass concentrated at k≥20).
5. Monotonicity: F_cal is nondecreasing for all tested a.
6. Normalization: p_cal sums to 1 within 1e-9 for all tested a.
7. Deterministic fitting: the same calibration input always produces
   the same fitted a.
8. Evaluation-outcome isolation: the fitted a is computed BEFORE any
   evaluation-set outcome is accessed (verified by construction).
