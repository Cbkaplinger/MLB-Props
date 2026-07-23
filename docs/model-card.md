# Pitcher strikeout-rate model card

## Intended use

Estimate a starting pitcher's pregame strikeout rate. A separate projected
batters-faced model will convert the rate to an expected strikeout count:

```text
expected strikeouts = predicted strikeout rate × projected batters faced
```

This repository is research code, not a validated betting system.

## Data and target

- Source: Baseball Savant pitch-level regular-season data.
- Level 1 unit: one row per qualifying starter/game.
- Target: `k_rate = K / PA`.
- Default training seasons: 2023-2025.
- Evaluation: chronological train/validation/test splits only; calendar dates
  are never divided across partitions.
- Primary rate metrics: MAE, RMSE, and R² on future starts.
- Prop evaluation must use projected, never actual same-game, batters faced.

The current date-disjoint 2023-2025 baseline uses 227 approved features.
Held-out test results are Mean RMSE 0.1076 / R² -0.0001, Ridge RMSE 0.1003 /
R² 0.1313, and LightGBM RMSE 0.0994 / R² 0.1459.

## Leakage policy

Every feature must be available before first pitch. Forbidden model inputs
include same-game `K`, `PA`, `Outs`, actual TBF, and any statistic containing
the game being predicted. Level 2 uses prior games only. `K`, `PA`, `Outs`, and
`k_rate` are retained in Level 3 solely as labels/evaluation fields.

`src/Python/features.py` validates explicit feature lists and accepts only
approved lagged-feature families and context columns. Unknown numeric columns
fail rather than silently entering training.

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
- Rolling FIP/xFIP use summed prior-start counts. xFIP uses league HR/FB
  available before the game date, regressed toward the previous season with a
  1,000-fly-ball prior. The 2023 boundary uses 2022 Statcast context calculated
  under the same fly-ball definition; 2022 itself does not enter model rows.

## Context features

Opponent features aggregate each hitter's pregame overall/handed K%, whiff%,
and chase%. Historical membership uses the first nine distinct batters by first
plate appearance and requires complete nine-player coverage. Live projections
must substitute the announced lineup.

Park factors are keyed by `(season, home_team)` and use prior seasons only.
The prior-only 2022 source supplies 2023 park history without entering model
rows. This prevents future park outcomes from entering earlier rows.

## Evaluation requirements

Before publishing performance or using probabilities:

- run the complete Level 1-3 pipeline;
- choose rolling windows with denominator-aware stabilization, then validate
  nearby choices with chronological CV and SHAP;
- train without label/identifier columns;
- compare against a mean baseline and a regularized linear baseline;
- assess calibration and proper scoring rules for prop probabilities;
- use projected TBF in all strikeout-count evaluation;
- freeze the data window, feature list, parameters, and model artifact.

## Current limitations

- TBF projection and end-to-end prop backtesting are incomplete.
- Announced-lineup ingestion is not implemented.
- Batter-by-pitch-type arsenal interactions remain planned.
- Weather, travel/rest, catcher, and market inputs are not integrated.
