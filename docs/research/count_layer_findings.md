# Count layer — expected_K = k_rate × projected_tbf

**Status:** historical baseline evaluation + current lane alignment note  
**Date:** 2026-07-27  
**Runner:** `models/Strikeout-Model/score_count_layer.py`  
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

## Lane alignment (read this first)

- The table below (`expected_K MAE = 1.790`) is a **legacy baseline lane**
  snapshot.
- Current **single-model MAE lane** best observed value is `~1.7621` from
  later sparse-set model-family ablation/governance artifacts.
- Current **live deployment lane** winner is a weighted ensemble selected on
  decision metrics (ROI/risk/market-skill), not expected-K MAE rank alone.

## Inputs (frozen)

| Piece | Choice |
|---|---|
| k-rate | Historical legacy single-model baseline (`184` freeze lineage) |
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
python models/Strikeout-Model/score_count_layer.py
python -m pytest tests/test_count_layer.py -q
```

## Next (after this)

1. ~~**Phase 11** — tune / walk-forward / calibrate~~ — done (confirmatory;
   `docs/research/phase11_model_quality_gates.md`).
2. ~~**Phase D** interim population policy~~ — done
   (`docs/research/phase_d_population_findings.md`).
3. ~~**Post-hoc `p_over_*` calibration (Platt)**~~ — production pointer set
   (`docs/research/prob_calibration_findings.md`). Raw binomial probs retained;
   `p_over_*_cal` feeds fair odds / edge.
4. Live / slate scoring (`docs/reference/live_assembly_plan.md`) — shipped.
5. Pregame role labels before pristine post-freeze holdout claims.
6. Optional product: de-vig market lines + fractional Kelly (paper CLV sample
   building; 8% floor locked until n≥100 clean props).
7. Do **not** dump bullpen into k-rate until a nested promotion screen says so.
8. Optional count-distribution challengers (NB / mixture-over-TBF) if live ECE
   regresses after Platt.
