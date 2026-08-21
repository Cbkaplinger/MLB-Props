# First projected-TBF model — freeze decision

**Status:** **frozen** for paper / props spine  
**Date:** 2026-07-27  
**Trainer:** `models/TBF-Model/train.py`  
**Frozen choice:** **Ridge** + **`workload_context_bullpen`** (thin pen, 24 features)  
**Target:** same-game `PA` (historical TBF oracle)

## Why this freeze (paper-ready)

| Contender | Test MAE | Test RMSE | Test R² | Notes |
|---|---:|---:|---:|---|
| **Ridge + thin bullpen** | **2.490** | **3.279** | **0.162** | **selected** |
| Ridge + context only | 2.494 | 3.279 | 0.162 | nearly tied; pen adds small lift |
| Ridge + rich bullpen | 2.492 | 3.283 | 0.159 | more features, no gain |
| Poisson / Elastic Net / LGBM | ≥2.494 | ≥3.282 | ≤0.160 | no clear win |

Primary metric for props = **MAE**. RMSE/R² agree that thin Ridge is best or tied.
R² ≈ 0.16 reflects starter-PA noise (SD ≈ 3.6), not under-modeling.

Rich bullpen (L/R, B2B, max, heavy) stays available as
`workload_context_bullpen_rich` for ablation / live UI — not the spine.

## Feature set (frozen)

`workload_context_bullpen` = rest (A/A.1) + lagged `PA/Outs/Pitches` P5/P10/P20
+ home/park/lineup K + `bullpen_pitches_L{1,2,3}d` + `bullpen_pitchers_used_L{1,2,3}d`.

Same-game `PA` is never a predictor.

## Next step (do this next)

**Live assembly + Phase D** — see `docs/diagrams/04-roadmap.md`.

Count layer first pass is done (`docs/research/count_layer_findings.md`). Projected TBF
beat `PA_P5` / mean-PA exposures on chrono test. Product work is slate scoring
and opener caveats — not more TBF feature hunting.

## Pickup

```powershell
python models/TBF-Model/train.py --model ridge --feature-set workload_context_bullpen
```
