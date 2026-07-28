# Model results

Active model evaluations are written with their generated artifacts under
`artifacts/models/`. This directory documents where historical result evidence
was relocated during repository cleanup.

## Contents

- `docs/archive/leaky-baseline-2026-07-23/` — Mean/Ridge JSON and generating
  worktree state for the invalid overlapping-date split
- `docs/archive/pre-pipeline-v6/` — pre-pipeline SHAP output containing
  forbidden same-game/unlagged fields
- `artifacts/models/lightgbm_krate_20260728_033241.*` — **frozen** 180-feature
  LightGBM production (Step 10 P1 swap)
- `artifacts/models/lightgbm_krate_20260727_204342.*` — Step 7 era 185-feature
  freeze (comparison / `step7_185`)
- `artifacts/models/lightgbm_krate_20260724_165215.*` — pre-freeze 248-feature
  2023-2024 development LightGBM (comparison / process history)
- `artifacts/models/lightgbm_krate_20260723_202255.*` — historical
  227-feature, 2025-consulting LightGBM benchmark
- TBF + count layer: see `docs/research/tbf_first_model_findings.md` and
  `docs/research/count_layer_findings.md` (`artifacts/models/tbf_pa_*`,
  `artifacts/count_layer/`)

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

`docs/research/PAPER_NOTES.md` is the canonical result log. No current holdout-prediction CSV
is claimed here.

## Current frozen production (2026-07-28)

Frozen LightGBM `production` = **180** features (Step 10 P1 physics swap on
top of Step 7 mean-window thin). Chrono cutoffs: train ≤ 2024-06-08, val
2024-06-09→08-05, test ≥ 2024-08-06. Test MAE / RMSE / R² ≈
**0.0787 / 0.0987 / 0.147** (`docs/research/step10_p1_registry_freeze.md`).

This is the active frozen *feature* baseline, not a pristine final test and
not a claim that hyperparameters or stack calibration are finished. Next:
Phase 11 (`docs/research/phase11_model_quality_gates.md`). Honest final evaluation
requires genuinely future post-freeze games (and Phase D population policy).
