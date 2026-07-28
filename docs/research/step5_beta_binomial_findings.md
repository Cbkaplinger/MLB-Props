# Step 5 findings — beta-binomial arm

**Status:** complete for the two-stage beta-binomial challenger  
**Date:** 2026-07-27  
**Local artifacts (gitignored):** `artifacts/feature_research/step5_beta_binomial/`  
**Runner:** `models/Strikeout-Model/research/beta_binomial_nested_compare.py`

## Verdict

Two-stage beta-binomial (fixed mean + global concentration `kappa` MLE) does
**not** overturn unweighted LightGBM on the nested 2023–2024 folds.

| Arm | Mean unweighted MAE | Mean binomial NLL/PA | Mean BB NLL/PA | Mean κ |
|---|---:|---:|---:|---:|
| LightGBM none | **0.0789** | **0.5231** | **0.0976** | ~1e6 (bound) |
| LightGBM pa | 0.0793 | 0.5233 | 0.0978 | ~1e6 (bound) |
| Beta-binomial (GLM mean) | 0.0878 | 0.5275 | 0.1000 | ~41 |
| Binomial GLM | 0.0878 | 0.5275 | 0.1000 | ~41 |
| Ridge none | 0.0838 | 0.5361 | 0.1034 | ~123 |

## Interpretation

1. **With LightGBM means, κ hits the upper search bound (~1e6).** That is the
   binomial limit: once the mean model is strong, there is little evidence here
   for a global extra-binomial dispersion parameter.
2. **With the weaker binomial-GLM mean, κ ≈ 41.** Residual overdispersion shows
   up when the mean is misspecified; a better mean absorbs it.
3. **Step 5 likelihood sequence (regression / PA-weight / binomial / BB) is
   closed for decision-making:** keep **unweighted LightGBM** as the rate
   backbone. PA-weighting and linear binomial/BB GLMs are finished diagnostics,
   not replacements.

## Protocol

- Same `nested_research_folds` and 248-feature production allow-list
- BB = stage-1 mean + stage-2 `kappa` fit on training rows only
- Reference arms refit under research LGBM protocol (800 trees, no early stop)
- Same-game `PA`/`K` used only in the response likelihood

## Pickup

```powershell
python models/Strikeout-Model/research/beta_binomial_nested_compare.py
```

## What is next (priority)

1. Phase 11 model quality — tune / walk-forward / calibrate
   (`docs/research/phase11_model_quality_gates.md`).
2. Phase D opener/piggyback before pristine holdout claims.
3. Pristine eval = future post-freeze games only (not recycled 2025).
4. Live assembly only after Phase 11 gates (or waiver).

## Artifact consolidation note

The generated `artifacts/feature_research/step5_beta_binomial/SUMMARY.md` was
redundant with this findings doc. Removed on 2026-07-28; retain
`aggregate` / `inner` / `outer` / `metadata` under `step5_beta_binomial/`.
