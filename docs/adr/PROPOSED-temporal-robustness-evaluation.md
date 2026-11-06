# Temporal-robustness evaluation of the retained candidate (manifest + specification)

## ID

`temporal_robustness_v1`

## Status

SPECIFICATION RESOLVED (2026-11-04) - the review items are incorporated
below and the executable checkpoint implements them: explicit period
definitions with identical-arm populations; fold/period feasibility before
fitting; label-coverage and complete-outcome checks; saved class
probabilities, PMFs, scores, and receipts; synthetic tests for chronology
and period accounting; R3 and 2026 structurally inaccessible to this
evaluation path. Implementation uses the current harness
(`temporal_robustness_evaluation.py`); exact R1/R2 packet published
separately. No tuning, no new features, no calibration, no additional
learner. No real-data execution without the reviewed packet + explicit
owner approval.

## Retained-candidate manifest (what is being evaluated)

The retained candidate is the 12-feature multinomial-plus-platoon pipeline
registered by the VERIFIED platoon_information_v1 run (Chat 2 verdict
2026-11-04) - NOT the LightGBM challenger (guard failed; control retained;
no adoption).

| Component | Identity |
|---|---|
| Model recipe | StandardScaler + sklearn LogisticRegression (C=1.0, lbfgs, max_iter=1000) multinomial; class probabilities via the identical softmax definition (2-class parameterization handled by the same definition); L2-regularized multinomial cross-entropy training loss; every training PA equally weighted |
| Features (12) | `ad.FEAT_H3` (8 registered) + 4 `platoon-features-v1` columns: shrunk (stand, p_throws) -> class rates, alpha = 40, strictly-prior pooling, unseen split/unknown hand -> global prior; switch-hitter forecast stand = modal strictly-prior stand conditional on the pitcher's hand (tie -> lexicographically smallest), then overall modal, then global fallback |
| Cutoff / label rules | states-v2 cutoff-correct construction (`forecast_states_v2.build_v2_states`: prior = ALL rows with game_date STRICTLY BEFORE each cutoff; same-date/future rows cannot enter); labels from the registered raw-Statcast terminal-event bridge (`statcast_event_bridge.attach_terminal_event_labels`: LEFT-join onto the declared PA population, conflict detection before any dedup, class_label >= 0 required for training/scoring) |
| Pooled workload | W0 pooled empirical BF37 per forecast cutoff (first-pitcher-of-record outings, opener-inclusive, history from 2023-01-01, add-one smoothing, registered tail conversion) - construction imported unchanged from the reviewed workload runner |
| Lineup assumptions | projected lineups only (no oracle manifests); 9 usable slots per start required; forecast-row batter stand is NOT pregame-observable for switch hitters (handled by the modal rule above); replacement batters count in realized K via actual-PA assessment |
| Aggregation | `ad.start_count_pmfs(p9, p9, pooled_bf37)["pmf_h3_raw"]` - 24-bucket K-count PMFs, registered binomial-conditional mixture over the cycled slot-mean |
| Artifacts (verified) | platoon run: `...\diagnostics\platoon_information_v1\` (receipt chain COMPLETED, hashes reconcile) - keyed probabilities, model artifacts, K PMFs, split-rate table, per-start parquet, receipts; LGBM run attempt 2: `...\diagnostics\lgbm_multiclass_v1_attempt2\` (control arm reproduces the same pipeline) |
| Code identities | runner `platoon_comparison.py` sha `8136e1a8...`; `platoon_features.py` sha `ccc56eca...`; adapter `adfa7283...`; m0 `5afe972b...`; workload_comparison `c0b391bb...`; kcount_combiner `94f57a49...`; statcast_event_bridge `5781b3cf...`; forecast_states_v2 `7ec56566...`; baseline_ladder `af81e313...`; binary_k_comparison `3ad1cced...` (all verified in the executed runs; full table in the packet) |

## Temporal-evaluation specification

### Purpose

Time-ordered robustness of the retained candidate: does the
multinomial-plus-platoon pipeline hold its forecast quality across
chronological periods, evaluated with the registered machinery and the
same endpoints, WITHOUT opening protected partitions or re-tuning?

### Periods (exact; dates verified against the registered source's observed game-date population)

| Period | Fit window | Score window | Distinct in-window date clusters (verified) | Prior exposure of the score window | Permission |
|---|---|---|---|---|---|
| R1 | 2023-03-30..2024-06-30 | 2024-07-01..2024-09-30 | fit 277; score 88 | EXPOSED: block_2024H2 outcomes were the estimation base of earlier arms and a canonical scoring population (count-agg v1) - NOT a fresh test | Existing registered-input permissions (same pinned pa_table) |
| R2 | 2023-03-30..2024-12-31 | 2025-01-01..2025-06-30 | fit 365 (incl. 277 + 88); score 98 (from 2025-03-18) | EXPOSED: block_2025H1 was the designated-eval cohort of all three verified lane runs - NOT a fresh test | Existing registered-input permissions |
| R3 | 2023-03-30..2025-06-30 | 2025-07-01..2025-09-28 | fit 463; score 86 | UNEXPOSED (confirm_2025H2 partition) | REQUIRES a specific new owner authorization - NOT granted by this specification and NOT requested in it |

Offseason feasibility (verified): the registered source contains ZERO
game dates 2024-10-01..2024-12-31 and 2023-01-01..2023-03-29 - fold/period
boundaries must respect observed date clusters only (the LGBM run's
infeasible calendar-month folds are the recorded precedent).

### Training / refit schedule

One refit per period at its declared fit-window end (expanding history,
fixed recipe, NO re-tuning, NO configuration search): R1 refit on
2023-03-30..2024-06-30; R2 refit on 2023-03-30..2024-12-31; (R3, if ever
authorized: refit ..2025-06-30). Each refit is a fresh fixed-recipe fit -
coefficients are never carried across periods.

### Cohort / coverage rules

- Scored population per period: projected-lineup requests restricted to
  the period's scored window; 9 usable slots per start; actual-PA
  assessment with repeat encounters; K-count over complete starter
  outcomes (realized K from ALL valid actual PAs).
- Coverage accounting: matched vs unmatched PAs, no-projected-matchup
  exclusions, missing-BF and no-lineup buckets reported per period -
  never silently absorbed.
- Cold-start and short-history behavior disclosed per period (the
  registered w150/EW state construction and the platoon fallback chain
  govern).

### Metrics (declared)

- Primary per period: per-PA multiclass log loss on the identical
  matched-PA population; contrast statistic = PER-START MEAN of per-PA
  log loss (each start equally weighted, PAs equally weighted within a
  start); paired slate-date bootstrap 2,000 draws seed 20261001.
- Comparisons per period: (a) retained candidate vs the 8-feature
  multinomial-plus-W0 control (isolates the platoon family's temporal
  stability); (b) descriptive per-period absolute levels vs the earlier
  verified runs' development results (context, not a claim).
- K-count acceptance guard per period: point-estimate margin 0.002
  count-RPS (candidate - control), NOT a statistical noninferiority
  claim; CI reported as context.
- Secondary: classwise log loss / Brier, K RPS means, K PMFs.

### Calibration allocation

NO calibration is fit in this evaluation. If a candidate survives
robustness and the owner orders a calibration milestone, its fit data
will be a chronological slice DISJOINT from every scoring window above,
pre-registered separately.

### Acceptance criteria (pre-declared)

- Robustness-supported: the candidate's per-period log-loss delta vs the
  control is directionally consistent (same sign) across R1 and R2 AND
  the K guard passes in every scored period AND the mean improvement is
  practically meaningful (> 0.0005 nats) in at least one period with no
  period degrading beyond the guard. Any such outcome registers a
  candidate for a FUTURE frozen-contract decision; promotion is never
  automatic.
- Not robustness-supported: inconsistent signs, a guard failure, or
  sub-threshold deltas everywhere -> retain the 8-feature multinomial-
  plus-W0 pipeline and close the platoon family's candidate registration.
- Direction and magnitude are reported separately for every period; CI
  overlapping zero is inconclusive, never treated as equivalence.

## Limitations

- All periods are development evidence on the registered source; none is
  a fresh final test (R1/R2 score windows are exposed as disclosed); R3
  would be the first unexposed confirmation and is OUT OF SCOPE until
  separately authorized.
- Matched-matchup PA coverage limitation carries over (K-count scoring
  over complete starter outcomes is a downstream check, not full PA-level
  coverage).
- No tuning, no feature changes, no new learner, no calibration, no SHAP,
  no taxonomy change; the recipe is frozen at the manifest identities.
- 2026 untouched (no-2026-tuning rule).

## Resolved review items (2026-11-04 specification checkpoint)

1. **Explicit period definitions + identical-arm populations (code
   constants):** the two periods are hardcoded runner constants (R1 fit
   `2023-03-30..2024-06-30`, score `2024-07-01..2024-09-30`; R2 fit
   `2023-03-30..2024-12-31`, score `2025-01-01..2025-06-30`). Within each
   period, BOTH arms are fit on the SAME fit rows and scored on the SAME
   matched-PA population (asserted); no arm sees extra rows.
2. **Fold/period feasibility BEFORE fitting:** per period - observed
   date-cluster counts in fit and score windows, nonempty populations,
   strict chronology (max fit date < min score date), and score-class
   compatibility (every scored class present in the fit population) are
   verified before any model fit; violations refuse.
3. **Label coverage + complete outcomes:** every scored PA carries a
   valid class label (unknown/out-of-set labels refuse with counts);
   every scored start has at least one actual PA (complete realized-K);
   matched/unmatched and missing-coverage buckets are reported per
   period, never silently absorbed.
4. **Saved artifacts:** per-period keyed class-probability tables (both
   arms), K PMFs, per-start scores, and the receipt chain - write-once.
5. **Chronology + period-accounting synthetic tests:** fit strictly
   precedes score in every period; per-period populations are disjoint
   (flipping R2 labels leaves R1 results unchanged and vice versa);
   period row/date counts asserted.
6. **R3/2026 structural inaccessibility:** the score windows end
   2025-06-30 (hard constants); the runner refuses any scored date on or
   after 2025-07-01 and any date in 2026; rows beyond the score windows
   are never read into a scoring path (excluded with disclosed counts).
7. **Machinery-identity anchor:** the registered 8-feature
   multinomial-plus-W0 recipe, refit on the declared `2024-05-01..
   2024-12-31` window and scored on the registered 2025H1 cohort, MUST
   reproduce the accepted per-start reference (`ae971758...`,
   `rps_w0_pooled`) within 1e-12 - run BEFORE the period contrasts and
   gating the whole evaluation. (No other reconstruction gate applies:
   the R1/R2 refit windows differ from any accepted fit window, so exact
   reference reproduction is only defined for the anchor.)
8. **Source declarations:** R1 scored actual PAs derive from the labeled
   PA source (the bridge labels the same pinned parquet); R2 scored
   actual PAs come from the pinned registered 2025H1 assessment artifact.
   Projected-lineups coverage verified for both score windows (88 and 98
   observed date clusters, date-column inspection only).
