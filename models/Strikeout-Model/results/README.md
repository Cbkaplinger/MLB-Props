# Model results

Active model evaluations are written with their generated artifacts under
`artifacts/models/`. This directory documents where historical result evidence
was relocated during repository cleanup.

## Contents

- `docs/archive/leaky-baseline-2026-07-23/` — Mean/Ridge JSON and generating
  worktree state for the invalid overlapping-date split
- `docs/archive/pre-pipeline-v6/` — pre-pipeline SHAP output containing
  forbidden same-game/unlagged fields
- `production/ops/live_krate_ensemble.json` — active live k-rate blend config
  (manual-lane winner transfer)
- `artifacts/models/lightgbm_krate_20260821_054152.*` — sparse72 member used by
  current live blend (weight 0.00; retained for explicit blend provenance)
- `artifacts/models/lightgbm_krate_mono_20260821_054127.*` — sparse72_monotone
  member used by current live blend (weight 0.60)
- `artifacts/models/lightgbm_krate_20260821_054126.*` — final58_consensus member
  used by current live blend (weight 0.40)
- `artifacts/models/lightgbm_krate_20260803_155401.*` — **frozen** 184-feature
  LightGBM single-model baseline (Step 11 discipline lift; fallback path)
- `artifacts/models/lightgbm_krate_20260728_033241.*` — prior Step 10 freeze
  (180; comparison / `step10_180`)
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

## Current frozen production (2026-08-03)

Frozen LightGBM `production` = **184** features (Step 10 P1 spine + four
opposing-lineup discipline nominees). Chrono cutoffs: train ≤ 2024-06-08, val
2024-06-09→08-05, test ≥ 2024-08-06. Test MAE / RMSE / R² ≈
**0.0780 / 0.0982 / 0.156** (`docs/research/step11_discipline_registry_freeze.md`).

Prior Step 10 freeze (`step10_180`, artifact `lightgbm_krate_20260728_033241`)
remains available for bake-offs. Research screens for quality-WD / age /
pitcher discipline / vs-hand stay parked under
`artifacts/feature_research/`.
