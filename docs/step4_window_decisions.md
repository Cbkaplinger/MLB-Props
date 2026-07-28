# Step 4 findings — provisional window decisions

**Status:** resolved for LightGBM backbone  
**Date:** 2026-07-27  
**Evidence:**
- `artifacts/feature_research/targeted_window_ablation_*` (BABIP / arm angle / RV)
- `artifacts/feature_research/step4_physics_windows/` (mean-window thinning)
**Runners:**
- `Models/Strikeout-Model/Strikeout-EDA/targeted_window_ablation.py`
- `Models/Strikeout-Model/Strikeout-EDA/physics_window_ablation.py`

## Scope

Decisions are for the **unweighted LightGBM** rate backbone (Step 5). Ridge
remains a research diagnostic only; Ridge-specific window picks do not block
registry freeze.

## Decisions

| Item | Decision | Evidence |
|---|---|---|
| **BABIP** | Keep experimental defaults `P5/P10/P20`. Do **not** add P30/P35. Do **not** promote into production on this gate. | LGBM selected metric-core in **both** outer folds (no positive MAE fold for longer windows). |
| **Arm angle** | Keep experimental defaults `P3/P5/P10`. Do **not** add P2. Do **not** promote into production on this gate. | LGBM selected P3 in one fold (`+0.000027` MAE) and core in the other; not durable. |
| **Run value (`rv_per_100`)** | LGBM-only registry proposal: add **`rv_per_100_P25`** if/when the family is promoted. Do **not** change module-wide mean defaults for Ridge. Leave current experimental `P3/P5/P10` until freeze wiring. | LGBM selected P25 in **both** outer folds; MAE improvements `0.000032` / `0.000603`. Ridge mixed and never improved outer MAE. |
| **Physics / usage / mechanics / FIP mean windows** | LGBM registry proposal: thin production mean-window families from **`P3/P5/P10` → `P3/P5`** (drop P10). Keep pipeline constant until Step 7 applies the proposal. | Outer LGBM screen: `mean_P3_P5` best mean ΔMAE **−0.000369** vs full triple, improved both folds. Dropping the families entirely hurts on average (+0.000931). |

## Physics thinning headline (LightGBM, mean over two outer folds)

Positive ΔMAE = config **worse** than full `P3/P5/P10`.

| Configuration | Mean ΔMAE vs full | Notes |
|---|---:|---|
| mean_P3_P5 | **−0.000369** | Best; both folds improved |
| mean_P3_only | −0.000309 | Close second |
| mean_P3_P10 | −0.000252 | Still beats full |
| full_P3_P5_P10 | 0 | Current production |
| mean_P5_P10 | +0.000136 | Dropping short P3 hurts |
| drop_mean_families | +0.000931 | Families still useful overall |

Rates (`P5/P10/P20`) and lineup windows were out of scope here: rates already
have adequate/gap mapping for studied metrics, and lineup nominees were fixed
in earlier batter screens.

## What does **not** change in the rolling pipeline

- `DEFAULT_RATE_WINDOWS = (5, 10, 20)` and `DEFAULT_MEAN_WINDOWS = (3, 5, 10)`
  still generate columns in Level 2.
- Step 7 **drops mean-family P10 from the LightGBM feature set** without
  rebuilding parquet (`docs/step7_registry_freeze.md`).
- BABIP / arm angle / RV remain **experimental** (`is_experimental_feature`).
- Rest / bullpen / intangibles stay on the **TBF track**.

## Freeze handoff — **applied in Step 7**

1. Mean-window thin applied: physics, usage, mechanics, FIP/xFIP → **P3 + P5**
   in the frozen production registry.
2. Run value **not** promoted (`rv_per_100_P25` still research-only).
3. BABIP and arm angle remain out of production.
4. Ridge window disagreement did not block freeze.

## Artifact consolidation note

The generated `artifacts/feature_research/step4_physics_windows/SUMMARY.md`
duplicated the verdict already captured above: `mean_P3_P5` beats full
`P3/P5/P10` (mean ΔMAE −0.000369; both folds improved), so freeze drops P10
from those mean-window families. The summary markdown was removed on
2026-07-28; retain `aggregate.csv`, `outer_results.csv`, and `metadata.json`.
