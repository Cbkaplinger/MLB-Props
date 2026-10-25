# PRE-REGISTRATION CARD — count-PMF calibration vs identity
# (pregame-pa-ext-v2 lane, 2026-10-24; DRAFT, not executed)

## 1. Question

Can one fixed calibration method improve the frozen K-count
distribution on later development periods, without changing the PA
model, workload forecast, or feature set?

## 2. Target layer: count-PMF (not PA)

The calibrator operates on the FINAL count distribution per start
(the 24-bucket PMF), not on per-PA probabilities. PA-level calibration
followed by re-aggregation is a DIFFERENT experiment and is not part
of this card.

## 3. Method: linear CDF recalibration (one method, not three)

The model's count CDF F(k) = P(K ≤ k) is mapped to a calibrated CDF:

    F_cal(k) = clip(a * F(k) + b, 0, 1)

where (a, b) are fit to minimize mean count-RPS on the calibration
window, subject to F_cal(23) = 1 (monotone, nonnegative, normalized).
Two parameters. No method selection — identity (a=1, b=0) is the
null comparator.

## 4. Inputs and keys (pinned)

- Model PMFs: `count_agg_eval_v1.parquet` pmf_baseline
  (4,823 dev starts; 82,817 PA keys implicitly via the aggregation).
- Realized K: `start_metrics_v2.parquet` (registered
  `af6814ec…`).
- BF PMFs: `bf_forecasts.parquet` (registered `c9c2762f…`).
- Cohort key hash: the ablation_count_rps canonical v2 keys
  (4,823 dev starts, ledger-projected nine slots).
- The 82,817 PA keys are NOT consumed (calibration operates at the
  count-PMF layer only).

## 5. Calibration forecast provenance

The PMFs in `count_agg_eval_v1.parquet` were produced by the frozen
recipe's walk-forward fits: the block_2024H2 model was trained on
2023-01-01..2024-05-01 (cal 2024-05-02..2024-06-30) and scored on
2024-07-01..2024-12-31; the block_2025H1 model was trained on
2023-01-01..2024-08-01 (cal 2024-08-02..2024-09-30) and scored on
2025-01-01..2025-06-30. Each start's PMF is therefore an
OUT-OF-SAMPLE forecast (the base model never saw its outcomes).
Calibration examples are out-of-sample predictions by construction.

## 6. Chronological separation

- Fit (a, b) on block_2024H2 scored starts (n=2,314).
- Score the fitted (a, b) on block_2025H1 scored starts (n=2,509),
  which are DISJOINT and LATER.
- The block_2025H1 outcomes are never used during fitting.
- Walk-forward check: refit (a, b) on 2024H2+2025H1 combined and
  compare against the block_2024H2-fitted values for stability.

## 7. PMF invariants (enforced at every step)

- Finite, nonnegative probabilities.
- Sum to exactly 1.0 (tolerance 1e-9).
- Support: k = 0..22 exact, tail absorbed at k=23 (registered
  convention).
- Monotone CDF: F(k) is nondecreasing in k.
- No change to the 24-bucket convention or the cap-60/tail-at-23
  registered interpretation.

## 8. Primary metric

Paired count-RPS difference: Δ = RPS_calibrated − RPS_frozen, on the
identical block_2025H1 scored starts, with the registered slate-date
bootstrap (n=2000, seed 20261001, Holm m=1).

## 9. Acceptance rule

- ACCEPT if the upper paired 95% CI bound < 0 (the calibrated PMF is
  genuinely better on later development data).
- CLOSE if the CI includes zero or favors the frozen PMF.
- No practical-effect margin is declared (the direction test is
  sufficient for this first calibration experiment).

## 10. Secondary reporting

- Calibration reliability: observed vs predicted K in decile buckets.
- MAE/RMSE of the point summary (mean of the PMF) vs actual K.
- Own-line LL/Brier (the market-line comparison, reported but never
  used for selection).
- The fitted (a, b) values and their block_2025H1 walk-forward
  stability.

## 11. Stop conditions

- If the calibration data has fewer than 1,000 starts -> STOP
  (insufficient calibration sample).
- If the fitted `a` is outside [0.5, 2.0] -> STOP (unstable).
- If any PMF invariant is violated -> STOP.
- If walk-forward (a, b) differ by more than 0.5 in either parameter
  -> STOP (non-stationary).

## 12. Execution contract

Real-data execution requires the registered gate
(--i-accept-outcome-evaluation or the equivalent) AND explicit owner
authorization. Write-once outputs; receipts initial-first; failure
records preserved. No 2025H2 confirmation fitting; no 2026 access.

## 13. Synthetic tests required

- Identity mapping recovers the input PMF exactly.
- (a, b) recovery on synthetic ground truth.
- PMF invariants after calibration (normalization, nonnegativity,
  monotone CDF).
- Chronological separation (calibration data from block_2024H2 does
  not leak into block_2025H1 evaluation).
- Stop-condition triggers.
