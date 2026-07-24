# Research Log: Pregame Pitcher Strikeout Rate Projection

Running log of findings, bugs, and decisions for an eventual writeup.
Update incrementally as work happens -- do not reconstruct retroactively.

## 1. Problem framing

> One paragraph: what is being predicted (pregame k_rate = K/PA for starters),
> why pregame specifically (not postgame description), why K% as the target
> rather than ERA/WHIP/win probability. State the scope honestly (single
> season, starters only, min_batters_faced filter).

## 2. Data and architecture

> Describe the three-level pipeline (games -> rolling -> training) and why
> it's structured this way. Link to dev-notes.md for full technical detail --
> this section should be the "why," dev-notes.md is the "how."

- Source: Baseball Savant pitch-level Statcast via pybaseball. The repository
  provides a validated season download and an ID-resolved RotoGrinders/MLB
  daily lineup adapter, but no automated daily projection scheduler.
- Level 1: pitcher_games, pitch_type_games, batter_games, park_factors
- Level 2: pitcher_rolling, batter_rolling (leakage-safe rolling/season-to-date)
- Level 3: pitcher_training, batter_training (final model-ready frame)

## 3. Leakage-safety methodology

> This is the most important section for establishing rigor. Document the
> explicit rules enforced (no same-game stats as features, rolling windows
> shifted by one game/start, park factors from prior seasons only, chronological
> train/val/test splits) and HOW each was verified (notebook cells, tests).

### Rules enforced

- Same-game `K`, `PA`, `Outs`, and `k_rate` are labels/evaluation fields, not
  model inputs.
- Statcast pitch-result categories remain separate: `S` is a strike, `B` is a
  ball, and `X` is a ball put into play. BIP is contact and is never added to
  strike counts or strike-rate numerators.
- Rolling and season-to-date player statistics are shifted by one game or
  start, so the game being predicted never contributes to its own features.
- Season-to-date windows reset at season boundaries.
- Park factors for target season `Y` use only seasons before `Y`.
- Opponent-lineup aggregates use each initial-lineup batter's pregame rolling
  statistics; historical initial lineups are the first nine distinct batters.
- Train, validation, and test rows are split chronologically without shuffling
  or dividing a calendar date across partitions.
- Unexpected numeric columns are rejected unless they match the approved
  pregame context or lagged-feature naming rules.
- Player IDs, names, dates, and join keys remain model metadata.

### Verification method

- Notebook-based manual spot checks (first-game-of-season null checks,
  season-boundary reset checks, manual rolling-window recomputation)
- Level 3 null audit traced 90 fully-null opponent-lineup rows to each season's
  opening games (including the Tokyo Series), where no batter has prior
  season-to-date PA. The nulls were retained as the leakage-safe behavior.
- Automated test suite covers ballpark, batter features/rolling, feature
  safety, identity, pipeline stages, pitcher features/rolling, reliability,
  stabilization, Statcast primitives, and the production trainer/splitter
  (`tests/test_train.py`). The dated counts in individual bug entries are
  historical snapshots rather than the live suite size.

## 4. Bugs found and fixed (evidence log)

> Add one entry per bug, in the format below, AS THEY ARE FOUND. Do not
> wait until the end of the project to write these -- capture the before/after
> evidence while it's fresh. This section is what proves process rigor to
> a reader, not just a clean final result.

### Entry template
**Date found:**
**File(s):**
**Issue:** [one sentence]
**Evidence:** [query/output that revealed it]
**Fix:** [what changed]
**Verification:** [how you confirmed the fix worked]

---

**Date found:** 2026-07-23  
**File(s):** `src/Python/ballpark.py`  
**Issue:** Rays' 2025 home games (Steinbrenner Field) were blended with
Tropicana Field history under the same `home_team == "TB"` code, biasing
the park's strikeout factor.  
**Evidence:** `raw.filter(home_team == "TB", game_date >= 2025-01-01).select(game_pk.n_unique())`
returned 81 (full season), confirming real data contamination, not a
hypothetical edge case.  
**Fix:** Added `VENUE_OVERRIDES` date-scoped remapping so 2025 TB rows group
under a distinct venue label internally, while `home_team` remains the
external join key for Level 3.  
**Verification:** `test_ballpark.py` (5 focused tests at the time) passed;
manual notebook comparison confirmed 2025 TB receives a neutral factor with
no prior Steinbrenner history, while 2026 TB uses pre-2025 Tropicana history.

---

**Date found:** 2026-07-23  
**File(s):** `src/Python/ballpark.py`  
**Issue:** A target season absent from the Statcast input could silently
disappear from `pregame_park_factors` instead of receiving one lookup per team
with neutral fallbacks where needed.  
**Evidence:** The original target-season venue map was derived only from rows
whose `_source_season` equaled the target. With 2023-2025 input, that map had
zero rows for 2026.  
**Fix:** Added explicit target-season venue resolution from the latest observed
team set and retained left-join/fill-null neutral defaults.  
**Verification:** The ballpark notebook now produces 120 rows for 2023-2026
(30 teams per season); the coverage query for `teams_covered != 30` returns
zero rows.

---

**Date found:** 2026-07-23  
**File(s):** `src/Python/pipeline/training.py`  
**Issue:** Level 3 left joins did not enforce lineup cardinality or complete
park-factor `(season, home_team)` coverage, so future schema/data regressions
could silently fan out rows or create all-null park factors.  
**Evidence:** Code audit found no uniqueness, row-count, or missing-dimension
guards around either join; the integration notebook established the expected
14,124 unique pitcher rows as the invariant.  
**Fix:** Added explicit duplicate-key, join-cardinality, missing-season, and
missing-team-key validation without changing feature selection or values.  
**Verification:** Added focused regression tests and reproduced the frozen
227-feature Mean/Ridge baseline after rebuilding Level 3.

---

**Date found:** 2026-07-23  
**File(s):** `Models/Strikeout-Model/train.py`  
**Issue:** The row-index 70/15/15 split divided games from April 15 and July 6
across adjacent partitions, so the date ranges were not strictly disjoint.  
**Evidence:** Rows immediately before and after both split indices had equal
`game_date` values (30 April 15 rows and 28 July 6 rows).  
**Fix:** Boundary dates are now assigned wholly to the later partition, with
guards for sorted input, insufficient dates, and empty partitions.  
**Verification:** New split tests enforce disjoint date ranges and full row
coverage; corrected Mean/Ridge runs use April 14/15 and July 5/6 boundaries.

---

**Date found:** 2026-07-23  
**File(s):** `src/Python/features.py`, `src/Python/pipeline/games.py`  
**Issue:** Any unknown numeric Level 3 column could become a model feature, and
Level 1 did not recheck local game IDs against the MLB schedule by default.  
**Evidence:** A synthetic same-game `Whiffs` column passed the prior
numeric-only selector; the previously mislabeled 2025 parquet demonstrated why
year/date checks alone are insufficient.  
**Fix:** Added an explicit pregame feature allowlist/pattern gate and mandatory
per-season official game-ID validation in the default Level 1 run.  
**Verification:** Regression tests cover rejection of unapproved numeric
columns and Level 1 schedule validation; all 2023-2025 local files independently
passed official schedule validation.

---

**Date found:** 2026-07-23  
**File(s):** `src/Python/pitcher_rolling.py`,
`src/Python/batter_rolling.py`, `src/Python/pipeline/training.py`  
**Issue:** Completed-season HR/FB entered rolled xFIP, same-date doubleheader
rows could feed one another by `game_pk`, and historical lineup membership
included late substitutes.  
**Evidence:** Code tracing showed xFIP in the default rolling means, rolling
ordered same-day games by ID, and Level 3 averaged every batter-game row.  
**Fix:** Made all player features calendar-date-exclusive, rejected duplicate
rolling keys, and restricted historical lineup membership to the first nine
distinct batters with exact nine-player coverage validation. FIP/xFIP were
rebuilt from summed prior-start counts; xFIP now uses league HR/FB available
before the game date, regressed toward the previous season with a
1,000-fly-ball prior. The 2023 boundary prior is calculated from validated
2022 Statcast (`0.12815157`) under the identical fly-ball definition rather
than an arbitrary constant. Intentional walks and batter-interference PAs were
also corrected in shared event flags.  
**Verification:** Rebuilt Levels 1-3; all 14,124 pitcher rows have nine lineup
members, zero duplicate keys, and zero null park factors. The 89-test suite
passes, including same-date, duplicate-key, and lineup-proxy regressions.

---

**Date found:** 2026-07-23  
**File(s):** `src/Python/pipeline/games.py`,
`src/Python/batter_rolling.py`  
**Issue:** The first model season still had two arbitrary boundaries: every
2023 park factor was neutral `1.0`, and batter shrinkage used a fixed `0.225`
league K-rate fallback.  
**Evidence:** All 30 2023 park rows were exactly neutral. Validated 2022
Statcast produced park factors from `0.84246` to `1.16455` and an exact
league K rate of `0.22381258`.  
**Fix:** Level 1 now uses the prior-only 2022 source for 2023 park history and
stores its league K rate for first-date batter shrinkage. No 2022 rows enter
the model window. Missing unsourced batter priors now remain null.  
**Verification:** Rebuilt Levels 1-3; 2023 park factors are non-neutral, every
first-date shrunk batter K rate equals the sourced 2022 prior, and all 89 tests
pass, including direct prior-only park-history wiring coverage.

## 5. Baseline results

> Record each baseline run here with full config, not just the winning one.
> This becomes the ablation table's anchor rows.

Historical frozen baseline (superseded because boundary dates overlapped):

| Model | Features | Train end | Val end | Test start | Test MAE | Test RMSE | Test R2 |
|---|---|---|---|---|---|---|---|
| Mean | 227 | 2025-04-15 | 2025-07-06 | 2025-07-06 | 0.0857 | 0.1074 | -0.0001 |
| Ridge | 227 | 2025-04-15 | 2025-07-06 | 2025-07-06 | 0.0797 | 0.1002 | 0.1290 |

Current 2023-2024-only, date-disjoint baseline after deterministic pruning:

| Model | Features | Train end | Val start | Val end | Test start | Test MAE | Test RMSE | Test R2 |
|---|---|---|---|---|---|---|---|---|
| Mean | 248 | 2024-06-08 | 2024-06-09 | 2024-08-05 | 2024-08-06 | 0.0854 | 0.1070 | -0.0010 |
| Ridge | 248 | 2024-06-08 | 2024-06-09 | 2024-08-05 | 2024-08-06 | 0.0788 | 0.0993 | 0.1378 |
| LightGBM | 248 | 2024-06-08 | 2024-06-09 | 2024-08-05 | 2024-08-06 | 0.0783 | 0.0983 | 0.1546 |

The superseded run previously labeled “final audit-corrected” trained through
2025-04-14, validated through 2025-07-05, and tested from 2025-07-06. Its
Mean/Ridge/LightGBM test RMSE values were 0.1076/0.1003/0.0994 and R² values
were -0.0001/0.1313/0.1459. It is retained in the experiment count because
early 2025 entered fitting and later 2025 was consulted; it is not a holdout
result.

> Add rows as new models or feature-pruned variants are run.
> Historical frozen snapshot location:
> `docs/archive/leaky-baseline-2026-07-23/`. It is retained for process
> history only and must not be cited as current performance.
> The current LightGBM artifact was created at `2026-07-24 16:52:15 UTC`:
> `artifacts/models/lightgbm_krate_20260724_165215.txt` (SHA-256
> `0d428a6cc0284881d99af226204666271005d9bd51f968d575cb429ddb2d28a8`)
> with evaluation metadata in the matching JSON (SHA-256
> `79b00d4098937eab769f0023d4c82a065cc1192d0cbb16323630a4144fac3036`).
> The fit contains only 2023-2024 rows. The previously consulted 2025 results
> remain historical evidence and were not read by this corrected run.

## 6. Ablation plan

> Design ablations around feature GROUPS, not individual columns, to tell
> a clean story. Fill in results as each ablation is run.

### Nested selection protocol

The reused `2023_h2` / `2024_h1` / `2024_h2` screen is retired. Feature-family
and window configurations are now selected by mean MAE on two inner,
chronological folds contained wholly within each outer training period. The
selected configuration is then refit on all outer-train rows and evaluated
once on that outer confirmation period. No outer row participates in its own
selection.

Outer confirmations are 2024 H1 after training on 2023 and 2024 H2 after
training through 2024 H1. Exact boundaries and inner selections are stored in
`candidate_ablation_metadata.json`, `window_ablation_metadata.json`, and the
matching `*_inner_selection.csv` files under
`artifacts/feature_research/`. `_research_folds` was removed and
`tests/test_nested_cv.py` enforces containment and date disjointness.

The nested rerun selected different feature/window configurations by outer
fold and model. All four feature-family selections beat their outer core MAE,
by `0.000291` to `0.000733`; all four window selections also improved outer
MAE, by approximately `0.000001` to `0.000386`. These are honest outer
confirmation results, but the changing selections are evidence against calling
one current configuration universally stable.

| Feature group removed | Test MAE | Test RMSE | Test R2 | Delta vs full |
|---|---|---|---|---|
| None (full model) | | | | -- |
| - Park factors | | | | |
| - Opponent lineup features | | | | |
| - Season-to-date (keep rolling only) | | | | |
| - Rolling windows (keep season-to-date only) | | | | |
| - Pitch-arsenal physics (velo/spin/movement) | | | | |

## 7. Feature redundancy audit

> Document findings from the correlation check on the frozen 227-feature set
> and the current 232-feature candidate set --
> which near-duplicate columns exist (e.g. k_rate_P5 vs P10 vs P20,
> k_rate_std vs k_rate_std_shrunk) and what was pruned, if anything.

### Reproducible phase-1 diagnostics

`scripts/feature_diagnostics.py` runs only on the 6,557-row chronological
training partition ending 2024-06-08. `src/Python/features.py` now excludes all
rolling `contact_rate` and `csw_rate` variants, retaining Whiff%, SwStr%, and
called-strike rate. The resulting 248-feature design is full rank.

Artifacts under `artifacts/feature_research/` include:

- `feature_missingness.csv` and `dispersion_ratios.csv`;
- full Pearson, targeted Spearman, and narrow tied-pair Kendall matrices plus
  flagged-pair tables, all using `|correlation| > 0.80`;
- `vif.csv`, `usage_composition_rank_audit.csv`, and
  `feature_dictionary.csv`;
- `feature_diagnostics_metadata.json`, which records the split and method.

The reduced design has 242 features above VIF 5 and 236 above VIF 10, so exact
identity removal fixed rank deficiency but did not solve the broader
multicollinearity problem. The eight retained pitch-type usage shares are full
rank and do not sum exactly to one because the taxonomy does not exhaust all
pitches, but 82.2%-96.3% of complete rows are within one percentage point of
one; they remain a near-compositional VIF concern.

The old dispersion claim does **not** reproduce under the required corrected
training-only scope. With documented PA bins `(8,12]`, `(12,16]`, `(16,20]`,
`(20,24]`, `(24,28]`, and `(28,∞]`, count-variance ratios range
`1.259-1.502` and K/PA-variance ratios range `1.273-1.496`. The prior
`1.38-1.53` / `1.35-1.52` ranges used 2023-2025 and did not document bin
edges; they are retained only as a superseded, non-reproducible scope.

### Phase-2 VIF cluster proposal

`scripts/vif_cluster_reduction.py` groups the 236 Phase-1 features above VIF 10
using the saved Pearson-linked clusters and chooses one representative from
each of 62 clusters. Selection priority is enforced in order: documented
stabilization/reliability, then lower training-split missingness, then the
simpler definition. Every decision and rationale is recorded in
`artifacts/feature_research/vif_cluster_selection.csv`.

The proposal retains 62 representatives plus 12 unclustered features, reducing
248 eligible features to 74. Recomputed VIF has median `3.214`, maximum
`16.432`, and two values above 10 (`xwOBA_P5` and `xFIP_P5`). This is a
meaningful cluster reduction, not a claim that all collinearity disappeared.
No further mechanical pruning is required merely to force VIF below 10:
overlapping rolling windows are correlated by design, and multicollinearity is
not a LightGBM predictive-performance pruning rule, although it remains
important for Ridge interpretation and stable attribution. The proposal has
not been wired into `train.py` or frozen as the registry.

### Expanded candidate research (2026-07-24)

The Level 1/2 pipeline now computes leakage-safe research candidates for prior-
two-start arsenal presence and pitch-weighted usage, BIP%, BABIP, first-pitch
strike%, ahead/behind count shares, two-strike reach, put-away%, arm angle,
fixed-formula MLB SIERA, and pitcher run-expectancy value. Conventional
Strike% is retained only as an auditable Level 1 metric and rejected from the
model because it is exactly `1 - Ball%`; neutral count share is the omitted
reference because ahead + neutral + behind = 1. WPA is rejected as leverage
context rather than pitcher strikeout skill.

All new artifacts are versioned under
`artifacts/feature_research/expanded/` and
`artifacts/stabilization/expanded/`. On the 6,557-row training partition, the
expanded 301-feature research design is full rank but has 282 VIF values above
10. The Ridge proposal reduces it to 81 features, median VIF `3.098`, maximum
`12.618`, with one value above 10.

At the `r=.50` reliability gate, BIP%, behind-count share, two-strike reach,
put-away%, and arm angle clear the lower-bootstrap-CI rule. BABIP, first-pitch
strike%, ahead-count share, overall run value, every pitcher pitch-type run-
value series, and every batter pitch-type/coarse-family run-value series do
not. Arm angle is the strongest measurement-stability result (`100` pitches;
about `1.1` starts), but repeatability alone is not predictive evidence.

Nested selection did not choose any expanded family in any outer-fold/model
selection. LightGBM selected `preferred_raw` then `batter_whiff`; Ridge selected
`compact_candidate` then `revised_compact`. Window selections likewise stayed
with existing discipline configurations. Therefore all 53 expanded columns
remain research-only and the production LightGBM registry stays at the 248
audit-corrected baseline features. The decision table is
`artifacts/feature_research/expanded/candidate_feature_registry.csv`; final
LightGBM and Ridge lists are `final_lightgbm_registry.csv` and
`final_ridge_registry.csv`.

#### Phase 3 follow-up and refreshed diagnostics

Phase 3 added 16 opposing-lineup batter-discipline candidates (Z-Swing%,
Swing%, Z-Contact%, and BB%; season-to-date plus P5/P10/P20) without promoting
them through the production gate. At that checkpoint the research design was
317 features: 248 production-baseline columns plus 69 research-only candidates.
The refreshed 6,557-row training-only diagnostic was full rank, with 291 VIF
values above 10, and yielded a separate 90-feature Ridge interpretation
proposal (median VIF `3.223`, maximum `12.640`, one value above 10).
That checkpoint's `pitcher_training.parquet` SHA-256 was
`f2f061489b098319e6eb3e531374be398a3f8d9dc4265f3ecf189c842ae5b3b6`;
the earlier `41d1d1b9...` hash remains attached only to the corrected-frame
ablation checkpoint that preceded the batter-discipline columns.

The stabilization-nominated batter family is lineup Z-Swing% P10, Swing% P10,
Z-Contact% P20, and BB% season-to-date. It improved LightGBM outer-fold MAE by
`0.000962` and `0.000743`; Ridge selected core in H1 and the family in H2.
This is positive LightGBM development evidence, but the 16 generated columns
remain research-only because explicit registry freeze was outside Phase 3.

The rolling-window follow-up tested only BABIP P20/P30/P35, arm angle P2/P3,
and run value P10/P20/P25. No global rolling default changed. Run-value P25 is
a LightGBM-specific proposal; BABIP, arm angle, Ridge run value, and unstudied
physics/usage windows remain provisional.

#### Hitter quality and lineup-construction follow-up

The batter game table now retains denominator pairs for BABIP, hard-hit%,
barrel%, sweet-spot%, average exit velocity/launch angle, xBA, wOBA, xwOBA,
HR%, FB%, HR/FB, pulled-air balls per BIP, and batter run value per pitch.
Every available metric receives leakage-safe season-to-date and P5/P10/P20
histories before lineup aggregation. The richer batter-by-pitch-type research
table has 416,999 batter/game/pitch-type rows and 37 columns; it is not joined
to the model because the earlier pitch-type run-value reliability gate failed.

Lineup construction now retains the flat mean and adds prior-date
batting-order-opportunity weighted means and weighted standard deviations.
The final prior-date weights are approximately 4.50 PA for lineup slot 1 and
3.47 for slot 9. Current-game realized PA is never used. Pulled-air rate is the
project's transparent definition: pulled Statcast fly balls or line drives per
BIP using batter hand and field-center x-coordinate 125.42.

At the lower-bootstrap-CI `r=.50` gate, hard-hit%, barrel%, average exit
velocity, average launch angle, xBA, xwOBA, HR%, FB%, HR/FB, and pulled-air
rate were reliably estimable. BABIP, sweet-spot%, wOBA, and run value per pitch
were not. The nested ablation therefore tested one stabilization-nominated
representation for only those ten metrics across four predeclared
configurations: core, flat, order weighted, and weighted plus dispersion.

Weighted plus dispersion won every inner selection. LightGBM outer-fold MAE
improved by `0.000360` and `0.000152`; Ridge MAE worsened by `0.000209` and
`0.000200`. No feature was promoted. The production gate remains 248 while the
research surface is 563 features (315 research-only). The refreshed Ridge VIF
proposal has 165 features, median VIF `4.263`, maximum `14.618`, and four
values above 10. Current `pitcher_training.parquet` SHA-256:
`20eaaca766a2a24fa8e0db5741c6ae039478476139d42c2b5c1bbd7e609e657e`.

#### Feature-count reconciliation and coverage inventory

The apparent 301-row `feature_dictionary.csv` versus 317 model-feature
discrepancy compared two different research checkpoints, not two views of the
same frame. The 301-row dictionary described the expanded pitcher design
before the 16 opposing-lineup discipline columns were materialized. Adding
season-to-date plus P5/P10/P20 for Z-Swing%, Swing%, Z-Contact%, and BB%
produced the 317-feature checkpoint. The later hitter-quality and lineup
construction work added the contact-quality, order-weighted, and weighted-SD
research variants. The current expanded dictionary and missingness files each
cover all 563 current research features: 248 production-baseline columns plus
315 research-only columns. The older 301 and 317 figures remain useful dated
checkpoints, but neither is the current model-input inventory.

`artifacts/feature_research/feature_coverage_matrix.csv` is the cross-level
inventory. Its 117 conceptual rows map every one of the 563 Level 3 features
exactly once through `level3_columns` and `level3_feature_count`. It also keeps
separate batter-source rows and 31 documented omission/rejection rows so that
Level 1/2 metrics do not disappear merely because they are not direct pitcher
training columns. The matrix is generated by
`scripts/feature_coverage_matrix.py`, which fails if the current dictionary is
not a 563-feature one-to-one accounting.

#### Research parking lot

These items are intentionally recorded without changing the feature pipeline:

- complete the rolling-window decision for provisional pitcher physics,
  mechanics, usage, BABIP, arm angle, and run-value representations;
- test season-to-date FIP and leakage-safe xFIP only as predeclared
  replacements, alongside the existing rolling composites;
- decide whether batter Zone%, O-Contact%, called-strike%, HBP%, hit rate, and
  BIP% merit stabilization screening; retain Contact% and CSW% as rejected
  deterministic representations;
- leave batter pitch-type matchup features outside Level 3 until a reliability
  design supports more than the failed run-value screen;
- consider pitcher-hand batter discipline splits only after the unsplit family
  is resolved;
- consider robust lineup dispersion/threat summaries only as a capped
  alternative to the existing weighted SD, not an open-ended operator search;
- correct neutral-site/international venue handling in the park-factor key;
- retain the VIF tie-breaker relabeling task for after this inventory.

### Denominator-aware stabilization findings

Development data are restricted to 2023-2024. Pitchers use the locked
`PA >= 9` research cohort; batter histories use all Level 1 batter games.
Curves use consecutive denominator buckets and 300 player-level bootstrap
resamples. A threshold is called reliably estimable only when the lower 95%
pointwise CI crosses it with at least 50 qualified players. Generated curves,
CI files, and plots are under `artifacts/stabilization/`.

Pitcher findings:

- K/PA: `r=.50` at 100 PA (CI crossings 75-125; 257 pitchers), approximately
  4.3 starts. `r=.70` median crossing is 325 PA (~14.1 starts), but the lower
  CI never crosses. Candidate: one ~5-start signal plus season-to-date.
- Whiffs/swings: `r=.50` at 200 swings (150-250; 252 pitchers), ~4.8 starts;
  `r=.70` at 550 swings (350-750; 145 pitchers), ~13.1 starts. Candidate:
  short ~5 starts and long ~13-18 starts.
- Whiffs/pitches (SwStr%): `r=.50` at 300 pitches (200-500; 282 pitchers),
  ~3.3 starts; `r=.70` at 900 pitches (600-1,500; 178 pitchers), ~10 starts.
  This is the leading pitcher whiff-skill candidate for K/PA prediction.
- Balls/pitches (Ball%): `r=.50` at 300 pitches (200-600; 282 pitchers),
  ~3.3 starts. The median `r=.70` crossing at 1,800 pitches is not reliable.
  Keep as a candidate for command and workload effects, not as a proven direct
  K-rate feature.
- Chases/out-of-zone pitches: median `r=.50` is 700 (~15.6 starts), but its
  lower-CI crossing occurs only at 1,450 with 15 qualified pitchers. Neither
  threshold is reliable. Prefer season-to-date pending predictive validation.
- CSW/pitches: `r=.50` at 800 pitches (300-1,400; 187 pitchers), ~8.9 starts;
  `r=.70` is not reached. Candidate: ~10-15 starts plus season-to-date.
- BB/PA: median `r=.50` is 250 PA (~10.9 starts), but the lower CI never
  crosses either threshold. Treat as noisy; prefer a long/shrunk estimate.
- GB/BIP: `r=.50` at 75 BIP (50-100; 253 pitchers), ~4.7 starts; `r=.70` at
  150 BIP (125-350; 181 pitchers), ~9.4 starts. Stable enough to test, but its
  direct value for K/PA is uncertain and should be established by ablation.
- HR/fly balls: neither median threshold is reached. Do not create an
  unshrunk individual HR/FB rolling feature; retain the regressed league
  HR/FB treatment used by xFIP.

Batter findings:

- K/PA: `r=.50` at 75 PA (50-100; 526 batters), ~18.8 games; `r=.70` at
  175 PA (100-225; 408 batters), ~43.8 games. Candidate: ~20 games plus a
  shrunk season-to-date estimate.
- Whiffs/swings: `r=.50` at 100 swings (50-100; 561 batters), ~14.3 games;
  `r=.70` at 150 swings (150-250; 515 batters), ~21.4 games.
- Whiffs/pitches (SwStr%): `r=.50` at 200 pitches (100-200; 564 batters),
  ~13.3 games; `r=.70` at 300 pitches (300-400; 520 batters), ~20 games.
- Chases/out-of-zone pitches: `r=.50` at 100 (50-100; 562 batters), ~14.3
  games; `r=.70` at 200 (150-250; 473 batters), ~28.6 games.

No rolling constants change from this analysis alone. The next step is a
within-family redundancy audit and chronological 2023-to-2024 predictive
comparison of the small candidate window sets. Naming is now consistent:
`whiff_rate = Whiffs/Swings` and `swstr_rate = Whiffs/Pitches` for both
pitchers and batters. Level 3 exposes distinct `opp_lineup_whiff` and
`opp_lineup_swstr` candidates. `opp_lineup_whiff` is in the frozen 227-feature
baseline; `opp_lineup_swstr` belongs to the later research candidate frame and
is not in that frozen registry.

JA ERA is not added as a feature because its exact published coefficients were
not supplied and it estimates run prevention rather than K/PA. Its available
components are represented separately: pitcher SwStr%, Ball%, and GB%. Raw
components let the model test incremental value without importing a redundant
ERA-scale composite. The planned ablation should compare both/all/none within
the pitcher whiff family and batter lineup whiff family, then test Ball% and
GB% individually.

### Pitch-type research and denominator corrections

The Level 1 build now writes `pitch_type_games.parquet`: 67,653 rows at one
starter/game/canonical-pitch-type grain for FF, SI, FC, SL, ST, CU, CH, and FS.
It retains the numerator/denominator pairs needed for honest aggregation.
`Strikes`, `Balls`, and `BIP` are mutually exclusive and sum to `Pitches` in
every row; a ball put into play is never included in a strike numerator.
Contact-quality values are restricted to `type == "X"` so exit velocity on
fouls cannot contaminate BIP quality.

The overall xBA, wOBA, and xwOBA rolling features were also corrected. They are
now `sum(numerator) / sum(denominator)` over prior starts, not unweighted means
of per-start rates. Splitter (`fs_*`) physics, movement, usage, and handedness
features now propagate through Level 2 and Level 3.

Pooled 2023-2024 descriptions support the baseball intuition but do not by
themselves justify model inclusion:

- Whiffs/swings were highest for SL (.326), FS (.322), ST (.313), CU (.311),
  and CH (.307), versus FF (.212), FC (.224), and SI (.128).
- Whiffs/pitches were highest for FS (.169), SL (.159), and CH (.155).
- GB/BIP was highest for FS (.543), SI (.533), and CH (.501).
- Weak-contact differences were small: CH (.0477), FC (.0467), ST (.0460),
  SI (.0456), and FS (.0446). These are descriptive pooled rates, not
  pitcher-skill reliability estimates.

Pitch-type split-half curves use each statistic's actual denominator. At
`r=.50`, only these lower-CI crossings retained at least 50 qualified pitchers:
FF Whiff% (175 swings), FF SwStr% (250 pitches), FF Ball% (450 pitches), FF
CSW% (550 pitches), FF GB% (100 BIP), SL Whiff% (150 swings), SL SwStr% (200
pitches), CH SwStr% (150 pitches), CH Ball% (250 pitches), and CH Chase% (125
out-of-zone pitches). No pitch-type weak-contact, hard-hit, barrel, xBA, wOBA,
or xwOBA estimate met that criterion. These noisy contact outcomes should be
shrunk heavily or omitted, not added as raw rolling rates.

Outputs are under `artifacts/stabilization/pitch_type/`; the reusable runner is
`Models/Strikeout-Model/Strikeout-EDA/run_pitch_type_stabilization.py`.

### Crucial analysis still required before registry freeze

1. **Separate strikeout skill from workload.** K/PA does not produce a
   strikeout-count prop by itself. Build and validate a pregame batters-faced
   or outs/pitches workload model, then combine exposure with K/PA (or compare
   with a count model using exposure/offset).
2. **Measure population-selection bias.** `PA >= 9` intentionally removes
   openers and very early exits, but an in-game injury is unknowable pregame.
   Report model coverage and evaluate the conditional "normal starter"
   estimand separately from all announced starters.
3. **Audit missingness and cold starts.** Quantify coverage by season, player,
   pitch type, and feature. Debuts and new pitch types need explicit
   prior-season/league fallback and missingness indicators; minor-league data
   remain out of scope.
4. **Validate production lineup construction.** Collect the ID-resolved daily
   adapter outputs and compare the retrospective first-nine-batters proxy with
   projected/confirmed lineups, including late scratches and handedness
   changes.
5. **Test drift and interactions.** Check 2023-to-2024 feature/target drift and
   test pitch-type skill only as leakage-safe prior-game rolls, ideally
   interacted with opponent lineup handedness and pitch-type vulnerability.
6. **Repeat grouped redundancy/ablation after these corrections.** Existing
   ablation numbers predate denominator-weighted expected stats and splitter
   propagation. Do not freeze pitch-type features from descriptive rankings or
   stabilization alone.
7. **Evaluate the final betting target.** Do not use the previously scored
   `2025-07-06+` benchmark for additional feature decisions. On development
   folds compare count MAE/RMSE, calibration, and probabilities above/below
   prop lines, not only K/PA R2; reserve genuinely future post-freeze games for
   the next pristine test.

### Corrected-frame protected feature-family ablation

The pipeline and ablations were rerun on 2026-07-24 after the
denominator-weighted expected-stat and splitter (`fs_*`) corrections. The
rebuilt pitcher frame has 14,124 rows and SHA-256
`41d1d1b9602b509bc183e3f03bedad13cc2b3a8eb7cb557607d712acfe5a9ee0`.
Three expanding, date-disjoint folds remain entirely within 2023-2024; the
2025 rows were filtered out before any fit, score, or feature decision. The
corrected frame has a 238-feature core, a 243-feature original compact
candidate, a 251-feature preferred-raw candidate, and 256 features with every
screened candidate.

- Opponent-lineup Whiff% + SwStr% is the strongest robust family. Its
  240-feature configuration improved MAE in all three folds for both models:
  LightGBM by `0.000554` with `0.01145` R2 improvement and Ridge by
  `0.000343` with `0.00701` R2 improvement.
- Pitcher Whiff% improved LightGBM MAE in all three folds (`0.000218`) but
  slightly hurt Ridge (`-0.000019`). Pitcher GB% likewise helped LightGBM in
  all folds (`0.000266`) but clearly hurt Ridge (`-0.000216`). Neither is a
  model-agnostic registry choice.
- Adding every candidate improved LightGBM MAE in only one fold and Ridge in
  two, with worse mean Ridge RMSE and R2. The broad 251-feature preferred-raw
  set was similarly inconsistent.
- The corrected window screen favors Ball% P5 (`0.000372` LightGBM MAE
  improvement, 3/3 folds) and SwStr% P20 (`0.000290`, 3/3 folds). Their Ridge
  improvements were positive but tiny and occurred in two folds. No Whiff%
  window improved all three LightGBM folds.
- A targeted 242-feature revised compact set added lineup Whiff%/SwStr%,
  pitcher Ball% P5, and pitcher SwStr% P20. It improved Ridge MAE in all folds
  (`0.000361`) but LightGBM in only two (`0.000487`) and did not beat the
  simpler lineup-only configuration for LightGBM.

The leading screened development configuration is therefore the 238-feature
core plus both opponent-lineup discipline rates (240 features). It is not a
frozen registry; that historical screen contained as many as 256 eligible
features. The current safety gate now admits only the 248 production-baseline
features by default, while 69 candidates require explicit research opt-in.
Pitcher Ball% P5 and SwStr% P20 remain model-specific challengers, not default
registry members. This decision used no 2025 result.

## 8. Error analysis

> Break down errors by dimension, not just aggregate metrics. Suggested cuts:
> - By month (early season / high variance vs. late season / stabilized)
> - By pitcher role or usage pattern
> - Specifically: Tampa Bay games pre- vs. post-venue-fix, as a natural
>   experiment demonstrating the bug fix mattered empirically, not just
>   theoretically

## 9. Calibration

> If probabilities/rates are used downstream for props, check whether
> predicted rates are calibrated (binned reliability check), not just
> accurate on average.

## 10. Limitations and threats to validity

> Write honestly. Known items already identified:
> - Small-sample PA noise inherent to per-game strikeout rate as a target
> - Neutral-site/international games (Mexico City, Seoul, London series)
>   not filtered from park factor computation -- documented but unaddressed
> - Opponent lineup features use the first nine distinct batters by first PA
>   as an approximation for the announced lineup
> - Team-composition bias in the basic venue-rate park factor method
>   (home team's own hitters/pitchers overrepresented at their park)

## 11. Reproducibility

> Fill in once frozen. Should be copy-paste runnable by a reader.

- Historical baseline commit:
  `2e7f83c24a6cb330d11f6e94a68315fce8b3272b` (see
  `docs/archive/leaky-baseline-2026-07-23/GIT_STATE.txt`; corrected artifact
  identity is established by the hashes above)
- Command sequence:
  `python -m Python.pipeline.games`,
  `python -m Python.pipeline.rolling`,
  `python -m Python.pipeline.training`,
  `python Models/Strikeout-Model/Strikeout-EDA/run_pitch_type_stabilization.py`
- Test suite: `python -m pytest` (129 tests, all passing as of 2026-07-24)
- Model training:
  `python Models/Strikeout-Model/train.py --model [mean|ridge|...]`

## 12. Required sequencing before the batters-faced (TBF) model

1. Complete a feature dictionary with missingness rates and correlation
   clusters by family.
2. Remove deterministic redundant features, including exact complements and
   algebraically derivable sums.
3. Run grouped ablations across every major family: rates, pitch physics,
   usage, mechanics, FIP/xFIP, lineup, park, and context.
4. Select one or at most a small number of windows per statistic using
   stabilization to nominate candidates and predictive validation to choose
   among them.
5. Compare ordinary unweighted K/PA regression with PA-weighted, binomial, and
   beta-binomial modeling.
6. Validate the complete selection procedure with nested chronological folds:
   inner folds for feature/window/hyperparameter selection and outer folds for
   confirmation.
7. Freeze an explicit compact feature registry with a documented missingness
   and cold-start policy.
8. Only then perform a protected evaluation. The historical
   `2025-07-06+` partition has already been scored by baseline runs and is not
   pristine; the next honest final test must use future post-freeze games.

Do not skip ahead to TBF or count-probability implementation until this
sequence is complete and documented. The detailed status and fold proposal are
in `docs/statistical_audit_and_sequencing_report.md`.

## 13. Strikeout-count probability modeling (planned, not yet built)

Candidate conditional count models are:

- beta-binomial regression with strikeouts as successes and PA/TBF as trials;
- negative-binomial regression with a log projected-TBF offset;
- Poisson regression with the same offset as a transparent baseline.

Beta-binomial is the leading conceptual candidate because it may solve both
the heteroskedastic K/PA problem and the conditional strikeout-count
probability problem in one likelihood. It must be compared with simpler
weighted/binomial baselines before implementation is finalized.

Actual same-game TBF is never a prediction-time input. Historical PA can be
part of the response likelihood and remain an evaluation oracle, while all
deployed and end-to-end backtest probabilities must condition on cross-fitted
or genuinely pregame projected TBF. Full uncertainty should eventually mix the
conditional strikeout distribution over the projected-TBF distribution.
