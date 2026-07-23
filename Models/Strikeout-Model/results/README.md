# Model results

Central location for comparing model evaluations and holdout predictions.

## Contents

- `_baseline_2026-07-23/mean.json` — historical 227-feature mean baseline
- `_baseline_2026-07-23/ridge.json` — historical 227-feature Ridge baseline
- `_baseline_2026-07-23/GIT_STATE.txt` — generating commit and worktree state
- `Test-Predictions/test_predictions_v6_lgb.csv` — LightGBM holdout predictions

## Historical frozen baseline

| Model | MAE | RMSE | R² |
|---|---:|---:|---:|
| Mean | 0.0857 | 0.1074 | -0.0001 |
| Ridge | 0.0797 | 0.1002 | 0.1290 |

This snapshot is retained as process history but is superseded: its row-index
split divided boundary dates across partitions. The final 227-feature,
date-disjoint Mean/Ridge/LightGBM evaluations are recorded in `PAPER_NOTES.md`.
The fitted model and complete feature metadata are stored as
`artifacts/models/lightgbm_krate_20260723_202255.*`.

Prediction CSV columns are `game_date`, actual `k_rate`, `pred`, and `resid`.
