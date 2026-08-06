# Step 11 — production registry freeze (lineup discipline lift)

**Status:** frozen  
**Date:** 2026-08-03  
**Prior freeze:** Step 10 P1 physics swap (`step10_180`, 180 features)  
**Evidence:** `artifacts/feature_research/lgbm_lift_promotion/`,  
`artifacts/model_quality/lgbm_discipline_stack_compare.json`,  
`artifacts/feature_research/multi_lift_pre_freeze/`  
**Freeze artifact:** `artifacts/models/lightgbm_krate_20260803_155401.{txt,json}`  
**Registry CSV:** `artifacts/feature_research/step11_discipline_freeze/production_registry.csv`

## What locked

LightGBM **`production`** = Step 10 spine (**180**) **plus** four opposing-lineup
discipline nominees:

| Feature | Role |
|---|---|
| `opp_lineup_zswing_P10` | lineup Z-Swing% (10-game) |
| `opp_lineup_swing_P10` | lineup Swing% (10-game) |
| `opp_lineup_zcontact_P20` | lineup Z-Contact% (20-game) |
| `opp_lineup_bb` | lineup BB% (season-to-date) |

**Size: 184** features.

Companion registry **`step10_180`** keeps the prior freeze for bake-offs.
`production_plus_discipline` is a backward-compatible alias of `production`.

## Why these four

Nested LightGBM selection (both outer folds) improved k-rate MAE vs the 180
core; one-shot 2025 holdout and walk-forward mean expected_K also moved
favorably. Additive follow-ons on top of 184 (quality WD, age, pitcher
discipline, lineup vs-hand) did **not** clear the both-fold nested bar and
remain research-only.

## Parked research (do not delete)

| Track | Location |
|---|---|
| Lift vs 180 | `artifacts/feature_research/lgbm_lift_promotion/` |
| Multi-block vs 184 | `artifacts/feature_research/multi_lift_pre_freeze/` |
| Quality / discipline stabilizations | `artifacts/stabilization/expanded/` |
| Birthdates (Marcel / age digs) | `data/dimensions/player_birthdates.parquet` |
| Runner | `models/Strikeout-Model/research/multi_lift_pre_freeze.py` |
| Runner | `models/Strikeout-Model/research/lgbm_lift_promotion.py` |

Pipeline still generates pitcher Z-Swing/Swing/Z-Contact rolling and lineup
vs-hand discipline columns as **experimental** for future model pivots.
