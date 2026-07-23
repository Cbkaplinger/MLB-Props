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
- Automated test suite: 84 tests across test_ballpark.py, test_batter_features.py,
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

> Document findings from the correlation check on the 227-feature set --
> which near-duplicate columns exist (e.g. k_rate_P5 vs P10 vs P20,
> k_rate_std vs k_rate_std_shrunk) and what was pruned, if anything.

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
  `python -m Python.pipeline.training`
- Test suite: `python -m pytest` (89 tests, all passing as of 2026-07-23)
- Model training:
  `python Models/Strikeout-Model/train.py --model [mean|ridge|...]`
