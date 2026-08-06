# Step 1 findings — feature dictionary / VIF keep-drop

**Status:** resolved (dual-registry policy; LightGBM production now **184** via Step 11)  
**Date:** 2026-07-25 (amended 2026-08-03)  
**Date:** 2026-07-27 (Step 1); production size updated 2026-07-28  
**Code:** `src/Python/registries.py`, `scripts/finalize_step1_registries.py`  
**Artifacts:** `artifacts/feature_research/step1_registries/`  
**Trainer:** `python Models/Strikeout-Model/train.py --feature-set {production,step7_185,pre_freeze_248,ridge_vif}`

## Decisions

| Registry | Size | Decision |
|---|---:|---|
| **LightGBM `production`** | **184** | **Current freeze (Step 11).** Step 10 P1 spine (180) + four lineup-discipline nominees. See `docs/research/step11_discipline_registry_freeze.md`. |
| **LightGBM `step10_180`** | **180** | Prior freeze (Step 7 thin + Step 9c/10 P1). |
| **`step7_185`** | 185 | Pre-P1 freeze retained for bake-offs (`docs/research/step7_registry_freeze.md`). |
| **`pre_freeze_248`** | 248 | Prior full allow-list for comparisons only. |
| **Ridge `ridge_vif`** | 73 | **Adopt** Phase-1 VIF cluster reduction (74), then **drop `xFIP_P5`**. **Keep `xwOBA_P5`** with one accepted residual VIF > 10. |

See `docs/research/step10_p1_registry_freeze.md` for the locked artifact and metrics.

### Unresolved clusters (closed)

| Feature | Action | Why |
|---|---|---|
| `xFIP_P5` | **Drop** from Ridge registry | Collinear with retained `FIP_P5`. |
| `xwOBA_P5` | **Keep** (flagged) | Expected-contact representative; forcing VIF < 10 is not the goal. |

## Missingness / dictionary gaps

- Wrote `missingness_by_season.csv` for the pre-freeze list (2023–2024).
- Hand-curated numerator / denominator / availability-date enrichment remains
  **deferred** optional dictionary work.

## Artifact consolidation note

The generated `artifacts/feature_research/step1_registries/SUMMARY.md` was a
transient runner summary (originally listing production 248 / freeze proposal
185 / ridge_vif 73). Its substantive conclusions are already documented here
and in `docs/research/step11_discipline_registry_freeze.md` (current production is **184**).
The markdown summary wrapper was removed on 2026-07-28; keep the CSV/JSON
evidence under `step1_registries/`.
