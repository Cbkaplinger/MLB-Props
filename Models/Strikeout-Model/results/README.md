# Model results

Active model evaluations are written with their generated artifacts under
`artifacts/models/`. This directory documents where historical result evidence
was relocated during repository cleanup.

## Contents

- `docs/archive/leaky-baseline-2026-07-23/` — Mean/Ridge JSON and generating
  worktree state for the invalid overlapping-date split
- `docs/archive/pre-pipeline-v6/` — pre-pipeline SHAP output containing
  forbidden same-game/unlagged fields
- `artifacts/models/lightgbm_krate_20260724_165215.*` — current 248-feature
  2023-2024 development LightGBM model and metadata
- `artifacts/models/lightgbm_krate_20260723_202255.*` — historical
  227-feature, 2025-consulting LightGBM benchmark

## Superseded baseline

| Model | MAE | RMSE | R² |
|---|---:|---:|---:|
| Mean | 0.0857 | 0.1074 | -0.0001 |
| Ridge | 0.0797 | 0.1002 | 0.1290 |

This table is retained as process history only. Its row-index split divided
boundary dates across partitions, so it is not valid current performance
evidence.

## Historical 2025-consulting benchmark

| Model | Features | Train end | Validation | Test start | RMSE | R² |
|---|---:|---|---|---|---:|---:|
| Mean | 227 | 2025-04-14 | 2025-04-15–2025-07-05 | 2025-07-06 | 0.1076 | -0.0001 |
| Ridge | 227 | 2025-04-14 | 2025-04-15–2025-07-05 | 2025-07-06 | 0.1003 | 0.1313 |
| LightGBM | 227 | 2025-04-14 | 2025-04-15–2025-07-05 | 2025-07-06 | 0.0994 | 0.1459 |

`PAPER_NOTES.md` is the canonical result log. No current holdout-prediction CSV
is claimed here.

## Current 2023-2024 development baseline

The current production gate contains 248 features. The latest LightGBM
development run trains, validates, and internally tests only on 2023-2024:
training ends 2024-06-08, validation covers 2024-06-09 through 2024-08-05, and
internal testing starts 2024-08-06. Internal-test MAE / RMSE / R² are
`0.07834` / `0.09829` / `0.15462`.

This is the active development baseline, but not a new independent final test.
The next final evaluation requires genuinely future post-freeze games.
