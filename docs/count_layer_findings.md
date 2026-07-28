# Count layer — expected_K = k_rate × projected_tbf

**Status:** first chrono evaluation complete (research; not live betting)  
**Date:** 2026-07-27  
**Runner:** `Models/Strikeout-Model/score_count_layer.py`  
**Code:** `src/Python/count_layer.py`  
**Artifact:** `artifacts/count_layer/count_layer_*.json`

## What this is

TBF is **not** a prop. It supplies pregame exposure for strikeout **counts**:

```text
expected_K = frozen_k_rate × projected_tbf
P(K ≥ line) ← Binomial / Poisson / beta-binomial with n = round(projected_tbf)
```

Same-game `PA` never enters prop probabilities. `kappa` is fit on **train** with
historical PA trials + predicted rate (Step 5 two-stage); at score time trials
switch to projected TBF.

## Inputs (frozen)

| Piece | Choice |
|---|---|
| k-rate | Step-10 LightGBM `production` (**180**, P1 swap) — `lightgbm_krate_20260728_033241` |
| projected_tbf | Ridge + `workload_context_bullpen` (thin pen, 24 feats) |

## Test partition (from 2024-08-06) — expected_K vs actual K

| Exposure | MAE | RMSE | R² |
|---|---:|---:|---:|
| **`projected_tbf`** | **1.790** | **2.213** | **0.168** |
| `PA_P5` | 1.802 | 2.229 | 0.156 |
| train-mean PA | 1.822 | 2.252 | 0.138 |

Projected TBF beats both simple exposure baselines.

## Line probs (test, binomial; BB identical — κ ≈ 1e6 → binomial limit)

| Line | Base rate | Acc (p≥0.5) | Brier | Log loss |
|---|---:|---:|---:|---:|
| 3.5 | 0.709 | 0.729 | 0.184 | 0.547 |
| 4.5 | 0.558 | 0.657 | 0.221 | 0.633 |
| 5.5 | 0.393 | 0.655 | 0.214 | 0.615 |
| 6.5 | 0.256 | 0.746 | 0.175 | 0.526 |
| 7.5 | 0.158 | 0.844 | 0.124 | 0.399 |

Poisson is essentially tied (slightly better Brier on some lines). With a strong
k-rate mean, global BB dispersion is not needed (same story as Step 5).

## Pickup

```powershell
python Models/Strikeout-Model/score_count_layer.py
python -m pytest tests/test_count_layer.py -q
```

## Next (after this)

1. ~~**Phase 11** — tune / walk-forward / calibrate~~ — done (confirmatory;
   `docs/phase11_model_quality_gates.md`).
2. ~~**Phase D** interim population policy~~ — done
   (`docs/phase_d_population_findings.md`).
3. Live / slate scoring (`docs/live_assembly_plan.md`) — optional next.
4. Pregame role labels before pristine post-freeze holdout claims.
5. Optional product: de-vig market lines + fractional Kelly (after prices).
6. Do **not** dump bullpen into k-rate until a nested promotion screen says so.
