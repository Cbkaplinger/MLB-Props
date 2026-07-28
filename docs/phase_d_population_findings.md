# Phase D — opener / piggyback population hygiene

**Status:** interim policy frozen (pregame role labels still missing)  
**Date:** 2026-07-28  
**Runner:** `Models/Strikeout-Model/Strikeout-EDA/phase_d_population_audit.py`  
**Artifact:** `artifacts/model_quality/phase_d_population/`

## Problem

`MIN_STARTER_BATTERS_FACED = 9` is a **postgame** filter used to define rows for a
**pregame** model. It does not leak feature values, but it conditions every
reported metric on “first pitchers who ultimately faced ≥9 batters.” Openers,
piggybacks, early hooks, and injury exits are systematically excluded.

## Audit (2023–2024 first-pitcher appearances)

Rebuilt with `min_batters_faced=0` from Statcast (`BUILD_COLUMNS`).

| Cohort | N | Share | PA mean | K-rate mean |
|---|---:|---:|---:|---:|
| All first pitchers | 9,714 | 100% | — | — |
| Research (`PA ≥ 9`) | 9,374 | **96.5%** | 22.6 | 0.220 |
| Excluded (`PA < 9`) | 340 | **3.5%** | 5.5 | 0.238 |
| Heuristic opener-like (`PA ≤ 6`) | 226 | 2.3% | — | — |
| Short exit (`PA` 7–8) | 114 | 1.2% | — | — |

By season: excluded share **4.1%** (2023) → **2.9%** (2024).

The heuristic `PA ≤ 6` bucket **mixes** planned openers with early hooks — it is
a diagnostic label only, never a training feature.

## What this means for claims

| Claim | Allowed? |
|---|---|
| Metrics on the `PA ≥ 9` research cohort | Yes (conditional estimand) |
| “Works for every announced starter” | **No** |
| Prop calibration for planned openers | **No** until pregame role exists |
| Live scoring of announced starters | Allowed with **out-of-support** flag for known openers / short-workload plans |

## Interim policy (frozen)

1. Keep `PA ≥ 9` as the **research estimand** for k-rate / TBF / count-layer
   training and Phase 11 metrics.
2. Model card / paper language must say metrics are **conditional** on that
   cohort.
3. Live path may score any announced starter, but opener / piggyback /
   short-workload designations are **out of support** until a pregame-observable
   role flag is ingested.
4. Do **not** call a holdout “pristine v1 baseline” until role labels exist and
   metrics are reported for (a) conventional starters and (b) all announced
   starters separately.

## Still required for pristine v1

- Pregame role source (lineup/news): announced starter vs opener vs piggyback —
  **not** inferred from same-game PA.
- Dual reporting: conventional subgroup vs all announced starters.
- Optional later: train a short-workload / opener-specific TBF path if volume
  warrants it (not on critical path; excluded N ≈ 340 over two seasons).

## Cutoff screen (5–10)

**Runner:** `phase_d_pa_cutoff_screen.py`  
**Artifact:** `artifacts/model_quality/phase_d_pa_cutoff/`

| Cutoff | Included | Excluded share | Included k_rate std |
|---:|---:|---:|---:|
| 5 | 9,611 | 1.1% | 0.1082 |
| 6 | 9,550 | 1.7% | 0.1075 |
| 7 | 9,488 | 2.3% | 0.1066 |
| 8 | 9,420 | 3.0% | 0.1060 |
| **9** | **9,374** | **3.5%** | **0.1057** |
| 10 | 9,320 | 4.1% | 0.1055 |

No sharp elbow. Moving 8↔9↔10 changes excluded share by ~0.5 pp and barely
moves k_rate stability. **Keep `MIN_STARTER_BATTERS_FACED = 9`** (one turn
through the order). Do not reopen production on this screen alone.

```powershell
python Models/Strikeout-Model/Strikeout-EDA/phase_d_pa_cutoff_screen.py
```
