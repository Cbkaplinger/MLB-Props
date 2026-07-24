# Model results

Active model evaluations are written with their generated artifacts under
`artifacts/models/`. This directory documents where historical result evidence
was relocated during repository cleanup.

## Contents

- `docs/archive/leaky-baseline-2026-07-23/` — Mean/Ridge JSON and generating
  worktree state for the invalid overlapping-date split
- `docs/archive/pre-pipeline-v6/` — pre-pipeline SHAP output containing
  forbidden same-game/unlagged fields
- `artifacts/models/lightgbm_krate_20260723_202255.*` — corrected frozen
  LightGBM model and complete feature/evaluation metadata

## Superseded baseline

| Model | MAE | RMSE | R² |
|---|---:|---:|---:|
| Mean | 0.0857 | 0.1074 | -0.0001 |
| Ridge | 0.0797 | 0.1002 | 0.1290 |

This table is retained as process history only. Its row-index split divided
boundary dates across partitions, so it is not valid current performance
evidence.

## Current date-disjoint baseline

| Model | Features | Train end | Validation | Test start | RMSE | R² |
|---|---:|---|---|---|---:|---:|
| Mean | 227 | 2025-04-14 | 2025-04-15–2025-07-05 | 2025-07-06 | 0.1076 | -0.0001 |
| Ridge | 227 | 2025-04-14 | 2025-04-15–2025-07-05 | 2025-07-06 | 0.1003 | 0.1313 |
| LightGBM | 227 | 2025-04-14 | 2025-04-15–2025-07-05 | 2025-07-06 | 0.0994 | 0.1459 |

`PAPER_NOTES.md` is the canonical result log. No current holdout-prediction CSV
is claimed here.
