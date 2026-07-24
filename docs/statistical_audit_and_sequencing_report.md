# Statistical rigor audit and feature-registry sequencing

Audit date: 2026-07-24

Scope: current pitcher strikeout-rate pipeline, active feature-research scripts,
generated development artifacts, and documented model evaluations. The report
now includes the implemented expanded-feature remediation and registry result.

## Executive findings

- **IN PROGRESS:** deterministic pruning reduced the active design from 256 to
  248 features and restored full rank, but multicollinearity remains severe:
  242 ordinary VIF values exceed 5 and 236 exceed 10 on the corrected
  production-only split. The current 563-feature research audit yields a
  separate 165-feature Ridge proposal with four VIF values above 10; it is not the
  production feature list.
- **RESOLVED:** `src/Python/features.py` now excludes every rolling Contact%
  and CSW% identity while retaining Whiff%, SwStr%, and called-strike rate.
- **RESOLVED:** feature and window selection now uses inner chronological folds
  contained wholly within outer training data; outer folds are confirmation
  only, and the reused `_research_folds` API has been removed.
- **RESOLVED FOR FUTURE FITS / HISTORICAL RISK REMAINS:** the trainer now
  filters to 2023-2024 before splitting, but prior runs trained on early 2025
  and scored `2025-07-06+`. No part of 2025 is pristine.
- **RISK FOUND:** current Ridge and LightGBM fits optimize unweighted game-level
  K/PA, treating a low-PA start as equally informative as a high-PA start.
- **PARTIALLY RESOLVED FOR THE EXPANDED CANDIDATES:** a 248-feature production
  allow-list and a separate VIF-reduced Ridge proposal now exist, but formal
  Step 7 registry freeze has not occurred. Drift, calibration, and broader
  selection-stability analysis remain gaps.
- **Recommendation:** complete the unresolved grouped-family and PA-aware
  modeling work before formal registry freeze, then reserve genuinely future
  post-freeze games as the next pristine test.

### Expanded-feature result — **RESOLVED**

The requested P2 arsenal, count-state, BIP/BABIP, arm-angle, fixed-formula
SIERA, and run-expectancy candidates were built with prior-game/date-only
rolling logic. Arm-angle coverage is 98.63% in 2023, 99.30% in 2024, and 99.48%
in 2025. Conventional Strike% and neutral count share are diagnostic-only exact
identities; WPA is rejected as leverage context.

The current training-only diagnostic contains 563 eligible research columns,
is full rank, and has 516 VIF values above 10. Its Ridge proposal contains 165
columns with median VIF 4.263, maximum 14.618, and four values above 10.

Reliability and nested selection did not justify promotion of the 53
pitcher-side additions. BIP%, behind-count share, two-strike reach, put-away%,
and arm angle passed the lower-CI `r=.50` repeatability gate, but no pitcher
expanded family or window won inner selection for either outer fold/model.
Overall, pitcher pitch-type, and batter pitch-type run value failed the
reliability gate. The four-feature batter-discipline nominee improved both
LightGBM outer folds but had mixed Ridge support, so it also remains
research-only. The stabilization-qualified batter quality weighted-dispersion
family likewise improved both LightGBM outer folds but worsened Ridge MAE in
both. Accordingly:

- all 315 expanded columns remain research-only pending registry freeze;
- production LightGBM remains the 248-feature audit-corrected baseline;
- Ridge has a separate 165-feature interpretation proposal;
- 2025 was not read during diagnostics or selection.

Pointers: `artifacts/feature_research/expanded/candidate_feature_registry.csv`,
`final_lightgbm_registry.csv`, `final_ridge_registry.csv`,
`candidate_ablation_*`, `window_ablation_*`, and
`artifacts/stabilization/expanded/`, plus the batter-discipline stabilization
and ablation files named in Part 2.

## Part 1: Statistical rigor audit

### 1. Multicollinearity (Ridge only) — **IN PROGRESS**

The original audit used all 9,374 development rows and all 256 eligible
features. It found rank 250, 252 generalized VIF values above 5, and 242 above
10. Those historical numbers are retained as the pre-remediation finding.

Phase 1 now has a reproducible, correctly scoped diagnostic:

- only the 6,557-row chronological training partition ending 2024-06-08;
- 248 features after deterministic pruning;
- full matrix rank 248, so ordinary inverse-correlation VIF is defined;
- 242 VIF values above 5 and 236 above 10;
- leading VIF values remain in the thousands for overlapping windows,
  release-point, and pitch-usage features.

The implemented order is now:

1. remove deterministic identities;
2. run full Pearson, targeted Spearman, and narrow Kendall checks;
3. rerun ordinary VIF and form Pearson-linked groups for VIF above 10;
4. select one evidence-based representative per group as a registry proposal.

This is relevant to Ridge coefficient stability and interpretation. VIF should
not be used as a LightGBM pruning rule.

Resolution pointer: `scripts/feature_diagnostics.py`,
`artifacts/feature_research/vif.csv`, and
`artifacts/feature_research/vif_cluster_selection.csv`.

### 2. Deterministic redundancy — **RESOLVED**

The pre-remediation identities were:

```text
contact_rate = 1 - whiff_rate
csw_rate = swstr_rate + cs_rate
```

`src/Python/features.py` now rejects all overall and pitch-type rolling
`contact_rate` and `csw_rate` variants. Whiff%, SwStr%, and called-strike rate
remain. Regression tests cover both direct validation and trainer-list
exclusion. The expanded pass also rejects conventional Strike% (`1 - Ball%`)
and neutral count share (the omitted ahead/neutral/behind reference).

The usage-composition audit found no exact sum-to-one or rank deficiency among
the eight retained pitch shares: each of six hand/window matrices has rank
eight. They are nevertheless near-compositional—82.2%-96.3% of complete rows
sum within one percentage point of one—and remain grouped VIF concerns.

Resolution pointer: `tests/test_feature_safety.py` and
`artifacts/feature_research/usage_composition_rank_audit.csv`.

### 3. Leakage, multicollinearity, and redundancy separation — **IN PROGRESS**

These are distinct problems, but the active workflow does not yet provide
three complete defenses:

- **Target leakage:** **OK.** `src/Python/features.py` excludes labels,
  identifiers, same-game outcomes, and unknown numeric columns. Rolling tests
  enforce prior-game/date-only inputs.
- **Multicollinearity:** **IN PROGRESS.** Full Pearson, targeted Spearman,
  narrow Kendall, ordinary VIF, and preliminary VIF groups now exist. Feature
  reduction and registry decisions have not yet occurred.
- **Deterministic redundancy:** **RESOLVED.** Exact Contact% and CSW%
  identities are excluded and tested.

The feature allowlist is a leakage-safety gate, not a feature-selection or
multicollinearity defense. Treating “approved pregame” as “appropriate to fit”
would conflate these concerns. Implementation pointer:
`artifacts/feature_research/feature_diagnostics_metadata.json`.

### 4. Stepwise regression — **OK**

No forward, backward, or stepwise regression implementation was found in the
active Python, notebook, or documentation search. It is not used as the final
selection method. This should remain the policy because repeated uncorrected
entry/removal tests inflate false discoveries and produce unstable selections.

### 5. Chronological validation — **OK**

No random `KFold`, `StratifiedKFold`, `train_test_split`, or generic
`cross_val_*` usage was found.

Current validation is chronological and date-disjoint:

- production trainer: one approximately 70/15/15 chronological split;
- feature research: three expanding 2023-2024 folds;
- stabilization: consecutive denominator buckets within player histories.

The date-disjoint implementation is correct, but item 6 identifies a separate
nested-selection problem.

### 6. Nested rolling-origin validation — **RESOLVED**

The original three-fold implementation reused validation scores for selection
and reported improvement. It has been retired: `_research_folds` no longer
exists, and both ablation scripts now call `nested_research_folds`.

The implemented outer confirmations are:

- `outer_2024_h1`: train all 2023; confirm 2024-03-28 through 2024-06-30.
  Its two inner folds split 2023 into expanding mid- and late-season
  selection periods.
- `outer_2024_h2`: train through 2024-06-30; confirm 2024-07-01 through
  2024-09-30. Its two inner folds validate on 2023 H2 and late 2024 H1.

Every feature/window configuration is scored only on inner folds. Mean inner
MAE selects one configuration separately for each outer fold and model; that
choice is then refit on the complete outer-train rows and evaluated once on
outer confirmation. Tests enforce date disjointness, whole-date membership,
inner containment within outer train, and zero inner contact with outer
validation.

Resolution pointer:
`Models/Strikeout-Model/Strikeout-EDA/nested_cv.py`,
`tests/test_nested_cv.py`, `candidate_ablation_inner_*`,
`window_ablation_inner_*`, and the matching metadata JSON files under
`artifacts/feature_research/`.

The infrastructure gap is resolved; configuration stability is not implied.
Different configurations were selected across outer folds/models, which is
honest evidence that the current candidate choices are not yet universal.
After the eventual procedure is frozen, the next pristine test still requires
future post-freeze data rather than the previously consulted 2025 benchmark.

### 7. Regularization paths — **GAP**

All requested comparisons are feasible:

- **RidgeCV:** near-drop-in replacement for fixed `Ridge(alpha=1.0)`. Search
  log-spaced alphas inside inner chronological folds, not ordinary built-in
  generalized CV over shuffled observations.
- **Elastic Net:** feasible through `ElasticNet`/`ElasticNetCV`; useful as a
  sparse comparison, although correlated predictors may be selected
  arbitrarily. Deterministic identities should still be removed first.
- **LightGBM controls:** current code already sets `num_leaves`,
  `min_child_samples`, column subsampling, and L1/L2 penalties. Add inner-fold
  searches for shallower `max_depth`, larger `min_child_samples`, smaller
  feature fractions, and stronger `reg_alpha`/`reg_lambda`. Set a positive
  bagging/subsample frequency if row subsampling is intended; `subsample=0.8`
  alone may remain inactive under LightGBM defaults.

Production `train.py` has early stopping; the feature/window ablation scripts
use a fixed 800 trees without early stopping. That mismatch should be resolved
inside the nested protocol.

Expected scope: moderate research-script changes, no Level 1-3 schema change.

### 8. Feature-selection stability — **GAP**

The current process reports positive-fold counts from one three-fold pass, but
does not independently test selection stability:

- no season-specific family importance;
- no grouped permutation importance;
- no leave-one-family-out/drop-column stability run;
- no bootstrap selection frequency;
- no current leakage-safe SHAP analysis.

Recommended defense:

1. define non-overlapping feature families;
2. run grouped drop-column or grouped permutation importance in each outer
   fold and separately by season;
3. retain a family only when direction and materiality are stable;
4. use SHAP only after deterministic and highly correlated predictors have
   been reduced, because SHAP attribution is unstable and divided arbitrarily
   among interchangeable predictors.

The only SHAP artifact is an archived pre-pipeline analysis containing
forbidden same-game fields; it is not current evidence.

### 9. Missingness and cold starts — **RISK FOUND**

The original all-development-row audit found 105 of 256 features above 20%
missingness, 45 above 50%, and 15 above 80%. The reproducible corrected
training-only artifact now finds:

- 100 of 248 features exceed 20% missingness;
- 45 exceed 50%;
- 15 exceed 80%;
- all features above 20% are pitch-type physics features;
- splitter physics P3/P5/P10 are approximately 83% missing.

Current handling:

- LightGBM routes `NaN` natively;
- Ridge median-imputes each feature;
- no explicit missingness indicators are created;
- pitch usage is constructed as zero when the corresponding hand denominator
  is zero, which can conflate “no opportunity against this hand” with “zero
  usage”;
- pitch physics remain null when a pitch is absent, but Ridge median imputation
  can turn “does not throw this pitch / no history” into typical league physics.

The model therefore mixes arsenal absence, cold-start history, and measurement
missingness. Required next work:

- distinguish “pitch not in arsenal,” “no prior sample,” and “measurement
  unavailable”;
- add indicators only where that distinction is available pregame;
- do not blanket-fill absent-pitch physics with zero;
- evaluate league/prior-season shrinkage for new pitches and debuts;
- ablate sparse pitch-type families before retaining them.

### 10. Heteroskedastic K/PA target — **RISK FOUND**

Current Ridge and LightGBM calls fit unweighted game-level `k_rate`. A 10-PA
start and a 28-PA start contribute equally to the loss even though the former
has much larger sampling variance. This conflicts with the denominator-aware
stabilization evidence.

Two feasible corrections:

#### A. PA-weighted regression

- Pass training-row `PA` as `sample_weight` to Ridge and LightGBM.
- Pass validation weights consistently for tuning/early stopping and report
  both weighted likelihood-oriented metrics and unweighted game-level metrics.
- For sklearn pipelines, route the weight to the final estimator; for LightGBM,
  use its native `sample_weight`.
- Keep `PA` excluded from prediction features.

Expected scope: small-to-moderate changes in `train.py`, ablation scripts,
metric reporting, and tests. No pipeline schema change because `PA` is already
retained as a label/evaluation field.

PA weighting is only an approximation to a binomial likelihood and does not
model extra-binomial game/pitcher variation.

#### B. Binomial/beta-binomial formulation

- Treat each game as `K` successes in `PA` trials.
- Predict pregame strikeout probability from leakage-safe features.
- Use PA as part of the response likelihood, never as a prediction-time
  feature.
- Add beta-binomial dispersion to model excess variation and produce a count
  distribution conditional on projected exposure.

Expected scope: moderate-to-large. It requires a new estimator/objective,
likelihood and probability metrics, count-PMF utilities, calibration tests,
and artifact schema. The current Level 3 labels are sufficient for historical
training.

Recommendation: add weighted regression as a diagnostic baseline, but evaluate
binomial and beta-binomial models as the statistically coherent solution.

### 11. Population-selection bias — **RISK FOUND**

`MIN_STARTER_BATTERS_FACED = 9` is a postgame filter used to define rows for a
pregame model. It does not leak a feature value into retained rows, but it
conditions the training population on an outcome unavailable before first
pitch. Injuries, ineffective early hooks, openers, and piggyback plans can be
systematically excluded.

Consequences:

- reported accuracy applies to “starts that ultimately reached 9 PA,” not
  automatically to all announced starters;
- live inference cannot know whether a starter will satisfy the filter;
- excluding early hooks can make workload and count performance optimistic;
- K-rate and future TBF models would inherit inconsistent populations.

Required resolution:

- define the deployment population using pregame-observable role information
  such as announced starter, opener designation, rotation role, and expected
  workload;
- report coverage for all announced starters and for a prespecified
  conventional-starter subgroup;
- keep the current cohort only as a conditional research estimand until that
  definition is available;
- explicitly address openers/piggybacks before Step 7 registry freeze.

### 12. Temporal drift and calibration — **GAP**

No active season-over-season feature/target drift report was found. No binned
predicted-versus-observed calibration analysis, Brier/log score, calibration
slope/intercept, or count-probability reliability diagram exists.

Both are listed as future work in `PAPER_NOTES.md`; neither is implemented.
Required analyses include 2023→2024 feature/missingness drift, target drift,
model residual drift, and calibration by season/month/workload group.

### 13. Multiple comparisons and final-test integrity — **RISK FOUND**

Using a declared counting unit, the paper log represents:

- **7 primary logged workflows:** overall stabilization, pitch-type
  stabilization, feature-family ablation, window ablation, superseded
  overlapping-boundary baseline, superseded 2025-contaminated date-disjoint
  baseline, and the corrected 2023-2024-only baseline;
- **109 stabilization curves:** 13 overall player/stat curves
  (9 pitcher + 4 batter) and 96 pitch-type/stat curves
  (8 pitch types × 12 statistics);
- **58 distinct ablation configuration/model experiments:** 29 unique
  configurations across the family and window screens × Ridge/LightGBM;
- **174 unique fold-level ablation scores:** each of those 58 experiments on
  three folds. The stored scripts produce 180 rows because the same core is
  rerun in both screens;
- **0 comparative shrinkage searches:** the 200-PA batter prior and
  1,000-fly-ball xFIP prior are fixed methodological choices, not logged grids;
- **8 logged baseline/internal-test evaluations:** two superseded
  overlapping-boundary evaluations, three 2025-contaminated date-disjoint
  evaluations, and three corrected 2023-2024 internal-test evaluations.

The 109 stabilization curves and 174 unique ablation fold scores are logically
restricted to 2023-2024 by code and metadata: no 2025 row enters a fit, score,
or reported selection result. However, the research scripts eagerly open
multi-season parquet files before filtering to 2023-2024. If “untouched” is
intended as a strict data-access guarantee rather than “unused in analysis,”
the holdout must live in a separate artifact with an access guard.

Five of those model evaluations did read the
`2025-07-06+` partition:

- superseded Mean and Ridge;
- corrected Mean, Ridge, and LightGBM.

Therefore it is false to describe that partition as “still untouched” or as a
future first-and-only honest check. The corrected baseline is valid historical
evidence, but repeated future consultation would compound test-set adaptation.
The next pristine final test must be genuinely future, post-freeze data.

### 14. 2025 train/holdout contamination — **RESOLVED**

The original finding was broader than item 13 stated: the trainer loaded the
full 2023-2025 Level 3 frame and split it 70/15/15, so January-April 2025
entered training and April-July 2025 entered validation before
`2025-07-06+` was tested. Thus the complete 2025 season was never a holdout.

`TRAIN_SEASONS` is now `(2023, 2024)`, and `train.py::load_frame` independently
filters the loaded parquet to those configured seasons before chronological
splitting or preprocessing. A regression test proves that an existing parquet
containing 2025 cannot reintroduce holdout rows. Pipeline generation separately
uses `PIPELINE_SEASONS = (2023, 2024, 2025)` so a fresh rebuild preserves the
historical holdout data and produces the 2026 park lookup. The corrected split
is:

- train: 2023-03-30 through 2024-06-08 (6,557 rows);
- validation: 2024-06-09 through 2024-08-05 (1,404 rows);
- internal test: 2024-08-06 through 2024-09-30 (1,413 rows).

Resolution pointer: `src/Python/config.py`,
`Models/Strikeout-Model/train.py`, `tests/test_train.py`, and
`artifacts/models/lightgbm_krate_20260724_142209.json`.

## Part 2: Required sequencing before a TBF model

Phase 1 resolved Step 2 and materially advanced Step 1. Steps 3 and 4 retain
their prior partial evidence. The project is still mid-feature selection and
is not ready to advance beyond this sequence.

### Step 1. Feature dictionary, missingness, and clusters — **IN PROGRESS**

What exists:

- a reproducible 563-row current research feature dictionary with name,
  generated definition, source function, family, training-split missingness,
  VIF, and VIF cluster; the 248-row root artifact remains the pre-expansion
  baseline;
- a full Pearson matrix and flagged pairs at `|r| > 0.80`;
- targeted Spearman analysis for rolling-window, shrinkage, and xFIP families;
- a narrow Kendall spot-check for tied low-count families;
- ordinary full-design VIF and Pearson-linked groups for VIF above 10.
- a proposal reducing 62 correlated serious-VIF clusters to one representative
  each using stabilization first, then missingness, then definition simplicity.

Artifacts: `artifacts/feature_research/feature_dictionary.csv`,
`pearson_*`, `spearman_*`, `kendall_*`, `vif.csv`, and
`feature_diagnostics_metadata.json`, plus `vif_cluster_selection.csv`,
`vif_reduced.csv`, `vif_reduced_features.csv`, and
`vif_reduction_metadata.json`.

The proposal reduces 248 features to 74 without modifying `train.py`. Median
VIF falls from the severe full-design regime to `3.214`; maximum VIF is
`16.432`, and only two features remain above 10: `xwOBA_P5` and `xFIP_P5`.
Those two clusters are explicitly flagged as unresolved rather than silently
pruned again.

The goal is correlated-cluster reduction, not forcing every feature below VIF
10. Rolling windows are redundant by design because they represent overlapping
histories, and tree predictive performance is generally insensitive to
multicollinearity even though importance attribution can become unstable.
Therefore VIF guides representative selection for a compact/interpretable
Ridge design; it is not a mandatory LightGBM pruning rule.

What is missing:

- hand-curated numerator/denominator and availability-date fields;
- missingness by season and cold-start semantics;
- registry-level keep/drop decisions and production adoption of the proposal.

Status: not complete.

### Step 2. Remove deterministic redundancy — **RESOLVED**

All rolling Contact% and CSW% variants are excluded by the feature-safety gate,
while Whiff%, SwStr%, and called-strike rate remain. Tests enforce the policy.
The usage audit found no exact rank deficiency, although near-compositional
behavior remains a VIF concern. Resolution pointer:
`artifacts/feature_research/usage_composition_rank_audit.csv`.

### Step 3. Grouped ablations across every family — **IN PROGRESS**

Ablation-tested:

- pitcher Whiff%, SwStr%, Ball%, and GB% additions;
- opponent-lineup Whiff% and SwStr% additions;
- compact combinations of those candidates.

Not comprehensively ablation-tested on the corrected frame:

- K%, BB%, called-strike%, chase%, zone%, HR%, xBA, wOBA, xwOBA, and other
  nonredundant rate families;
- pitch physics grouped by pitch type and measurement;
- handedness-specific pitch usage;
- release mechanics;
- FIP/xFIP;
- the complete lineup family including K%, handed K%, and chase%;
- park factor;
- home/context;
- rolling-only versus season-to-date-only families.

The blank leave-family-out plan in `PAPER_NOTES.md` confirms this gap.

### Step 4. Select a small number of windows — **PARTIALLY RESOLVED**

Completed evidence:

- denominator-aware stabilization for 21 pitcher and 8 batter overall
  statistics;
- denominator-aware pitch-type stabilization for 96 pitch-type/stat pairs;
- predictive window screen for pitcher Whiff%, SwStr%, and Ball%;
- an 88-metric map from actual rolling usage to the `r=.50` crossing evidence;
- a capped proposal for the three material gaps: BABIP P20/P30/P35, arm angle
  P2/P3, and run value P10/P20/P25 (five new metric-window values total);
- metric-isolated nested inner/outer re-ablation of exactly those candidates;
- leakage-safe batter Z-Swing%, Swing%, Z-Contact%, and BB% season-to-date and
  P5/P10/P20 features, plus one stabilization-nominated lineup-family test.

The targeted confirmation does not justify changing the global rolling
constants. BABIP selected core in both LightGBM folds and in one Ridge fold; the
Ridge-selected P30 alternative in the other fold worsened outer MAE. Arm angle
selected P3 in one LightGBM fold with a `0.000027` MAE improvement and selected
core in the other three model/fold combinations. Run value is model-dependent:
P25 was selected by LightGBM in both folds and improved outer MAE by `0.000032`
and `0.000603`, while Ridge selected core/P10 and had no positive outer fold.
Accordingly, P25 is a LightGBM-specific registry proposal, not a module-wide
default; BABIP, arm angle, and Ridge run value remain provisional.

The four added batter rates crossed `r=.50` at approximately 14.3 games for
Z-Swing%, 13.3 for Swing%, 20 for Z-Contact%, and 50 for BB%. To avoid another
window search, the nested family test declared one configuration in advance:
opponent-lineup Z-Swing% P10, Swing% P10, Z-Contact% P20, and BB%
season-to-date. LightGBM selected it in both outer folds and improved MAE by
`0.000962` and `0.000743`. Ridge selected core in 2024 H1, then selected the
family in H2 with a `0.000139` improvement. This supports the family for
LightGBM; Ridge support remains mixed.

The hitter-side expansion then mirrored the pitcher workflow for 14 quality
and batted-ball metrics. Ten cleared the lower-bootstrap-CI `r=.50` gate:
hard-hit%, barrel%, average exit velocity, average launch angle, xBA, xwOBA,
HR%, FB%, HR/FB, and pulled-air balls per BIP. BABIP, sweet-spot%, wOBA, and
run value per pitch did not. A capped nested comparison tested only core, flat
lineup means, batting-order weighted means, and weighted means plus dispersion,
using one stabilization-nominated representation for each qualified metric.

Weighted mean plus dispersion won inner selection for both models in both outer
periods. LightGBM outer MAE improved by `0.000360` and `0.000152`; Ridge outer
MAE worsened by `0.000209` and `0.000200`. This supports lineup heterogeneity
as a LightGBM-specific research family, not a production or model-agnostic
promotion. Batting-order weights use only prior-date league PA by slot.

Artifacts:

- `artifacts/feature_research/window_stabilization_gap.csv`;
- `artifacts/feature_research/window_change_proposals.csv`;
- `artifacts/feature_research/targeted_window_ablation_*`;
- `artifacts/stabilization/expanded/batter_discipline/`;
- `artifacts/feature_research/batter_discipline_ablation_*`;
- `artifacts/stabilization/expanded/batter_quality/`;
- `artifacts/feature_research/batter_quality_ablation_*`.

Incomplete:

- predictive selection for most rate families;
- physics, movement, usage, release, and FIP/xFIP windows;
- batter K-window/shrinkage choices for lineup construction;
- nested confirmation of Ball% P5 and SwStr% P20;
- direct stabilization studies for 71 mapped metrics. This includes the
  handedness-specific pitch-usage shares (`*_usage_vR` and `*_usage_vL`) that
  can produce a profile like “pitch usage by batter hand”; those shares are
  calculated per start and currently rolled as unweighted P3/P5/P10 means.

The production defaults remain 5/10/20 for rates and 3/5/10 for mean/physics
features. The “rolling windows provisional” caveat is therefore narrowed but
still open; no family-wide final window policy exists.

### Step 5. Compare unweighted and PA-aware likelihoods — **NOT STARTED**

No weighted Ridge/LightGBM, binomial regression, or beta-binomial model has
been evaluated. This is the next major statistical modeling comparison after
deterministic pruning and a first-pass family dictionary.

### Step 6. Nested chronological stability — **RESOLVED**

Feature and window selection now occurs on inner chronological folds only.
Each selected configuration is refit and reported on a distinct outer
confirmation period. `_research_folds` is removed, metadata records every
boundary, and focused tests enforce no inner/outer leakage. Resolution pointer:
`Models/Strikeout-Model/Strikeout-EDA/nested_cv.py` and
`artifacts/feature_research/*ablation_inner_selection.csv`.

### Step 7. Explicit compact registry — **IN PROGRESS**

`artifacts/feature_research/expanded/candidate_feature_registry.csv` is now a
566-row decision registry: 248 production-baseline features, 315 research-only
candidates, and 3 explicit rejections. It records family, definition,
numerator/denominator, source, missingness, deterministic status, eligibility,
decision, and rationale. `final_lightgbm_registry.csv` materializes the
248-feature production allow-list; `final_ridge_registry.csv` is a separate
165-feature interpretation proposal.

This resolves the earlier absence of a row-level registry artifact, but not
formal freeze. The production list has not been locked with a final dataset
hash, parameters, approval date, and protected post-freeze evaluation after
Steps 3 and 5. The historical “240-feature leading development registry”
remains an experimental configuration rather than the final compact registry.

### Step 8. Single protected evaluation — **RISK FOUND / BLOCKED**

Steps 1, 3, 4, 5, and 7 remain incomplete. In addition, `2025-07-06+` has
already been scored by five logged baselines, so it cannot fulfill the
requested untouched-test role.

Do not use it for further feature decisions. After Steps 1-7, report it only as
a previously observed historical benchmark and designate future post-freeze
games as the new pristine evaluation.

## Part 3: Strikeout-count probability model scoping

All count-model options are **NOT STARTED**. Actual same-game TBF/PA must never
be a prediction-time feature. It may be retained as response structure and an
evaluation oracle. End-to-end evaluation must use projected TBF generated
without access to the same game's outcomes.

In the current repository, starter TBF is represented by `PA`; there is no
separate `actual_tbf` column. Level 3 retains `K`, `PA`, `Outs`, and `k_rate`,
which is enough to fit historical binomial/beta-binomial responses. It does not
contain `projected_tbf` or the lagged workload features needed to produce one.
Level 1 retains workload foundations such as pitches and outs, but Level 2
currently drops them except for active labels, so a TBF training spine must
extend label/history retention or rebuild from Level 1.

The original 2023-2025 dispersion ranges (`1.38-1.53` for count variance and
`1.35-1.52` for K/PA variance) do not reproduce under the required
training-only scope, and their PA-bin edges were not documented. The
reproducible 6,557-row training-only analysis uses bins `(8,12]`, `(12,16]`,
`(16,20]`, `(20,24]`, `(24,28]`, and `(28,∞]`; its count-variance ratios
range `1.259-1.502` and K/PA-variance ratios range `1.273-1.496`. Most bins
still show material overdispersion, but these are model-scoping diagnostics,
not final out-of-sample dispersion estimates. See
`artifacts/feature_research/dispersion_ratios.csv`.

### 1. Beta-binomial regression — **NOT STARTED / RECOMMENDED**

Natural formulation:

```text
K_game | PA_game, p_game, dispersion ~ Beta-Binomial
p_game = link(leakage-safe pregame features)
```

Advantages:

- models `K` successes out of `PA` trials directly;
- automatically gives high-PA games more likelihood information;
- handles extra-binomial variation beyond ordinary binomial sampling;
- yields `P(K >= n | projected TBF)` directly;
- respects the finite support `0 <= K <= TBF`;
- can unify the heteroskedastic K/PA correction and count-probability layer.

Requirements:

- custom/scientific likelihood tooling beyond the current sklearn interface;
- inner/outer chronological fitting and dispersion validation;
- count PMF/CDF, log score, Brier score, calibration, and tail diagnostics;
- a distribution for projected TBF, not only a point estimate, if full
  workload uncertainty is to be propagated.

Leakage rule: historical actual PA is the trials component of the response,
not a model feature. At inference and end-to-end backtest time, condition on
out-of-fold/projected TBF only. To include workload uncertainty, mix the
beta-binomial count distribution over the predicted TBF distribution.

Feasibility: high statistical fit, moderate-to-large implementation scope.

### 2. Negative-binomial count regression with log-TBF offset — **NOT STARTED**

Natural formulation:

```text
log(E[K_game]) = log(projected_TBF_game) + f(pregame features)
```

Advantages:

- familiar overdispersed count model;
- direct expected-count and tail probabilities;
- easier implementation than custom beta-binomial in many libraries.

Limitations:

- strikeouts are bounded by TBF, while negative binomial support is unbounded;
- dispersion represents count variation but not the finite-trials mechanism;
- a point offset understates uncertainty in projected workload;
- using actual same-game TBF as a prediction input or end-to-end offset would
  leak workload information.

Training/evaluation should use cross-fitted projected TBF when testing the
real deployed pipeline. Actual TBF remains an oracle for workload-model
evaluation, not the deployed count-model input.

Feasibility: moderate implementation scope; useful challenger, not the most
natural primary model.

### 3. Poisson GLM baseline — **NOT STARTED**

Natural formulation:

```text
log(E[K_game]) = log(projected_TBF_game) + linear pregame predictor
```

Advantages:

- simplest auditable count baseline;
- fast and interpretable;
- establishes whether more complex dispersion models add value.

Limitations:

- assumes conditional variance equals the mean;
- has unbounded support and may understate tails;
- does not represent finite PA trials or workload uncertainty.

The observed within-PA-bin overdispersion already makes the Poisson variance
assumption doubtful, which is why it belongs only as an auditable floor.

Feasibility: small implementation scope. It should be retained as a baseline,
not expected to be the final probability model.

### Unified recommendation — **NOT STARTED / PLANNED**

After the feature-registry sequence:

1. compare unweighted K/PA regression, PA-weighted regression, binomial
   regression, and beta-binomial regression on the same nested folds;
2. select the rate/likelihood framework before building a separate count
   mechanism;
3. if beta-binomial is well calibrated, use it as the unified skill and
   conditional count model;
4. compare Poisson and negative binomial as transparent count baselines;
5. combine every count model with cross-fitted projected-TBF inputs and test
   both point-exposure and full workload-distribution propagation.

This prevents building one mechanism to correct K/PA heteroskedasticity and a
second disconnected mechanism for count probabilities when one beta-binomial
likelihood may address both.
