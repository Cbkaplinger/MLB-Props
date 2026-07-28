# Step 5 findings — binomial GLM arm

**Status:** complete for the L2-regularized binomial GLM challenger  
**Date:** 2026-07-27  
**Local artifacts (gitignored):** `artifacts/feature_research/step5_binomial/`  
**Runner:** `Models/Strikeout-Model/Strikeout-EDA/binomial_nested_compare.py`  
**Dependency:** `statsmodels` (now in `pyproject.toml` research extras)

## Verdict

On the same nested folds / 248-feature allow-list, an L2-regularized binomial
GLM (`K` successes / `PA` trials, `alpha=1.0`) **does not beat unweighted
LightGBM** on either game-level rate error or binomial negative log-likelihood.

| Arm | Mean unweighted MAE | Mean unweighted RMSE | Mean binomial NLL / PA |
|---|---:|---:|---:|
| LightGBM none | **0.0789** | **0.0996** | **0.5231** |
| LightGBM pa | 0.0793 | 0.0999 | 0.5233 |
| Binomial GLM | 0.0878 | 0.1077 | 0.5275 |
| Ridge none | 0.0838 | 0.1057 | 0.5361 |
| Ridge pa | 0.0854 | 0.1081 | 0.5532 |

So far in Step 5:

1. PA-weighting ≈ no gain (see `docs/step5_pa_weight_findings.md`)
2. Linear binomial GLM ≈ worse than unweighted LightGBM on rate **and** NLL

## Protocol notes

- Response: two-column `(K, PA−K)`; features exclude same-game `PA`/`K`
- Preprocessing: median impute + standardize (train-only), then intercept
- Penalty: statsmodels `fit_regularized` elastic net with `L1_wt=0` (ridge-like)
- Reference Ridge/LightGBM arms refit under the same research LGBM protocol
  (800 trees, no early stopping) and are scored with binomial NLL as well

## Interpretation

A coherent binomial likelihood does not automatically win when the mean model is
a linear logit on 248 correlated features. Tree-based `k_rate` regression still
produces better calibrated probabilities under the binomial scoring rule here.
Remaining Step 5 work is **beta-binomial** (extra-binomial dispersion) and,
optionally, alpha / compact-feature sensitivity for the GLM — not jumping to TBF.

## Pickup

```powershell
python Models/Strikeout-Model/Strikeout-EDA/binomial_nested_compare.py --alpha 1.0
```

## Sequencing reminder

- Step 5 remainder: beta-binomial challenger (now complete — see
  `docs/step5_beta_binomial_findings.md`).
- Steps 1–10 closed for LightGBM; TBF + count layer chrono-scored.
- Remaining critical path: Phase 11 model quality (tune / walk-forward /
  calibrate), then Phase D + pristine post-freeze eval
  (`docs/phase11_model_quality_gates.md`, `diagrams/04-roadmap.md`).

## Artifact consolidation note

The generated `artifacts/feature_research/step5_binomial/SUMMARY.md` pointed
only at this write-up and the regenerate command. It contained no unique
analysis. Removed on 2026-07-28; keep the numeric evidence tables/metadata
under `step5_binomial/`.
