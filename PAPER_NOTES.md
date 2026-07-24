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
  currently provides a validated season download, but no automated daily job.
- Level 1: pitcher_games, batter_games, park_factors
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
- Automated test suite: 96 tests across test_ballpark.py, test_batter_features.py,
  test_batter_rolling.py, test_feature_safety.py, test_identity.py,
  test_pipeline.py, test_pitcher_features.py, test_pitcher_rolling.py,
  test_reliability.py, test_stabilization.py, test_statcast.py

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

Final audit-corrected, date-disjoint baseline:

| Model | Features | Train end | Val start | Val end | Test start | Test MAE | Test RMSE | Test R2 |
|---|---|---|---|---|---|---|---|---|
| Mean | 227 | 2025-04-14 | 2025-04-15 | 2025-07-05 | 2025-07-06 | 0.0859 | 0.1076 | -0.0001 |
| Ridge | 227 | 2025-04-14 | 2025-04-15 | 2025-07-05 | 2025-07-06 | 0.0797 | 0.1003 | 0.1313 |
| LightGBM | 227 | 2025-04-14 | 2025-04-15 | 2025-07-05 | 2025-07-06 | 0.0786 | 0.0994 | 0.1459 |

> Add rows as new models are run (LightGBM, XGBoost, feature-pruned variants).
> Historical frozen snapshot location:
> `Models/Strikeout-Model/results/_baseline_2026-07-23/`.
> The fitted LightGBM model and its complete feature/evaluation JSON are in
> `artifacts/models/lightgbm_krate_20260723_202255.*`.
> Final SHA-256: pitcher training
> `ba27a66c90335de113232308de9364ae22769f61ce3cbd36f9fe2294f024f3d9`,
> batter training
> `45809e8f3dc727de427ac479206105c0f1480455b50c22ba959f4e90bc199cda`,
> ordered feature list
> `df924cf1d06108ff7e34d3e50e5a97472fbc44ac886de6f18acc8d19578d6c30`.
> Git commit hash at time of this run:
> `2e7f83c24a6cb330d11f6e94a68315fce8b3272b` (dirty working tree; exact source
> snapshot and status are stored with the frozen artifacts).

## 6. Ablation plan

> Design ablations around feature GROUPS, not individual columns, to tell
> a clean story. Fill in results as each ablation is run.

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
`opp_lineup_swstr` candidates; neither is frozen into the final registry.

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
4. **Validate production lineup construction.** Compare the retrospective
   first-nine-batters proxy with scraped announced lineups, including late
   scratches and handedness changes.
5. **Test drift and interactions.** Check 2023-to-2024 feature/target drift and
   test pitch-type skill only as leakage-safe prior-game rolls, ideally
   interacted with opponent lineup handedness and pitch-type vulnerability.
6. **Repeat grouped redundancy/ablation after these corrections.** Existing
   ablation numbers predate denominator-weighted expected stats and splitter
   propagation. Do not freeze pitch-type features from descriptive rankings or
   stabilization alone.
7. **Evaluate the final betting target.** Preserve the untouched 2025 holdout;
   on development folds compare count MAE/RMSE, calibration, and probabilities
   above/below prop lines, not only K/PA R2.

### Protected feature-family ablation

A fixed Ridge and LightGBM screen used three expanding, date-disjoint folds
contained entirely within 2023-2024. The 2025 holdout was not read. Every
configuration used the same 214-feature core; reported improvements are mean
validation deltas against that core. Outputs and split metadata are under
`artifacts/feature_research/`.

- Batter lineup Whiff% + SwStr% was the only family that improved MAE in all
  three folds for both models: LightGBM improved by `0.000527` MAE and `0.0106`
  R2; Ridge improved by `0.000302` MAE and `0.0066` R2. Retain both as
  candidates for now.
- Pitcher Whiff% + SwStr% improved LightGBM in all folds (`0.000341` mean MAE)
  but slightly hurt Ridge (`-0.000042`). Their incremental value appears
  nonlinear; do not force both into a linear model.
- Pitcher Ball% improved LightGBM in all folds (`0.000352` mean MAE) and was
  effectively neutral in Ridge (`-0.000014`). Keep it as a candidate.
- Pitcher GB% improved LightGBM in two of three folds but hurt Ridge in every
  fold (`-0.000400` mean MAE). Exclude it from the leading K/PA registry for
  now; retain it for run-prevention/workload research.
- Adding all candidates was worse than selective subsets and improved
  LightGBM MAE in only two folds. This rejects an indiscriminate
  "include everything" approach.

Redundancy remains substantial: P10 versus P20 correlations are approximately
`0.96` within Whiff%, SwStr%, Ball%, and GB%; pitcher Whiff% versus SwStr% is
approximately `0.94` at matched windows; batter lineup Whiff% versus SwStr% is
`0.925`.

The follow-up window screen found that average improvement alone overstated
short-window value because the 2023 second-half fold drove most P5 gains.
Pitcher Whiff% + SwStr% at P20 was the only tested whiff combination that
improved LightGBM in all three folds and improved Ridge in two. SwStr% P20 was
the strongest Ridge discipline window. Ball% P20 improved Ridge in all three
folds and LightGBM in two, while Ball% P5 improved LightGBM in only one.

The provisional compact candidate set is therefore pitcher Whiff% P20,
pitcher SwStr% P20, pitcher Ball% P20, and both season-to-date batter lineup
rates. P5 may remain a nonlinear recent-form challenger, but P10/P20/STD
duplicates should not all survive the registry freeze. This remains a
development-data decision; no 2025 result has been consulted.

That five-feature compact addition was then tested as one configuration. It
improved MAE in all three folds for both models: LightGBM by `0.000436` with
`0.0078` R2 improvement, and Ridge by `0.000370` with `0.0081` R2 improvement.
At 219 total features it was more consistent than the indiscriminate
232-feature set, which improved LightGBM in only two folds and hurt Ridge.
This is now the leading registry candidate, not a frozen final registry.

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

- Git commit: `2e7f83c24a6cb330d11f6e94a68315fce8b3272b`
  (dirty working tree; see baseline `GIT_STATE.txt` and hashes above)
- Command sequence:
  `python -m Python.pipeline.games`,
  `python -m Python.pipeline.rolling`,
  `python -m Python.pipeline.training`,
  `python Models/Strikeout-Model/Strikeout-EDA/run_pitch_type_stabilization.py`
- Test suite: `python -m pytest` (100 tests, all passing as of 2026-07-23)
- Model training:
  `python Models/Strikeout-Model/train.py --model [mean|ridge|...]`
