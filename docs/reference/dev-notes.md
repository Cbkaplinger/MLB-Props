# Feature pipeline reference

This is the current implementation reference for the MLB pitcher strikeout
project. Historical notebook scores and the former Longleaf workflow were
removed because they were produced before the leakage-safe pipeline and are not
valid evidence of current model quality.

Visual phase diagrams (architecture, leakage, modeling status, roadmap) live
under `docs/diagrams/`. Prefer those over ad-hoc flowchart exports.

Pipeline companion notebooks live under `src/Notebooks/` (including
`pipeline/training.ipynb`). PDF exports are optional and regenerable with
`scripts/export-notebook.ps1` / `scripts/export_notebook.py`; they are not
provenance artifacts.

Generated `artifacts/feature_research/*/SUMMARY.md` wrappers were retired on
2026-07-28. Conclusions live in the matching `docs/step*_findings.md`; keep
the numeric CSV/JSON evidence folders, not the duplicate markdown summaries.

## Objective and leakage boundary

The pitcher model predicts a starter's game-level strikeout rate:

```text
k_rate = strikeouts / batters faced
```

Every feature must be known before first pitch. Same-game `K`, `PA`, and `Outs`
remain in the final frame only as labels/evaluation fields and must be excluded
from model inputs. All player-form features lag the current game.

## Three data levels

Paths are defined in `src/Python/config.py` and default to
`data/processed/`.

| Level | Builder | Pitcher artifact | Batter artifact |
|---|---|---|---|
| 1: game | `pipeline/games.py` | `pitcher_games.parquet` | `batter_games.parquet` |
| 2: rolling | `pipeline/rolling.py` | `pitcher_rolling.parquet` | `batter_rolling.parquet` |
| 3: training | `pipeline/training.py` | `pitcher_training.parquet` | `batter_training.parquet` |

Level 1 also writes `pitch_type_games.parquet` at
starter/game/canonical-pitch-type grain for denominator-aware pitch-type
research.

Run all stages:

```powershell
python -c "from Python.pipeline import run_all; run_all()"
```

The default pipeline source window is `PIPELINE_SEASONS = (2023, 2024, 2025)`
so Level 3 retains the historical holdout and park factors extend through
2026. Model fitting independently filters to
`TRAIN_SEASONS = (2023, 2024)` before splitting.

Or run `python -m Python.pipeline.games`, `.rolling`, and `.training`
individually.

### Level 1: Savant to game tables

`statcast.py` loads regular-season parquet exports and defines shared event,
wOBA/xwOBA, and plate-discipline primitives. Level 1 verifies every requested
season's local game IDs against MLB's official regular-season schedule before
building outputs; `verify_schedule=False` is an explicit offline-only escape
hatch. It also loads the immediately preceding season as prior-only HR/FB
context. Thus a 2023-2025 build uses 2022 Statcast for the early-2023 xFIP
prior without creating 2022 model rows.

`pitcher_features.py` produces one row per true starter/game:

- default minimum of nine batters faced removes openers and very early exits;
- foul tips count as whiffs;
- fly balls include Statcast `fly_ball` and `popup`;
- wOBA/xwOBA use Savant's `woba_value`, `woba_denom`, and
  `estimated_woba_using_speedangle`;
- outs include batting, caught-stealing, and pickoff outs;
- FIP uses published FanGraphs season constants; xFIP uses league HR/FB
  available before each game date, regressed toward the previous season;
- pitch-type physics, usage by batter hand, wOBA/xwOBA, extension, mean release
  point, and release-point standard deviation are retained.

`batter_features.py` produces one row per batter/game with overall outcomes,
vs-LHP/vs-RHP strikeout counts, discipline counts/rates, Savant wOBA/xwOBA, and
the static game context (`game_date`, home/away teams, batting/opponent team,
home flag, batter hand).

### Level 2: game tables to pregame player form

`pitcher_rolling.py` creates lagged, denominator-weighted rates and rolling means.
Defaults are 5/10/20 starts for rates and 3/5/10 starts for physics, mechanics,
usage, and expected metrics. Season-to-date rates reset each season. All games
on the current calendar date are excluded, and duplicate pitcher-game keys fail
loudly. Rolling FIP/xFIP are calculated from summed prior-start
HR/BB/HBP/K/FB/outs rather than averaging per-start ratios. xFIP applies the
league HR/FB known before the projected date, with a 1,000-fly-ball prior based
on the previous loaded season. Under the pipeline's `fly_ball + popup`
definition, the sourced 2022 prior for 2023 is 0.12815157.

`batter_rolling.py` creates:

- season-to-date overall and handedness-split K%;
- lagged 5/10/20-game K%;
- empirical-Bayes season K% shrinkage toward league K% through the previous
  date only (the first date uses the exact-definition previous-season league
  rate; 2023 uses 2022's `0.22381258`);
- season-to-date whiff and chase rates;
- season-to-date and P5/P10/P20 discipline, expected-stat, contact-quality, and
  batted-ball rates. Added families include wOBA, xwOBA, xBA, BABIP, average
  exit velocity/launch angle, hard-hit%, barrel%, sweet-spot%, HR%, FB%,
  HR/FB, pulled-air balls per BIP, and batter run value per pitch.

Batter rolling features likewise exclude every same-date game, reject duplicate
batter-game keys, and allow partial early-history windows (`P20` means up to the
last 20 games, with at least one prior game by default).

`pipeline/rolling.py` keeps static keys/context, Level 2 features, and pitcher
labels. It drops raw same-game feature columns by default. Use `keep_raw=True`
only for diagnostics, never as the model input artifact.

The rolling-window caveat is **resolved for the LightGBM backbone**
(`docs/research/step4_window_decisions.md`). Targeted re-ablation kept BABIP and arm
angle on experimental defaults without promotion. Run-value **`P25`** and mean-
window thin **`P3/P5`** (drop P10 on physics/usage/mechanics/FIP) are LGBM
freeze proposals only — pipeline constants are unchanged until Step 7.
See `window_stabilization_gap.csv`, `targeted_window_ablation_*`, and
`step4_physics_windows/` in `artifacts/feature_research/`; do not recreate
windows in notebooks.

### Level 3: model-ready joins

`pipeline/training.py` joins:

- pitcher rolling form;
- the opposing batters' pregame overall/handed K%, Whiff%
  (`Whiffs/Swings`), SwStr% (`Whiffs/Pitches`), chase%, Z-Swing%, Swing%,
  Z-Contact%, BB%, expected stats, contact quality, and batted-ball outcomes;
- the season/stadium park factor.

The new batter-discipline family uses stabilization nominees rather than a
window search: lineup Z-Swing% P10, Swing% P10, Z-Contact% P20, and BB%
season-to-date. Nested confirmation selected the family in both LightGBM outer
folds (MAE improvements `0.000962` and `0.000743`) and one of two Ridge folds
(`0.000139`); Ridge selected core in the other fold. Treat the family as
supported for LightGBM and provisional for Ridge. Evidence is under
`artifacts/stabilization/expanded/batter_discipline/` and
`artifacts/feature_research/batter_discipline_ablation_*`.

The broader batter-quality screen first applied the same denominator-aware
reliability gate used for pitchers. Hard-hit%, barrel%, average exit velocity,
average launch angle, xBA, xwOBA, HR%, FB%, HR/FB, and pulled-air balls per BIP
cleared the lower-CI `r=.50` gate. BABIP, sweet-spot%, wOBA, and run value per
pitch did not. Only the ten qualified metrics entered nested testing, with one
stabilization-nominated representation each.

Pulled-air rate is defined transparently as pulled Statcast fly balls or line
drives divided by all balls in play. Pull side is determined from batter hand
and the Statcast field-center x-coordinate (`125.42`); it is a project research
definition, not a claim of exact equivalence to a vendor's proprietary metric.

Level 3 now emits three research representations: the original flat lineup
mean, a batting-order-opportunity weighted mean, and a weighted standard
deviation that preserves Judge-versus-Volpe heterogeneity. Opportunity weights
are prior-date league-average PA by lineup slot, not the current game's
realized PA. The latest learned weights decline monotonically from about 4.50
PA for slot 1 to 3.47 for slot 9. Rolling occurs per batter before aggregation;
the pipeline deliberately does not roll a changing team-lineup mean.

Inner folds selected the qualified weighted-mean-plus-dispersion family for
both models and both outer periods. It improved LightGBM outer-fold MAE by
`0.000360` and `0.000152`, but worsened Ridge MAE by `0.000209` and `0.000200`.
This is LightGBM-specific development support, not promotion. All new hitter
quality and lineup-construction columns remain research-only.

The historical lineup proxy uses the first nine distinct batters to appear for
each team, ordered by first plate appearance. This removes bullpen-only pinch
hitters from the feature membership and Level 3 requires exactly nine matched
batters. Live inference must still use the announced lineup.

Season-opening games, including early neutral-site openers, intentionally have
null opponent-lineup rates. Every batter has zero prior season-to-date PA before
their first game, so a leakage-safe rate does not yet exist. These nulls must be
handled by model-native missing-value support or preprocessing fitted on the
training split; they must not be backfilled from same-game outcomes.

The batter training frame does not yet include opposing-starter features and is
therefore not feature-complete for a production batter-side model.

### Daily lineup adapter

`Python.daily_lineups` ingests the current RotoGrinders DraftKings MLB page,
preserving batting order and projected/confirmed status. It joins each game to
the official MLB schedule, resolves scraped players only within the matching
MLB active/40-man roster, and returns numeric `batter`/`pitcher` IDs. Name-only
or forward-filled joins are forbidden. Validation requires nine unique
resolved batters per team; `--require-confirmed` additionally rejects
projected lineups.

The adapter writes dated batter and starter inputs under `data/processed/`.
RotoGrinders supplies the earlier prediction surface; MLB schedule, roster,
probable-pitcher, and person endpoints remain the canonical identity/game
surface. The HTML source is external and must be monitored for markup or usage
policy changes.

### Preserved future-target foundations

Level 1 intentionally retains `Hits`, `BB`, `Runs`, `Pitches`, `Outs`, and
`PA`/batters faced even when they are not inputs to the K/PA model. These
outcomes and the denominator plans in `reliability.py` are foundations for
future hit, walk, runs-allowed, pitches, outs, and workload models; they are not
dead columns or dead research code.

Level 2 keeps active pitcher labels (`K`, `PA`, `Outs`, `k_rate`) and also
emits leakage-safe lagged workload (`PA_P*` / `Outs_P*` / `Pitches_P*`), rest
flags, and joins team bullpen L1–L3d lookbacks for the TBF spine. Same-game
`PA` / `Outs` / `Pitches` remain labels/oracles, never prediction-time features.

`models/Strikeout-Model/train.py` reads `PITCHER_TRAINING_PATH` and defaults to
`--feature-set production` (**184** frozen features via
`Python.registries.resolve_feature_names`). Companions: `step10_180`,
`step7_185`, `pre_freeze_248`, `ridge_vif`. `models/TBF-Model/train.py` +
`score_count_layer.py` consume the workload spine for projected TBF and prop
probs. The approximate 70/15/15 chronological split keeps each calendar date
wholly inside one partition.

The frozen 2023-2024 LightGBM `production` registry has **184** features
(Step 10 P1 spine + Step 11 lineup-discipline lift). Chrono cutoffs: train ≤
2024-06-08, val 2024-06-09→08-05, test ≥ 2024-08-06. Frozen test MAE / RMSE /
R² ≈ 0.0780 / 0.0982 / 0.156
(`docs/research/step11_discipline_registry_freeze.md`; artifact
`lightgbm_krate_20260803_155401`). `step10_180` retains the prior freeze;
`step7_185` / `pre_freeze_248` remain comparison-only. Feature selection is
closed; further parked candidates live under `artifacts/feature_research/`.
The trainer filters to `TRAIN_SEASONS` before splitting, so existing Level 3
artifacts may retain later-season rows without allowing them into fitting.

## Park factors and future intangibles

`park_factors.parquet` is a dimension table keyed by `(season, home_team)`.
For season `Y`, its factor uses only seasons before `Y`. The preceding
prior-only Statcast season supplies the first model season's history, so 2023
uses 2022 rather than receiving neutral factors. A 2023-2025 build also writes
the 2026 lookup. This avoids using future park outcomes in earlier training
rows.

Venue resolution is date-aware where a team code spans multiple physical
parks. In particular, `TB` home games in 2025 resolve to Steinbrenner Field;
the override ends on December 31, 2025 because the Rays returned to Tropicana
Field in 2026. Statcast already distinguishes the Athletics' Sacramento era
as `ATH` from the pre-2025 Oakland code `OAK`.

Neutral-site and international games (including the Mexico City, Seoul, and
London series, Field of Dreams, and the Little League Classic) are not
currently filtered. They remain grouped under Statcast's listed home-team
code and can slightly contaminate that venue's factor.

Future catcher, weather, travel, or other context belongs in separate
keyed dimension tables and is joined at Level 3 (or onto the TBF spine). It
does not belong in player rolling files unless the feature itself represents
lagged player form. Market / CLV is a separate product layer
(`docs/reference/market_clv_gates.md`) and never enters training.
Rest / bullpen / TBF Phases A–C are implemented and documented in
`docs/research/workload_rest_bullpen_feature_plan.md`; remaining roadmap items
are in `docs/diagrams/04-roadmap.md`.

## Stabilization and feature selection

`reliability.py` contains:

- game-count split-half reliability;
- enhanced reliability/ICC/year-over-year summaries;
- denominator-aware split-half curves for pitch-, swing-, zone-, and
  plate-appearance-denominated statistics.

Use the denominator where reliability reaches the chosen threshold (commonly
`r ≈ 0.5`), translate it to starts, then compare nearby windows with
chronological cross-validation and grouped ablation. Stabilization chooses
plausible windows; it does not prove predictive value.

## CLV-skill checks (market layer)

`skill_stats.py` (the **market layer** companion of `reliability.py`) contains
the skill checks run against `artifacts/odds_log/ledger.parquet` by
`production/notebooks/results_dashboard.ipynb` Sections 11-18:

- `two_proportion_z_test(s_a, n_a, s_b, n_b)` — pooled-variance z-test for
  head-to-head win-rate comparison; used by §11 to test whether
  `clv ≥ +1.0pp` bets win at a different rate than `clv < +1.0pp` bets;
- `bootstrap_bca_ci(values, *, n_boot, alpha, seed, statistic)`
  — bias-corrected-and-accelerated bootstrap CI; used by §12 / §18a because
  `market.bootstrap_mean_ci` (percentile-only) is biased and too narrow at
  the per-band n≈10-40. `_inverse_std_normal_cdf` is a 60-iteration bisection
  on `_std_normal_cdf` (prior Wichura/Acklam approximation constant typos
  were retired); `_jackknife_acceleration` is the standard BCa `a` estimator;
- `stake_weighted_bootstrap_ci(values, weights, ...)` — BCa CI on
  `sum(clv × stake) / sum(stake)`, the metric that governs bankroll outcomes
  (used by §14; equal-weighted CLV is the skill metric but the sizing metric
  is what scales to bankroll);
- `rolling_stat_with_se(values, window, se_scale)` — rolling mean with a
  normal-approximation ±se_scale × SE ribbon for the day-stability check
  used by §13.

All four are pure-Python (numpy imported lazily inside the BCa helpers only
when array operations are needed), matching `market.bootstrap_mean_ci`'s
convention. `pytest` coverage: `tests/test_skill_stats.py` (14 tests).

## Statistical safeguards checklist

Beyond leakage prevention, the following categories are tracked separately
because they require distinct defenses:

- **Target leakage:** `features.py` allowlist and same-game exclusion tests
  enforce the pregame boundary described above.
- **Multicollinearity:** the implemented training-only analysis uses a full
  Pearson pass, targeted Spearman checks for rolling/shrinkage/xFIP families,
  and narrow Kendall checks for tied low-count families at
  `artifacts/feature_research/*correlation*`. VIF and Pearson-linked clusters
  are in `vif.csv` and `feature_dictionary.csv`. Pairwise correlation cannot
  detect multivariate redundancy, so VIF remains required. These diagnostics
  apply to Ridge interpretation, not as a LightGBM pruning rule; investigate
  VIF above 5 and treat VIF above 10 as serious. Step 1 adopted the Phase-2
  cluster proposal as the Ridge research registry with one amendment (drop
  `xFIP_P5` → 73 features; keep `xwOBA_P5` as residual VIF > 10). See
  `docs/research/step1_feature_dict_vif_findings.md` and `--feature-set ridge_vif`.
  Full VIF<10 is not enforced: overlapping rolling histories are redundant by
  design, and tree prediction is generally insensitive to multicollinearity
  even though Ridge coefficients and feature attribution are not. The expanded
  563-column research frame has a separate 165-column Ridge proposal under
  `artifacts/feature_research/expanded/` (research-only surface).
- **Deterministic redundancy:** exact complements or sums, such as
  `Contact% = 1 - Whiff%` and `CSW% = SwStr% + called-strike%`, are now
  excluded by `features.py` and covered by feature-safety regression tests.
  Conventional Strike% is also excluded as `1 - Ball%`, and neutral count
  share is omitted because ahead + neutral + behind = 1.
  The usage-composition rank audit is saved in
  `artifacts/feature_research/usage_composition_rank_audit.csv`.
- **Cross-validation:** only chronological, date-disjoint folds are allowed;
  standard random K-fold CV is rejected. Feature, window, and hyperparameter
  selection must use inner folds distinct from outer folds used to confirm
  generalization. This is implemented in `nested_cv.py`: inner folds are
  contained wholly within each outer-train period, `_research_folds` is
  removed, and outer data are used only after a configuration is selected.
  `tests/test_nested_cv.py` enforces the boundary and containment rules.
- **Heteroskedastic target treatment:** single-game K/PA is noisier at low PA
  than high PA. Step 5 nested compares (PA-weighted, binomial, beta-binomial)
  favor **unweighted LightGBM**; see `docs/research/step5_*_findings.md`. Count-layer
  props use projected TBF trials (`docs/research/count_layer_findings.md`).
- **Population-selection bias:** `PA >= 9` is a postgame outcome used to define
  a pregame prediction population. Phase D interim policy frozen (~3.5%
  excluded); pregame role labels still open for pristine v1
  (`docs/research/phase_d_population_findings.md`).
- **Feature-selection stability:** a family's improvement must persist across
  separate seasons and outer folds using grouped permutation or drop-column
  importance. SHAP is considered only after deterministic and highly
  correlated features are reduced.
- **Expanded-feature registry:** P2 arsenal, count-state, BIP/BABIP, arm angle,
  SIERA, run value, and lineup expansions require `include_experimental=True`.
  Frozen production is **184** features (`docs/research/step11_discipline_registry_freeze.md`);
  `step10_180` / `step7_185` / `pre_freeze_248` are comparison-only. Definitions live under
  `artifacts/feature_research/`.
- **Multiple-comparisons risk:** every consulted configuration belongs in the
  `PAPER_NOTES.md` experiment log. The `2025-07-06+` partition was already
  scored by historical baseline runs, so it is not a pristine future test and
  must not be reused for feature decisions. A new honest final check requires
  genuinely future, post-freeze data.

See `docs/research/statistical_audit_and_sequencing_report.md` for the complete audit,
VIF caveats, nested-fold proposal, and count-model scope.

## Current feature inventory

The live Level 3 parquet contains labels, identifiers, production features, and
research candidates. Do not treat every numeric column as a model input.
`Python.registries.resolve_feature_names(frame, "production")` returns the
**184** frozen features; use `"step10_180"`, `"step7_185"`, `"pre_freeze_248"`, or
`"ridge_vif"` for companions.
`Python.features.model_feature_names(..., include_experimental=True)` exposes
the broader research-eligible surface.

The current generated inventory is
`artifacts/feature_research/expanded/feature_dictionary.csv`. Registry status
and rationale are in `candidate_feature_registry.csv`. Current freeze:
`docs/research/step11_discipline_registry_freeze.md`. Prior freezes:
`step10_p1_registry_freeze.md`, `step7_registry_freeze.md`. Regenerate
diagnostics in the order documented by `artifacts/README.md` whenever Level 3
feature logic changes.

## FIP constant maintenance

Completed-season constants in `FANGRAPHS_FIP_CONSTANT` are fixed. Refresh the
current season from FanGraphs Guts before rebuilding, pass an override to
`add_fip_xfip`, or set `include_constant=False` when only the FIP core is needed.
A season-level additive constant has no within-season tree-model signal.

## Current limitations

- Projected TBF is **frozen** (Ridge + thin bullpen; see
  `docs/research/tbf_first_model_findings.md`). Count layer v1 is chrono-scored
  (`docs/research/count_layer_findings.md`; lines **2.5…9.5**). Live slate
  assembly and paper-trading CLV are automated under `production/`
  (`docs/reference/live_assembly_plan.md`, `market_clv_gates.md`).
- The CLV skill gate stays **INCONCLUSIVE** at the resolved ledger: floor ≥ 12%
  BCa CI `[-0.30, +1.78]` includes zero (n_clv = 72). Hold 12% / ⅛-Kelly until
  **n_clv ≥ 150** at floor ≥ 12%, per
  `docs/research/floor_freeze_log.md` and `production/notebooks/results_dashboard.ipynb`
  §18b (`artifacts/odds_log/next_50_checkpoint.json`).
- Negative-binomial count challenger and mixing over a TBF distribution are
  not built. Step 5 rate-likelihood helpers remain in
  `src/Python/likelihoods.py`.
- Daily lineup ingestion resolves names within-team via
  `active → 40Man → fullSeason`. Dual-starter scoring and projection log/grade
  are in production ops.
- Step 5 likelihood sequence is **resolved**: unweighted LightGBM remains the
  rate backbone. Count-layer β-binomial on projected TBF collapsed to binomial.
- Phase D interim policy frozen (`docs/research/phase_d_population_findings.md`);
  pregame role labels still required for pristine v1.
- Full batter-by-pitch-type arsenal/lineup interactions are not implemented;
  the research-only run-value audit found no pitch type or coarse family
  reliably estimable at the lower-CI `r=.50` gate.
- Weather, travel, and catcher inputs are not integrated. Rest/bullpen/TBF
  companions A–C are in `docs/research/workload_rest_bullpen_feature_plan.md`.
- Neutral-site/international games can contaminate team-keyed park factors.
- The production LightGBM registry is the **frozen 184-feature** allow-list
  (Step 11). `step10_180` / `step7_185` / `pre_freeze_248` remain for comparisons.
  Ridge research uses `ridge_vif` (73). The historical 2025 benchmark is not an
  untouched final test.

## Validation

Unit tests cover Statcast flags, pitcher/batter game aggregation, rolling
leakage boundaries, FIP/xFIP, park factors, lineup joins, stabilization, safety
rules, and parquet stage boundaries. Run:

```powershell
python -m pytest
```
