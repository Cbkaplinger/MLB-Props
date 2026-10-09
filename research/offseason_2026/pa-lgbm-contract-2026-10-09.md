# PA-LGBM lane contract — label, feature scaffold, reconciliation (2026-10-09)

> **Status: FROZEN 2026-10-09, before any scaffold code was written.** Owner
> authorization of 2026-10-09: contract + data/feature scaffold + bounded
> reconciliation ONLY. No model fitting, no scored comparison, no tuning, no
> production changes, no 2025/2026 outcome access, no commit/push. The fit
> itself is a LATER, separate authorization request.

Scope: replace the game-rate label with a binary PA label AND redesign the
historical feature aggregation (pooled sufficient statistics, explicit
evidence strength). Changing the label alone was explicitly rejected.

Frozen prior results stay untouched: archived bridge/WF runs, I3b, pa-k
baseline arm A/B results, all manifests. Any workload-denominator adjustment
to the BF lane is OUT OF SCOPE here; interface findings are reported, not
acted on.

## 1. Label contract — completed-PA definition `pa_completed_v1`

Identity: `(game_pk, at_bat_number)`, asserted unique per game.

Terminal selection: within each PA group, order by `pitch_number`; the
group's outcome is defined by the **last row carrying a non-null event that
maps to `completed_pa`**. If no such row exists, the group is classified by
its terminal (max `pitch_number`) row. Rationale: baserunning events can be
logged after a completed outcome within the same group; a terminal-row-only
rule (production) can discard a genuine completed PA. This differs from
production `plate_appearances()` (last row, then filter) BY DESIGN; the
reconciliation quantifies the difference with examples. It also differs from
the pa-k table (which trusted `events` non-null rows without terminal
selection).

Explicit event mapping (three classes; scaffold fails loud on any event
value absent from the map):

- `completed_pa`: every terminal batting outcome — includes `strikeout`,
  `strikeout_double_play`, `walk`, `intent_walk`, `hit_by_pitch`, `single`,
  `double`, `triple`, `home_run`, `ground_rule_double`, `field_out`,
  `force_out`, `fielders_choice`, `fielders_choice_out`, `triple_play`,
  `grounded_into_double_play`, `double_play`,
  `sac_fly`, `sac_fly_double_play`, `sac_bunt`, `sac_bunt_double_play`,
  `field_error`, `catcher_interf`, `fan_interference`,
  `defensive_indiff`. Label `y = 1` iff event is in `STRIKEOUT_EVENTS`
  = {strikeout, strikeout_double_play} (both are pitcher and batter Ks).
  Amendment 2026-10-09 (pre-implementation data probe, 2023 parquet):
  `fielders_choice`, `fielders_choice_out`, `triple_play` added after
  enumerating real distinct events; scaffold still fails loud on anything
  unmapped, and the reconciliation re-enumerates per season.
- `baserunning_only`: the 16 production `NON_PA_EVENTS` (caught stealing x3,
  pickoff x3, pickoff_caught_stealing x3, stolen_base x3, `wild_pitch`,
  `passed_ball`, `other_out`, `runner_double_play`). NOT plate appearances;
  excluded from the label population; counted. (Inheritance from production
  `statcast.py` is a starting classification, not a majority vote; the
  reconciliation reports how often these groups contain no completed event.)
- `incomplete`: `truncated_pa`, or terminal row with null events, or a group
  with no mapped event at all, or a MIXED-BATTER group (more than one
  distinct batter within the PA group). Amendment 2026-10-09, after the
  first reconciliation probe found 13-16 mixed-batter groups per season in
  real data (mid-PA batter changes): these carry an explicit `mixed_batter`
  reason flag, are excluded from labels, and are counted with examples in
  the report. Excluded; counted; never silent.

Attribution: responsible pitcher = the `pitcher` value on the defining row.
PA groups with more than one distinct `pitcher` are flagged
`mid_pa_pitcher_change`, attributed to the defining-row pitcher, and counted
(reported, not dropped).

Population for modeling: first-pitcher PAs only (spine first-pitcher
identity via `audit_identity`, same join as pa-k). All-pitcher PAs are a
different population, reported in reconciliation, never mixed.

Denominator policy: `pa_completed_v1` is a NEW, versioned definition. Neither
production nor research counts are adopted because they are called canonical.
The reconciliation report (Section 5) is the evidence record. If the new
denominator changes workload meaning (BF lane interface), that is REPORTED,
not silently absorbed.

## 2. Feature aggregation redesign — pooled sufficient statistics

Principle: carry **counts, sums, valid-observation counts, and variance
inputs**; derived means/rates are computed at read time. Changing a window
never re-averages an average. Every rate feature ships its numerator and
denominator columns alongside.

History rule: snapshots use ONLY rows with `game_date` strictly before the
forecast game's date (same-day excluded in v1). Feature weighting (how
history is pooled) and training-row weighting (which population the fit
prioritizes) are SEPARATE declared decisions — v1 training rows are
unweighted per PA (declared; opportunity weighting is a later, separate
authorization).

### Pitcher snapshot (keyed by `(game_pk, pitcher)`, cutoff = game_date)

| Feature block | Construction (v1 frozen recipe) | Evidence columns carried |
| --- | --- | --- |
| K rate | shrunk: `(k_prior + w*lg)/(n_prior + w)`, w=150, lg = training-window prior K share | `k_prior`, `n_prior` (completed PAs) |
| Velocity per pitch_type | pooled `sum(release_speed)`, `sum(release_speed^2)`, `n_valid` (non-null measurements only); mean/var derived at read | `n_valid`, `n_missing`, last valid speed, days since last valid |
| Usage per pitch_type | `n_type / n_eligible`; `n_eligible` = rows with non-null `pitch_type` — missing velocity NEVER alters this denominator | `n_type`, `n_eligible` |
| Whiff rate | `whiffs / swings` (statcast.py description sets) | both counts |
| Contact rate | `contacts / swings` | both counts |
| Workload | prior starts (distinct game_pk), prior completed PAs, days since previous appearance, count of prior short starts (PA<9; historical fact, disclosed as descriptive) | all counts + dates |

Fastball v1 = `pitch_type == "FF"` only; SI and all other types carried
separately (no blending). Headline velocity features: FF `n_valid`, FF mean,
FF sd, FF days-since-last-valid, plus per-type usage shares.

### Batter snapshot (keyed by `(batter, game_pk)`, cutoff = game_date)

| Feature block | Construction | Evidence columns |
| --- | --- | --- |
| K rate vs RHP/LHP split | same shrunk construction, w=150, per hand side faced | `k_prior`, `n_prior` per side |
| Workload | prior completed PAs, days since previous game | counts + dates |

### Shrinkage / recency (small, fixed; no search)

- v1 recipe: w=150 shrinkage on all rate features (pa-k heritage); recency
  carried as FEATURES (days-since columns), never as weights.
- Pre-declared bounded comparison for the LATER fit authorization (not the
  scaffold): w in {50, 150, 400} on the K-rate block only, evaluated under
  the frozen experiment spec of Section 4. No other windows/shrinkage
  variants are authorized; no "trust after X observations" thresholds.

No broad window or feature search is authorized anywhere in this lane.

## 3. Pregame availability (leakage rules)

- Pitcher snapshot keyed by pitcher-game; batter snapshot keyed by
  (batter, game_pk); cutoff = the forecast game's `game_date`.
- No current-game outcomes in either history. Realized lineup/appearance
  paths are NOT inference inputs; participating hitters only label rows.
- Invariance tests required: future-append (adding fabricated future games
  leaves snapshots byte-identical) and outcome-mutation (mutating a
  current-game outcome leaves features of that game's rows unchanged).
- Cold-start taxonomy (mutually exclusive, counted):
  `career_debut`, `season_debut`, `insufficient_history` (prior n < w),
  `failed_join`. Short outings, debuts, and sparse history are retained in
  evaluation; no outcome-based eligibility anywhere.

## 4. Frozen experiment spec (declared now; executed only on later authorization)

- Primary metric: paired PA log loss (challenger − reference), slate-date
  clustered bootstrap, 2000 resamples, seed 20261001, Holm over the frozen
  family of 3 primary comparisons: {B vs A, C vs A, C vs B}.
- Secondary: Brier, reliability bands (pa-k set), coverage, permanent slices
  (short outings, cold-start classes, calendar month).
- Arms: A = shrunk log5 (w=150, pa-k heritage); B = LightGBM binary logistic
  WITHOUT log5-derived rate features; C = same WITH them. Frozen legacy
  baseline hyperparameters (5000/0.03/31/50/0.8/0.7/0.1/2.0/seed42/ES200);
  no class balancing; no tuning. Every fold's early stopping occurs before
  its scored block (last-15% chronological internal validation, WF pattern).
- Training rows: one row per completed PA, unweighted (declared). Training
  population = first-pitcher completed PAs, 2023 (+2022 via aggregates only,
  pa-k convention) with 2024 as the chronological transfer population.
- Baselines inventory (reported in reconciliation): pa-k arm A log5 (scored
  2026-10-07, retained benchmark), pa-k arm B L2 logistic (scored, CI
  includes 0), production L3 LightGBM ensemble (game-rate, production PA
  denominator, lineage NOT PA-usable), phase11b walkforward OOF (game-rate,
  lineage-mismatched). No PA-level tree prototype exists in the tree. Stored
  in-sample predictions are NEVER compared with new chronological OOF.
- Aggregation separation: this authorization covers the classifier lane
  ONLY. Binomial vs Poisson-binomial count aggregation (same classifier,
  same workload PMF, same rows; binomial scalar = mean matchup PA prob over
  the frozen lineup assumption) is a separate later comparison. No realized
  workload or lineup paths in deployable forecasts.

## 5. Reconciliation (bounded, no modeling)

Loader: reuse `run_corrected_history_2023.py` provenance machinery
(`default_sources`, `verify_and_load`, `_unified_pitches`, `audit_identity`)
- no duplicate loader. 2022/2023 via known SHAs; 2024 first-hashed as
identity registration (recorded, not independently verified), WF-convention.

Report contents (JSON + markdown under `MLB-Props-Research\pa-lgbm-reconciliation-<ts>\`):

1. `pa_completed_v1` population counts per season: groups, completed,
   incomplete, baserunning-only, mid-PA pitcher changes, first-pitcher
   subset, K counts.
2. Discrepancy counts vs production `plate_appearances()` (all-pitcher and
   first-pitcher) and vs the pa-k table convention, with per-event-class
   breakdown and >=20 concrete examples per disagreement class
   (game_pk, at_bat_number, event sequence).
3. Feature-source coverage: FF valid-velocity availability, per-type usage
   null rates, cold-start class counts on 2023-2024 first-pitcher rows.
4. Baseline inventory (Section 4) with code paths and provenance.
5. Workload interface findings (BF-lane implications REPORTED only).

Stop rule: any unmapped event value, identity duplication, or reconciliation
failure STOPS the lane; requirements are never relaxed to proceed.

## 6. Deliverables of THIS authorization

1. This frozen contract.
2. `research/offseason_2026/pa_lgbm_scaffold.py` — pure functions, no I/O:
   event mapping, label table, pooled snapshot builders, feature dictionary.
3. `tests/test_pa_lgbm_scaffold.py` — synthetic tests: mapping classes,
   terminal/baserunning selection, mid-PA flag, pooled-vs-equal-weight
   identity, velocity/usage denominator separation, swing identity,
   pregame cutoff, future-append + outcome-mutation invariance, cold-start
   taxonomy, fail-loud unmapped events.
4. `research/offseason_2026/run_pa_label_reconciliation.py` + its report.
5. Feature dictionary with exact denominators and history units (in
   scaffold docstring + contract Section 2).
6. Backlog receipts; one fit-ready authorization request listing exact
   changed files.

Changed-file boundary: only the four paths above plus
`docs/EXECUTION_BACKLOG.md`. Any additional path requires proposal first.

## Amendments (dated, all BEFORE any fitting or scoring)

### Amendment 3 (2026-10-09, pre-fit checks) — baseline inventory corrected

The Section 4 sentence "No PA-level tree prototype exists in the tree" is
corrected: `experiments/tree_pa` EXISTS (card sha 95b9627d..., phase 8) with
verdict TIE / blend rejected / lane CLOSED — it exists but is not an open
challenger. `experiments/logistic_pa` (L3 ridge logistic, DEVELOPMENT
baseline, fit 2023-03-30..10-01 on 105,225 rows, permitted scoring 2024
E1/E2, bundle reproduced to 2.2e-16) is the strongest prior PA ML baseline.

**Arm D added (2024 block only):** stored L3 predictions
(`experiments/logistic_pa/pa_predictions.parquet`, all 2024 rows, hash
recorded in pre-fit checks) are OUT-OF-SAMPLE for 2024 (fit 2023 only) and
are joined to the 2024 v1 eval rows on `(game_pk, at_bat_number)`;
unmatched rows counted; D metrics computed on matched rows only and paired
comparisons involving D restricted to matched rows. The 2023 stored
predictions are IN-SAMPLE (fit dates cover the 2023 eval windows) and are
NEVER used. 2023 family stays {B−A, C−A, C−B}; 2024 family is
{B−A, C−A, C−B, D−A, C−D}; Holm applied WITHIN each block over that block's
family.

### Amendment 4 (2026-10-09, pre-fit checks) — velocity provenance

Raw (pre-imputation) FF availability over the pooled prior pool (prior
seasons + same-season strictly earlier): 4,771/4,860 keys with >=1 valid FF
measurement (2023), 4,752/4,854 (2024); p50 736 / 1,071 valid measurements.
Zero-or-absent keys: 89 (2023) / 102 (2024), dominated by career debuts
(60/53) — genuinely no history. Keys with FF rows but zero valid
measurements: 0 in every class. Historical-feature and label priors both
use pa_completed_v1 completed rows. Priors for rate AND pitch-type/swing
features are built from the POOLED multi-season raw pool (a single-season
raw pass was a checks-stage bug, corrected before fitting; the
season_debut class initially showed no FF history only because of it).

Frozen velocity handling for the fit: NO imputation for LightGBM arms
(native NaN handling) + explicit `has_ff_history` flag; NaN is honest
missingness. The training-league-median fill idea is withdrawn (no linear
arm consumes velocity in this run).

### Amendment 5 (2026-10-09, owner freeze) — metric and scope wording

- Primary: opportunity-weighted (per-PA mean) paired log loss on identical
  eval rows. Start-weighted diagnostics are SECONDARY.
- Secondary: Brier, reliability bands, start-weighted means, coverage,
  cold-start slices (career_debut / season_debut / insufficient_history /
  established), short-outing slices (start completed PA < 9), month slices.
- 2024 is labeled a chronological DEVELOPMENT TRANSFER, not untouched
  validation.
- Mechanism receipt (check 1): starter-level identities hold exactly
  (pa-k − v1 = mixed-batter; production − v1 = truncated_pa + mixed-batter;
  v1-only = 0 in all seasons — the bridge-audit baserunning-filter-order
  class is empirically empty in 2022-24 regular seasons; mid-PA pitcher
  changes = 0 within starter groups, 58-64/season across all pitchers,
  attributed to the defining-row pitcher).

### Amendment 6 (2026-10-09, post-first-run correctness) — run invalidated and re-scored

The first scored run (`pa-lgbm-comparison-2024-20261009_152350`, completed
as `..._152829`) is INVALIDATED: its feature join attached snapshots on
`game_pk` alone while snapshot keys cover BOTH teams' starting pitchers per
game (the pa-k 4,860-appearance heritage of `audit_identity`), exactly
duplicating every eval row (96,611 unique keys x 2 = 193,222). A pa-k-style
"first-pitcher" population means per-side starters (both starters per
game), ~106k completed PAs per season and ~96.6k eval rows — matching the
pa-k 2023 eval arithmetic (45,524/16,065/17,954/17,072). The reported
"2024 C−A improvement" of the invalidated run was an artifact; after the
fix it flips sign.

Corrected canonical run: `pa-lgbm-comparison-2024-20261009_154851`
(n=96,611 2023 / 96,558 2024; per-origin windows match pa-k). Regression
tests added: feature-join row-cardinality guard (fail-loud) and a
cross-starter duplication test. The D common-row comparison
(`matched_metrics`, 95,808 rows) is reported alongside full-coverage A/B/C;
unmatched rows (750) are reason-coded as stored-population definition
differences. Attempts preserved.
