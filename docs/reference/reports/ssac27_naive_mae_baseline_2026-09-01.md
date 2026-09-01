# SSAC27 Item 6 — Chronological naive `k_rate` baselines (2026-09-01)

**Producer:** `models/Strikeout-Model/research/marcel_baseline.py`  
**Outputs:** `artifacts/feature_research/marcel_baseline/`

## Chronological game-level lane (same split as registry freeze test start)

| Partition | Baseline | MAE | RMSE | R² | n |
| --- | --- | ---: | ---: | ---: | ---: |
| test | marcel (3/2/1 + EB regress, no age) | **0.08257** | 0.10340 | 0.0644 | 1413 |
| test | prior_season_only | 0.08301 | 0.10384 | 0.0564 | 1413 |
| test | train_mean | 0.08538 | 0.10696 | −0.0010 | 1413 |
| validation | marcel | 0.08209 | 0.10260 | 0.0428 | 1404 |
| validation | train_mean | 0.08374 | 0.10497 | −0.0018 | 1404 |

Frozen LightGBM **reference** on the same test window (not re-fit here): MAE ≈ **0.0787** (`docs/research/step10_p1_registry_freeze.md`).

Same-lane train_mean on `pitcher_training.parquet` chronological test: `k_rate` MAE ≈ **0.08538**; `expected_K` (= `k_rate × PA`) MAE ≈ **1.92** (train-mean rate × observed PA vs realized K).

## Relation to Table 2a (sparse72 model-family)

Table 2a ridge sparse72 MAE **0.07668** is a **different protocol** (outer-fold sparse-set family ablation), not the Marcel chronological split. Do **not** subtract Table 2a − Marcel as a single delta without fold-aligned predictions.

Manuscript treatment: keep Table 2a as challenger screen; add **Table 2b** chronological naive baselines so readers see delta-over-naive on an auditable lane (LGBM freeze 0.0787 vs Marcel 0.08257 ≈ **−0.0039** absolute MAE).
