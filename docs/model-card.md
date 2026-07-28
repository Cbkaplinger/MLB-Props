# Pitcher strikeout-rate model card

## Intended use

Estimate a starting pitcher's pregame strikeout rate. A frozen projected
batters-faced model converts the rate to an expected strikeout count and line
probabilities:

```text
expected strikeouts = predicted strikeout rate × projected batters faced
P(K ≥ line) ← count layer on projected TBF
```

This repository is research code, not a validated betting system.

## Data and target

- Source: Baseball Savant pitch-level regular-season data.
- Level 1 unit: one row per qualifying starter/game.
- Target: `k_rate = K / PA`.
- Training, validation, and internal test seasons: 2023-2024 only.
- Frozen production registry: **180** LightGBM features (Step 10 P1 physics
  swap; see `docs/step10_p1_registry_freeze.md`). Companion `step7_185` retains
  the prior 185-feature freeze for bake-offs.
- Historical holdout season: 2025. The trainer excludes it before any split or
  preprocessing fit. Earlier baseline work already consulted 2025, so it is a
  historical benchmark rather than a pristine final test.
- Companion models: frozen Ridge projected TBF + count layer
  (`docs/tbf_first_model_findings.md`, `docs/count_layer_findings.md`).
- Evaluation: chronological train/validation/test splits only; calendar dates
  are never divided across partitions.
- Primary rate metrics: MAE, RMSE, and R² on future starts.
- Prop evaluation must use projected, never actual same-game, batters faced.
  Prefer Brier / log loss on lines over accuracy alone.

The frozen date-disjoint 2023-2024 LightGBM production artifact uses **180**
features. Test MAE / RMSE / R² ≈ 0.0787 / 0.0987 / 0.147
(`docs/step10_p1_registry_freeze.md`). Artifact:
`artifacts/models/lightgbm_krate_20260728_033241.*`. Internal chrono results are
development evidence, not an independent final evaluation. `step7_185`,
`pre_freeze_248`, and earlier screens remain process evidence.

## Leakage policy

Every feature must be available before first pitch. Forbidden model inputs
include same-game `K`, `PA`, `Outs`, actual TBF, and any statistic containing
the game being predicted. Level 2 uses prior games only. `K`, `PA`, `Outs`, and
`k_rate` are retained in Level 3 solely as labels/evaluation fields.

`src/Python/features.py` is a safety gate: it accepts only approved
lagged-feature families and context columns, and unknown numeric columns fail
rather than silently entering training. It also enforces the **180-feature**
production allow-list by default; `step7_185`, `pre_freeze_248`, and expanded
research candidates require an explicit feature-set / experimental opt-in.

## Feature pipeline

1. `pipeline/games.py`: raw Savant to pitcher-game, batter-game, and park
   dimension tables.
2. `pipeline/rolling.py`: game tables to lagged rolling/season-to-date player
   features while retaining static game context.
3. `pipeline/training.py`: pitcher form + opponent lineup + prior-season park
   factor to the model-ready frame.

Important definitions:

- true starts require at least nine batters faced by default;
- foul tips are whiffs;
- fly balls include popups;
- wOBA/xwOBA use Savant values and denominators;
- pitcher outs include recorded caught-stealing and pickoff outs;
- release extension and horizontal/vertical release-point consistency are
  included;
- research-only candidates include P2 arsenal presence/usage, BIP/BABIP,
  count-state rates, arm angle, fixed-formula SIERA, and run-expectancy value;
  none cleared nested promotion, so they are not production inputs;
- opposing-lineup Z-Swing%, Swing%, Z-Contact%, and BB% season-to-date and
  rolling candidates are generated, but remain research-only pending an
  explicit registry freeze;
- Rolling FIP/xFIP use summed prior-start counts. xFIP uses league HR/FB
  available before the game date, regressed toward the previous season with a
  1,000-fly-ball prior. The  midseason Step 10 swap promotes five physics stems
  to **P1** (last start) while dropping their redundant P3/P5;
- 2023 boundary uses 2022 Statcast context calculated under the same fly-ball
  definition; 2022 itself does not enter model rows.

## Context features

Opponent features aggregate each hitter's pregame overall/handed K%,
Whiff% (`Whiffs/Swings`), SwStr% (`Whiffs/Pitches`), and chase%. Research-only
lineup columns additionally cover discipline, wOBA/xwOBA/xBA, BABIP, contact
quality, batted-ball shape, and run value over season-to-date and P5/P10/P20
histories. They are represented as flat means, prior-date batting-order
opportunity weighted means, and weighted lineup dispersion. Historical
membership uses the first nine distinct batters by first PA and
requires complete nine-player coverage. The frozen 180-feature production
baseline retains only the established lineup context columns. Live
projections substitute the RotoGrinders projected/confirmed lineup through
`Python.daily_lineups`; every scraped name must resolve to an official
team-roster MLB ID.

Park factors are keyed by `(season, home_team)` and use prior seasons only.
The prior-only 2022 source supplies 2023 park history without entering model
rows. This prevents future park outcomes from entering earlier rows.

## Evaluation requirements

Before publishing performance or using probabilities:

- run the complete Level 1-3 pipeline;
- choose rolling windows with denominator-aware stabilization, then validate
  nearby choices with chronological CV and grouped ablation;
- train without label/identifier columns;
- compare against a mean baseline and a regularized linear baseline;
- assess calibration and proper scoring rules for prop probabilities;
- use projected TBF in all strikeout-count evaluation;
- freeze the data window, feature list, parameters, and model artifact;
- retain 2023-2025 in `PIPELINE_SEASONS` for holdout/projection artifacts, but
  enforce `TRAIN_SEASONS = (2023, 2024)` in trainer loading; no 2025 row may
  enter training, validation, preprocessing, or internal testing;
- perform feature/window/hyperparameter selection in inner chronological folds
  and confirm the procedure in distinct outer folds. The 2025 holdout was
  already scored by historical baselines, so it must not drive further model
  decisions or be described as pristine; the next honest final test requires
  genuinely future post-freeze games;
- account for K/PA heteroskedasticity via the closed Step 5 nested compares
  (keep unweighted LightGBM; `docs/step5_*_findings.md`);
- derive `P(K >= n)` from the count layer on **projected** TBF
  (`docs/count_layer_findings.md`); prefer Brier/log loss over accuracy.
  Negative-binomial challenger and TBF-distribution mixing remain optional;
- after the feature freeze, run **Phase 11** estimator tuning, walk-forward
  stack backtest, and calibration before live or market use
  (`docs/phase11_model_quality_gates.md`).

## Diagrams

Phase charts (keep separate; do not collapse into one mega-flowchart):

- `diagrams/00-index.md` — status snapshot
- `diagrams/01-architecture.md` — as-built L1→L3→train→artifact, live deferred
- `diagrams/02-leakage-and-risks.md` — priors, park contamination, ≥9 PA filter
- `diagrams/03-modeling-and-evaluation.md` — chrono splits, Steps 1–10, Phase 11
- `diagrams/04-roadmap.md` — Phase 11 → live → market
- `docs/workload_rest_bullpen_feature_plan.md` — rest / bullpen / TBF (A–C done; D open)
- `docs/tbf_first_model_findings.md` / `docs/count_layer_findings.md` — TBF + props
- `docs/step5_*_findings.md` — Step 5 likelihood arm results
- `docs/step10_p1_registry_freeze.md` — current feature freeze
- `docs/phase11_model_quality_gates.md` — **next** engineering phase

## Current limitations

- **Projected TBF is frozen** (Ridge + thin bullpen; test MAE ≈ 2.49). Same-game
  `PA` remains label/oracle only. Lagged workload (`PA_P*` / `Outs_P*` /
  `Pitches_P*`), rest, and team bullpen L1–L3d are in Level 2 / TBF joins; they
  are experimental for k-rate and do not enter the 180-feature freeze.
- **Count layer v1 + Phase 11 stack:** walk-forward expected_K MAE ≈ 1.78;
  line ECE ≈ 0.024 (no recalibration). Negative-binomial / TBF-mixture
  challengers not built. See `docs/phase11_model_quality_gates.md`.
- Daily lineup ingestion exists (`Python.daily_lineups`); live assembly is
  optional next with opener **out-of-support** flags —
  `docs/live_assembly_plan.md`.
- Step 5 nested compares favor unweighted LightGBM for the *rate* model; the
  count layer re-checked β-binomial on projected TBF (κ → binomial limit).
- Phase D: ~3.5% of first pitchers excluded by `PA ≥ 9`; interim policy frozen
  (`docs/phase_d_population_findings.md`). Pregame role labels still required
  for pristine v1 claims.
- Batter-by-pitch-type run value remains research-only.
- Weather, travel, catcher, and market (de-vig / Kelly) inputs are not integrated.
- Neutral-site/international games can contaminate team-keyed park factors.
- The production LightGBM gate is the **frozen 180-feature** registry
  (`docs/step10_p1_registry_freeze.md`). Ridge research uses `ridge_vif` (73).
  Historical 2025 cannot serve as a pristine final test.
