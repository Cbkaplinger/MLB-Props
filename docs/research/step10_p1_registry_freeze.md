# Step 9c / 10 — production registry lock (P1 physics swap)

**Status:** frozen  
**Date:** 2026-07-28  
**Evidence:** `docs/research/step9_metric_window_findings.md` (Step 9c)  
**Freeze artifact:** `artifacts/models/lightgbm_krate_20260728_033241.{txt,json}`  
**Registry CSV:** `artifacts/feature_research/step10_p1_freeze/production_registry.csv`

## What locked

LightGBM **`production`** is Step 7 mean-window thin **plus** Step 9c’s
five-stem last-start swap:

| Stem | Was | Now |
|---|---|---|
| `ff_velo` | P3, P5 | **P1** |
| `cu_vaa` | P3, P5 | **P1** |
| `cu_usage_vR` | P3, P5 | **P1** |
| `fs_usage_vR` | P3, P5 | **P1** |
| `sl_vaa` | P3, P5 | **P1** |

**Size: 180** features (185 − 10 P3/P5 + 5 P1).

Level 2 `DEFAULT_MEAN_WINDOWS = (1, 3, 5, 10)` generates P1 for all mean stems;
the production registry **consumes P1 only for the five stems above** (other
`*_P1` columns are ignored).

## Freeze fit (2023–2024 chrono)

| Partition | MAE | RMSE | R² |
|---|---:|---:|---:|
| Validation | 0.0764 | 0.0966 | 0.151 |
| Test | 0.0787 | 0.0987 | 0.147 |

Research bake-off of the same swap vs `step7_185` (earlier session): k-rate MAE
0.07842 vs 0.07863; expected_K MAE 1.769 vs 1.773.

## Companion registries

| Set | Size | Use |
|---|---:|---|
| `production` | 180 | **Current** LightGBM default |
| `step7_185` | 185 | Pre-P1 freeze |
| `pre_freeze_248` | 248 | Pre-Step-7 allow-list |
| `ridge_vif` | 73 | Ridge research |

```powershell
python -m Python.pipeline.rolling
python -m Python.pipeline.training
python Models/Strikeout-Model/train.py --model lightgbm --feature-set production
```

## Next

**Phase 11 — model quality** (not live assembly): tune LightGBM + TBF on the
frozen 180-feature spine → walk-forward stack backtest → calibration.
Canonical plan: `docs/research/phase11_model_quality_gates.md`. Live inference follows
those gates (`docs/reference/live_assembly_plan.md`).
