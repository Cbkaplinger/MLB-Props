# Platoon-information value card

## ID

`platoon_information_v1`

## Question

Holding the eight registered features, the cutoff-correct feature
constructor, the pooled W0 workload, the aggregation, the training rows, and
the assessment cohort fixed, does adding the declared platoon feature family
(handedness-conditioned historical class rates) improve the multiclass
predictor's probability forecasts?

## Status

DRAFT - implemented and synthetic-tested only; NOT executed on real data.
Real-data execution requires this reviewed packet plus explicit owner
approval. No taxonomy change, tuning sweep, new workload policy, or
production change.

## Source verification (done 2026-11-04, identity + handedness columns only; no outcome reads)

- The registered pa_table ALREADY carries `stand` (batter side) and
  `p_throws` (pitcher hand) on every row - no new input, no raw-Statcast
  dependency, no identity join needed.
- 731,347 rows, 2022-04-07..2025-09-28; ZERO nulls in either field; domains
  exactly {L, R}.
- `p_throws` is perfectly stable per pitcher (1,512 pitchers, zero with >1
  value) -> pitcher hand is pregame-known and row-consistent.
- 1,052 batters; 113 have >1 historical stand (switch hitters); 51
  (batter, p_throws) pairings show mixed stands.
- Source-time semantics: `stand`/`p_throws` are recorded on the historical
  PA rows themselves (strictly-prior rows are legitimate history). For a
  FORECAST row, the batter's stand is NOT pregame-observable for switch
  hitters, so the forecast uses the declared modal-stand rule below; the
  pitcher's `p_throws` IS pregame-known.

## Arms

| Component | Control | Challenger | Shared? |
|---|---|---|---|
| Base features | `ad.FEAT_H3` (8) via `attach_prior_features` on `fv.build_v2_states` cutoff-correct states | Same | Yes |
| Platoon features | none | 4 columns: shrunk (stand, p_throws) -> class-rate estimates (below) | - (the ONLY difference) |
| Estimator | `m0.fit_multinomial` (registered recipe: StandardScaler + LogisticRegression C=1.0 lbfgs max_iter=1000; K marginal via softmax; 2-class parameterization handled by the identical-softmax helper) | Same estimator family and hyperparameters, fit on 12 columns (8 + 4) | Same family |
| Training rows | Labeled frame, window `2024-05-01..2024-12-31`, `class_label >= 0` | Identical frame | Yes |
| Pooled workload | W0 pooled BF37 per cutoff (imported construction from the reviewed workload runner) | Same | Yes |
| Aggregation | `ad.start_count_pmfs(p9, p9, bf37)["pmf_h3_raw"]` (24 buckets) | Same | Yes |
| Cohort | Registered 2,509-start block_2025H1 eligible cohort (`f77d7a66...`), REQUIRED at CLI, restricted BEFORE feature construction | Same | Yes |
| Control reconstruction | Gate vs pinned accepted per-start reference (`ae971758...`, column `rps_w0_pooled`), tolerance 1e-12, ENFORCED pre-decode | Same gate | Yes |

## The declared platoon feature family (exact)

Four feature columns, one per outcome class c of the registered 4-class
taxonomy (`m0.CLASS_NAMES`):

    p_platoon_c = (count_hist(c, split) + alpha * q_global_c(cutoff))
                  / (n_hist(split) + alpha)

where:

- **Split** = (batter `stand`, pitcher `p_throws`) of the historical row -
  four cells: (L,L), (L,R), (R,L), (R,R).
- **Pooling population** = ALL rows in the decoded PA table with
  `game_date` STRICTLY BEFORE the row's cutoff date (same full y-based
  history convention as states-v2; same-date and future rows cannot enter
  by construction; the row's own outcome is never in its own feature).
- **`count_hist(c, split)`, `n_hist(split)`** = counts over that strictly-
  prior population, class labels from the registered terminal-event bridge
  (rows with `class_label < 0` are excluded from both numerator and
  denominator).
- **`q_global_c(cutoff)`** = the global strictly-prior class proportions
  (same population, all splits pooled) - the shrinkage target.
- **Shrinkage:** `alpha = 40` effective pseudo-observations (10 per class),
  a declared engineering constant, not tuned. A split with n_hist = 60
  carries 60/(60+40) = 60% empirical weight; n_hist = 600 carries ~94%.
- **Unseen-split behavior:** n_hist = 0 -> the feature equals
  `q_global_c(cutoff)` exactly (full shrinkage to the global prior). An
  unknown/missing stand or p_throws on a forecast row -> the same global
  fallback.
- **Forecast-row stand (switch hitters):** the batter's stand is NOT
  pregame-observable, so the forecast uses the modal strictly-prior stand
  CONDITIONAL on the opposing pitcher's hand; the pitcher's hand is their
  MODAL STRICTLY-PRIOR `p_throws` AT THE CUTOFF (verified stable per
  pitcher over the full table; a pitcher with no rows strictly before the
  cutoff has NO known hand -> unknown -> global fallback). Ties resolve to
  the lexicographically smallest stand. No conditional history -> the
  batter's modal strictly-prior stand overall; no batter history ->
  unknown -> global fallback. Historical rows use their own recorded
  `stand` (they are history, not forecasts).
- **Computed per distinct cutoff** (training-row dates and request cutoff
  dates), reusing the states-v2 cutoff convention; the per-cutoff tables are
  the only added computation.

Leakage statement: the features are handedness-conditioned HISTORICAL class
rates computed exclusively from strictly-prior rows; no target-row outcome,
no same-date row, no future row contributes to any feature.

## Endpoints (pre-declared before scoring)

- **Primary:** multiclass log loss on the identical matched-PA population
  (probabilities from the keyed table, matchup-key m:1 join).
  **Weighting (declared):** the contrast statistic is the PER-START MEAN of
  per-PA log loss - each start equally weighted, PAs equally weighted
  within a start - contrasted with the registered paired slate-date
  bootstrap (2,000 draws, seed 20261001). The headline mean per-PA log-
  loss values are descriptive summaries of the same matched population.
  Statistical direction: CI entirely below zero favors the platoon
  challenger; entirely above favors the control; overlapping zero is
  inconclusive.
- **Practical threshold (declared):** a mean log-loss improvement below
  0.0005 nats does not justify the added feature family, regardless of CI
  direction.
- **K-count non-degradation criterion:** mean per-start count-RPS of the
  challenger must not exceed the control's by more than the declared margin
  of **0.002 count-RPS** (point estimate). A challenger that improves (or
  is neutral within) this margin AND achieves a practically meaningful
  primary improvement registers a candidate feature-family addition for a
  FUTURE frozen contract decision; promotion is never automatic.
- **Secondary evidence (declared, not decisive):** classwise log loss and
  Brier per class, mean K-count RPS per arm, K PMFs per start, per-split
  cell counts.

## Artifacts (write-once run directory)

Same conventions as the accepted runners: `platoon_comparison_report.json`,
`platoon_per_start_v1.parquet`, `keyed_pa_probabilities.parquet` (both
arms' full class-probability vectors), `model_artifacts.json` (both fitted
models, reloadable), `k_pmf_per_start_v1.parquet` (both arms),
`bf37_pooled_by_date_v1.parquet`, per-cutoff split-rate table
(`platoon_split_rates_v1.parquet`), `receipt_initial.json` /
`receipt_final.json` / `failure_record.json`.

## Limitations

- Development evidence on the registered 2025H1 cohort; not a fresh final
  test; no production, betting-value, or causal claims.
- The platoon family captures only the (stand, p_throws) split; no
  pitcher-specific or batter-specific handedness interactions beyond it.
- The 2-class softmax repair in `m0.apply_multinomial` and the reviewed
  `workload_comparison.py` remain DEFERRED and untouched.
- 2026 untouched (no-2026-tuning rule); protected partitions and old
  registrations unchanged.
- Real-data execution requires the reviewed packet + explicit owner
  approval; this card authorizes implementation and synthetic testing only.
