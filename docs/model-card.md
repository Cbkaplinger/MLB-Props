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
- Evaluation: chronological train/validation/test splits only.
- Primary rate metrics: MAE, RMSE, and R² on future starts.
- Prop evaluation must use projected, never actual same-game, batters faced.

No current performance score is published. Older notebook scores used a
superseded feature pipeline and must not be treated as valid.

## Leakage policy

Every feature must be available before first pitch. Forbidden model inputs
include same-game `K`, `PA`, `Outs`, actual TBF, and any statistic containing
the game being predicted. Level 2 uses prior games only. `K`, `PA`, `Outs`, and
`k_rate` are retained in Level 3 solely as labels/evaluation fields.

`src/mlb_props/features.py` validates explicit feature lists and selects only
numeric, non-identifier, non-label columns for the training script.

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
- FIP constants use FanGraphs published values, while xFIP league HR/FB uses
  all loaded pitchers.

## Context features

Opponent features aggregate each hitter's pregame overall/handed K%, whiff%,
and chase%. Historical membership uses players who appeared; live projections
must substitute the announced lineup.

Park factors are keyed by `(season, home_team)` and use prior seasons only.
The first available season is neutral. This prevents future park outcomes from
entering earlier rows.

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

- No leakage-free Level 3 baseline has been recorded.
- TBF projection and end-to-end prop backtesting are incomplete.
- Announced-lineup ingestion is not implemented.
- Batter-by-pitch-type arsenal interactions remain planned.
- Weather, travel/rest, catcher, and market inputs are not integrated.
