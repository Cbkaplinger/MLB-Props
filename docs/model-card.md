# Pitcher strikeout model card

## Intended use

Estimate a starting pitcher's pregame strikeout rate. A separate estimate of
batters faced (TBF) converts that rate into an expected strikeout count:

```text
expected strikeouts = predicted strikeout rate × projected TBF
```

The project is research code. It is not yet a production betting system.

## Target and evaluation

- Target: strikeouts divided by plate appearances (`K / PA`) for a start.
- Split: chronological train, validation, and test periods.
- Primary rate metrics: MAE, RMSE, and R² on unseen future starts.
- Prop evaluation must use **projected** TBF. Actual same-game PA or TBF may
  only be used after prediction to score results.
- Probability quality should be checked with calibration and proper scoring
  rules before using estimated edges.

## Leakage policy

Every model input must be available before first pitch. Same-game outcomes are
forbidden, including:

- `PA`
- `K`
- actual TBF or actual strikeouts
- any feature calculated with data from the start being predicted

Lagged rolling features such as `PA_P5` are allowed when their calculation uses
`shift(1)` before rolling. `src/mlb_props/features.py` enforces the explicit
forbidden-feature list.

## Current limitations

- Metrics saved in existing notebook outputs predate removal of same-game `PA`
  and must not be treated as valid pregame performance.
- The repository does not yet contain a frozen, reproducible v9 model artifact.
- TBF projection and honest end-to-end prop backtesting are incomplete.
- Opponent lineup, park, rest, weather, and market-price inputs are not yet
  integrated.
- Feature selection contains many correlated rolling-window measurements and
  should be revisited only after a leakage-free baseline is retrained.

## Retraining gate

Do not publish new performance claims until the model has been retrained
without forbidden features and evaluated chronologically with projected TBF.
