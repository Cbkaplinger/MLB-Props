# Step 3 findings — leave-family-out ablation

**Status:** major Step 3 evidence landed (production 248-feature allow-list)  
**Date:** 2026-07-27  
**Local artifacts:** `artifacts/feature_research/leave_family_out/`  
**Runner:** `models/Strikeout-Model/research/leave_family_out_ablation.py`

## Protocol

- Outer nested folds only (`nested_research_folds`); 2025 not read
- Full model = all 248 production features
- Positive `delta_mae` = dropping the family **hurt** (family is useful)
- Structural tests: drop all `_P*` rolling columns, or drop all `_std` columns

## Headline (mean over two outer folds)

### LightGBM (keep full as baseline)

| Configuration | Mean ΔMAE vs full | Interpretation |
|---|---:|---|
| drop_lineup | **+0.00254** | Strongest hurt — lineup is load-bearing |
| drop_rolling (keep STD/static) | **+0.00125** | Rolling windows matter for trees |
| drop_pitch_physics | +0.00052 | Modest hurt |
| drop_park / drop_context / drop_usage | ~+0.0002–0.0003 | Small but consistent direction |
| drop_fip_xfip | −0.00029 | Slightly better without FIP/xFIP |
| full | 0 | — |

### Ridge

| Configuration | Mean ΔMAE vs full | Interpretation |
|---|---:|---|
| drop_lineup | **+0.00231** | Same story — lineup hurts when removed |
| drop_park / drop_context | small + | Tiny contribution |
| drop_rolling (keep STD/static) | **−0.00598** | Ridge **improves** without overlapping windows (multicollinearity) |
| drop_pitch_physics / rates / … | negative Δ | Many families look harmful under unpenalized-overlap Ridge |

## Takeaways for sequencing

1. **Opponent lineup is the clearest keep** for both models.
2. **LightGBM wants rolling windows**; Ridge prefers a much thinner / less
   overlapping design (aligns with the VIF-reduced Ridge proposal).
3. **Park and home/context** are small but not zero for LGBM.
4. **FIP/xFIP** is not helping LightGBM on these folds.
5. Step 4 window work should focus on **which rolling lengths to keep for
   LGBM**, not “rolling vs none” — rolling already wins for the production
   backbone.

## Next

- Fill `PAPER_NOTES.md` §6 table from `aggregate.csv` — done
- Step 4 window decisions — **done** (`docs/research/step4_window_decisions.md`)
