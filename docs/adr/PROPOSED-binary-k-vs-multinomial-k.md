# Binary-K vs multinomial-K comparison card

## ID

`binary_k_vs_multinomial_v1`

## Question

Holding the pooled league BF workload (W0), lineup reconstruction, count
aggregation, training rows, features, and assessment population fixed, does a
binary K-vs-non-K logistic produce better final K-count distributions than the
existing multinomial model's K marginal?

## Status

DRAFT - implemented and synthetic-tested only; NOT executed on real data.
One authorized run requires the reviewed packet plus explicit owner
authorization. Single-change discipline: the ONLY difference between arms is
the source of the per-PA K probability. No taxonomy reopening, no calibration,
no feature change, no workload change.

## Control (exact)

The existing multinomial-plus-W0 control: the m0 multinomial logistic
(`m0.fit_multinomial`, registered recipe - StandardScaler + LogisticRegression
C=1.0 lbfgs max_iter=1000, class order `m0.CLASS_NAMES`) fit on the declared
training rows; per-PA K probability = class-0 (strikeout) marginal of the
softmax; count aggregation `ad.start_count_pmfs(p9, p9, pooled_bf37)`
(`pmf_h3_raw`), pooled BF37 exactly as the accepted W0 arm of
`workload_personalization_w0v1`. A reconstruction gate MUST reproduce the
pinned per-start count-RPS of that accepted arm within 1e-12 before any
contrast is reported.

## Arms

| Component | Control (multinomial-K) | Challenger (binary-K) | Shared? |
|---|---|---|---|
| Estimator | Multinomial logistic (m0 registered recipe) | Binary logistic, same estimator family (StandardScaler + LogisticRegression C=1.0 lbfgs max_iter=1000, sigmoid head) | Same family, same hyperparameters |
| Label | 4-class `class_label` (unchanged) | `is_k = 1[class_label == K_CLASS]` derived from the SAME class_label column - no second label source | Same rows |
| Training rows | Declared labeled training frame | Identical frame; per-arm row counts asserted equal | Yes |
| Features | `ad.FEAT_H3` (8) via `attach_prior_features` on `fv.build_v2_states` cutoff-correct states | Same frames consumed by both fits (one construction, two fits) | Yes |
| Per-PA K probability | Softmax K marginal | Sigmoid P(K) | - (the ONLY difference) |
| Pooled workload (BF37) | W0 pooled empirical BF37 per forecast cutoff (first-pitcher-of-record outings, opener-inclusive, `2023-01-01 <= game_date < cutoff`, add-one smoothing, registered tail) - imported from the reviewed workload runner for construction identity | Same object | Yes |
| Count aggregation | `ad.start_count_pmfs(p9, p9, bf37)["pmf_h3_raw"]` (24 buckets) | Same function, same BF37, same p9 layout | Yes |
| Assessment cohort | Registered 2,509-start block_2025H1 eligible cohort (hash `f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7`), REQUIRED at CLI with hash pin, restricted BEFORE feature construction | Same | Yes |

## Binary-label derivation

`is_k` is derived ONLY from the bridged `class_label` column
(`(class_label == K_CLASS).cast(Int64)`), which itself comes from the
registered raw-Statcast terminal-event bridge. Guards: training must contain
both classes (single-class refuses); binary and multinomial training row
counts asserted equal; binary positive/negative counts recorded in receipts.
The assessment side derives the SAME `is_k` for realized-K counts, identical
to the reviewed runners.

## Keyed probability alignment

One keyed PA probability table is built directly from the shared feature rows
(`game_pk, side, pitcher, slot, batter, p_k_multinomial, p_k_binary`) - no
positional transfer across frames. A row-permutation invariance test proves
per-key probabilities survive a reversed feature frame. Per-PA descriptive
metrics join actual PAs on the MATCHUP key (m:1 validated), never on slot.

## Same-population checks

- Both arms are scored on the identical sorted start-key list (one loop, one
  realized map); key-set equality asserted, never an implicit intersection.
- Cohort restriction (semi-join) applied to requests and assessment BEFORE
  feature construction; excluded starts counted, never silently absorbed.
- Duplicate actual-PA identities refuse; a start without 9 usable slots
  refuses (same as the reviewed runners).
- Per-PA descriptive metrics use the identical matched-PA set for both arms
  (denominators asserted equal).

## Endpoints

- **Primary:** delta = RPS(binary-K) - RPS(multinomial-K control) per start on
  identical assessment keys, paired slate-date bootstrap (2,000 draws,
  seed 20261001) via `bl.paired_contrast` (legacy label disclosed verbatim).
- **Descriptive (not decisive):** per-PA K log loss and Brier for both arms on
  the identical matched-PA population, with denominators recorded.

## Practical decision rule (pre-declared before scoring)

Three separate conclusions, per the registered conventions:

1. **Statistical direction:** CI entirely below zero - binary-K favored;
   entirely above - multinomial retained; overlapping zero - inconclusive,
   never treated as equivalence.
2. **Practical magnitude:** |delta| < 0.005 count-RPS is directionally
   uninformative regardless of CI direction (same engineering threshold
   rationale as the workload card; an engineering decision, not a
   demonstrated minimum detectable effect).
3. **Promotion:** none automatic. A favorable result registers a candidate
   K-probability-source change for a FUTURE frozen contract decision;
   promotion requires its own pre-registered, separately authorized change.
   The reconstruction gate must pass before any contrast is reported.

## Artifacts (write-once run directory)

| File | Content |
|---|---|
| binary_k_comparison_report.json | Both arms' mean count-RPS, paired delta + CI, reconstruction evidence, per-PA descriptive metrics, counts |
| binary_k_per_start_v1.parquet | game_pk, side, pitcher, game_date, realized_k, rps_multinomial_control, rps_binary_k, rps_diff |
| keyed_pa_probabilities.parquet | (game_pk, side, pitcher, slot, batter, p_k_multinomial, p_k_binary) |
| model_artifacts.json | Both fitted models: coefficients, scaler mean/scale, feature order, class order, settings (reloadable) |
| k_pmf_per_start_v1.parquet | Per-start 24-bucket K PMFs for both arms |
| bf37_pooled_by_date_v1.parquet | Pooled BF37 per cutoff date |
| receipt_initial.json | Immutable: ack, code identities, config, expected input hashes |
| receipt_final.json | Receipt chain + cohort identity + reconstruction + output hashes + acceptance |
| failure_record.json | On any exception: stage, error, initial-receipt sha; then re-raise |

## Limitations

- Development evidence on the registered 2025H1 cohort; not a fresh final
  test; no production, betting-value, or causal claims.
- The binary arm models only P(K); it cannot represent the non-K outcome
  structure (walk-class vs in-play-out). This comparison says nothing about
  uses of the non-K classes beyond the K-count aggregation, which consumes
  only p_k.
- Single-change discipline: scaler, features, regularization, training rows,
  workload, and cohort are held fixed; the comparison isolates the K
  probability source, not the estimator family in general.
- The fitted coefficients are serialized for reproducibility; they are NOT
  re-tuned or recalibrated by this experiment.
- 2026 remains untouched (no-2026-tuning rule); protected partitions and old
  registrations unchanged.
- Real-data execution requires the reviewed packet plus explicit owner
  authorization; this card authorizes implementation and synthetic testing
  only.
