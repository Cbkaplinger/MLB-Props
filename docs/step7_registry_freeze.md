# Step 7 — LightGBM registry freeze (historical)

**Status:** superseded by Step 10 P1 freeze (`docs/step10_p1_registry_freeze.md`)  
**Date:** 2026-07-27 (original); retained as feature set `step7_185`  
**Original artifact:** `artifacts/models/lightgbm_krate_20260727_204342.{txt,json}`  
**Feature set then:** 185 features (mean P10 thin only)

## What we did with windows

Step 4 showed `P3+P5` beats the full `P3/P5/P10` triple for physics / usage /
mechanics / FIP. Step 7 applied that thin at feature selection (drop 63 mean
`*_P10` columns). Rate windows `P5/P10/P20` were left alone.

## Locked freeze record (Step 7 era)

| Field | Value |
|---|---|
| Features | **185** |
| Sample weight | `none` |
| Test MAE / RMSE / R² | 0.0787 / 0.0986 / 0.149 |

## Current companion registries

| Set | Size | Use |
|---|---:|---|
| `production` | **180** | **Current** — Step 7 + Step 9c/10 P1 swap |
| `step7_185` | 185 | This freeze (comparison) |
| `pre_freeze_248` | 248 | Pre-thin allow-list |
| `ridge_vif` | 73 | Ridge research |

```powershell
python Models/Strikeout-Model/train.py --model lightgbm --feature-set production
python Models/Strikeout-Model/train.py --model lightgbm --feature-set step7_185
```
