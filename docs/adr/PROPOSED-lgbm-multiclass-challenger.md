# Bounded-selected LightGBM vs fixed multinomial challenger card

## ID

`lgbm_multiclass_v1`

## Question

Holding the 12-feature input (8 registered + 4 platoon-features-v1
columns), the training rows, the pooled W0 workload, the aggregation, and
the assessment cohort fixed, does a BOUNDED-SELECTED LightGBM multiclass
model (grid-selected on chronological folds inside the training window)
improve the probability forecasts over the FIXED multinomial-plus-platoon
development control?

## Status

DRAFT - implemented and synthetic-tested only; NOT executed on real data.
Real-data execution requires the reviewed packet + explicit owner approval.

## Registered reentry reason

The fixed-config LightGBM rung was RETIRED by the lgbm-equal-info v2
closeout. This is a NEW registered experiment, not a reopening of that
closeout: the owner explicitly assigned an equal-information multiclass
boosted-tree challenger with a small predeclared chronological tuning
budget against the NEW development control (multinomial-plus-platoon),
which did not exist at the time of the v2 closeout. No old result is
re-argued.

## Arms

| Component | Control (multinomial-plus-platoon) | Challenger (boosted tree) | Shared? |
|---|---|---|---|
| Features | 12 columns: `ad.FEAT_H3` (8) + `PLATOON_COLS` (4, platoon-features-v1) | Identical 12 columns - EQUAL INFORMATION, no extras | Yes |
| Estimator | Registered multinomial recipe (StandardScaler + LogisticRegression C=1.0 lbfgs; identical softmax application) | LightGBM multiclass (`LGBMClassifier`, objective `multiclass`, deterministic) | - (the ONLY difference) |
| Training rows | Labeled frame, window `2024-05-01..2024-12-31`, `class_label >= 0` | Identical frame for the FINAL fit | Yes |
| Training loss / weighting | L2-regularized multinomial cross-entropy, equal per-PA weights | LightGBM multiclass softmargin log loss, every training PA EQUALLY weighted (no sample/class weights) | Equal weighting, different objective family |
| Pooled workload | W0 pooled BF37 per cutoff (imported construction) | Same | Yes |
| Aggregation | `ad.start_count_pmfs(p9, p9, bf37)["pmf_h3_raw"]` (24 buckets) | Same | Yes |
| Cohort | Registered 2,509-start block_2025H1 cohort (`f77d7a66...`), REQUIRED at CLI, restricted BEFORE feature construction | Same | Yes |
| Control reconstruction | Gate vs the pinned accepted per-start reference of the platoon run's challenger arm (`platoon_per_start_v1.parquet`, column `rps_platoon`, sha `c7428375...`), tolerance 1e-12, ENFORCED pre-decode | Same gate | Yes |

## Tuning budget (pre-declared, small, chronological)

- Grid: `num_leaves` in {7, 15, 31} x `min_data_in_leaf` in {50, 200} =
  **6 configurations**; fixed `learning_rate = 0.05`, `n_estimators = 200`
  (no early stopping), `objective = multiclass`, `seed = 20261001`,
  `deterministic = true`, `force_row_wise = true`, single-threaded.
- **Chronological validation (2 folds, inside the declared training
  window, NEVER on the registered assessment cohort):**
  - Fold A: fit on rows `2024-05-01..2024-08-31` -> validate on
    `2024-09-01..2024-10-31`.
  - Fold B: fit on rows `2024-05-01..2024-10-31` -> validate on
    `2024-11-01..2024-12-31`.
- Selection: lowest MEAN validation multiclass log loss across the two
  folds; tie -> fewer `num_leaves`; tie -> larger `min_data_in_leaf`; tie
  -> grid order. ALL 6 x 2 = 12 fold results are recorded in the report
  and receipt (no fold cherry-picking, no reselection).
- After selection: ONE final challenger fit on the full declared training
  window with the selected configuration.
- The registered assessment cohort (block_2025H1) is read ONLY for final
  scoring, after the configuration is frozen; it never touches tuning or
  selection. Protected partitions and 2026 are never read.

## Endpoints (pre-declared before scoring)

- **Primary:** per-PA multiclass log loss on the identical matched-PA
  population (probabilities from the keyed table, matchup-key m:1 join).
  **Weighting (declared):** the contrast statistic is the PER-START MEAN
  of per-PA log loss (each start equally weighted, PAs equally weighted
  within a start), paired slate-date bootstrap (2,000 draws, seed
  20261001). The headline mean per-PA values are descriptive summaries.
  Statistical direction: CI entirely below zero favors the challenger;
  entirely above favors the control; overlapping zero is inconclusive.
- **Practical threshold (declared):** a mean log-loss improvement below
  0.0005 nats does not justify the added model complexity, regardless of
  CI direction.
- **K-count non-degradation criterion:** mean per-start count-RPS of the
  challenger must not exceed the control's by more than the declared
  margin of **0.002 count-RPS** (point estimate). This is a POINT-ESTIMATE
  ACCEPTANCE GUARD, deliberately NOT a statistical noninferiority claim.
- **Secondary evidence (declared, not decisive):** classwise log loss and
  Brier per class, mean K-count RPS per arm, K PMFs per start, the full
  tuning-fold table.
- **Promotion:** never automatic. A qualifying result registers a
  candidate model-family change for a FUTURE frozen-contract decision.

## Artifacts (write-once run directory)

Same conventions: `lgbm_comparison_report.json` (incl. the full 12-row
tuning fold table + selected configuration),
`lgbm_per_start_v1.parquet`, `keyed_pa_probabilities.parquet` (both arms'
full class-probability vectors), `model_artifacts.json` (both models;
the LightGBM booster serialized to text, reloadable),
`k_pmf_per_start_v1.parquet`, `bf37_pooled_by_date_v1.parquet`,
`platoon_split_rates_v1.parquet` (reused construction, saved for
verification), `receipt_initial.json` / `receipt_final.json` /
`failure_record.json`.

## Limitations

- Development evidence on the registered 2025H1 cohort; not a fresh final
  test; no production, betting-value, or causal claims.
- Equal-information design: any challenger gain is attributable to the
  model family, not features.
- The tuning budget is deliberately small and chronological; it does not
  establish optimality of the selected configuration.
- The 2-class softmax repair in `m0.apply_multinomial` and the reviewed
  `workload_comparison.py` remain DEFERRED and untouched.
- 2026 untouched; protected partitions and old registrations unchanged.
- Real-data execution requires the reviewed packet + explicit owner
  approval; this card authorizes implementation and synthetic testing
  only.
