# SSAC27 Item 5 — N=5161 enumeration

**Date:** 2026-09-01  
**Pinned count:** `artifacts/odds_log/quant_honesty_aug21_summary.json` → `n_trials = 5161`  
**Exact enumeration source:** `artifacts/odds_log/ensemble_sweep_ranked_ensemble_full_aug21_deduped.csv` (**5161 rows**)

## What 5161 is (and is not)

**Is:** the number of **eligible blend × edge-floor configurations** evaluated in the Aug-21 deduped open-universe ensemble sweep after the `min_bets ≥ 25` gate.

**Is not:** Optuna hyperparameter trials, model-family architecture search counts, or feature-subset enumerations. Earlier manuscript wording that implied “feature-set × model-family × hyperparameter draws” was imprecise and is corrected below.

## Regenerable arithmetic

Producer: `production/ops/run_model_ensemble_sweep.py`  
Metadata: `artifacts/odds_log/ensemble_sweep_ensemble_full_aug21_deduped.json`

| Factor | Value |
| --- | --- |
| Feature-set lanes in the blend simplex | 3 — `production_sparse72`, `production_sparse72_monotone`, `production_final58_consensus` |
| Calibration mode | isotonic (fixed) |
| Weight grid | step `0.05` on the 3-simplex → **231** blends |
| Edge floors | `0.005` … `0.12` step `0.005` → **24** floors |
| Full Cartesian grid | **231 × 24 = 5544** (`rows_total` in metadata; full CSV) |
| Eligibility gate | `n_bets ≥ 25` on deduped manual tickets |
| Dropped ineligible | **383** |
| **Eligible / ranked (= N)** | **5544 − 383 = 5161** |

Verification (2026-09-01):

```text
len(ranked CSV) == 5161
len(full CSV filtered n_bets >= 25) == 5161
```

## Implication for DSR

The Deflated Sharpe Ratio in `quant_honesty_aug21_summary.json` deflates the audited lane’s Sharpe using **this policy-search breadth** (blend×floor configs), not a model-training trial count. That is the correct object for a *decision-policy* DSR, but it must be stated explicitly so readers do not confuse it with Optuna `n_trials`.

## Manuscript action

Update §8.2 DSR provenance to this enumeration and cite the ranked CSV + sweep metadata as the auditable source.
