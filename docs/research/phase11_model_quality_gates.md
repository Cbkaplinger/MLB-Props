# Phase 11 — Model quality gates (after feature freeze)

**Status:** 11.A–C **complete** (verification, not big lifts); 11.D interim policy
frozen — see `docs/research/phase_d_population_findings.md`  
**Date:** 2026-07-28  
**Audience:** research → decision-quality before any live or market path

## Verdict (honest)

Phase 11 was mostly a **gate pass**, not a discovery phase. Nested LGBM HPO did
not beat freeze defaults on outer confirmation; walk-forward `expected_K` held
near the prior chrono reference (~1.78 vs ~1.79); line ECE was already acceptable
without recalibration. That is useful — it means the frozen stack was already
near a local optimum — but it is **not** a story of large metric gains.

| Gate | Result | Learning |
|---|---|---|
| **11.A** | Keep baseline LGBM defaults; Ridge α ≈ 123 + joblib | HPO ≈ flat vs defaults |
| **11.B** | Mean expected_K MAE **1.778** (3 windows); pass | Stack coherent under expanding WF |
| **11.C** | Mean ECE **0.024**; no recalibration **in-gate** | Probs usable; 3.5 slightly hot |
| **11.D** | ~**3.5%** of first pitchers excluded by `PA≥9` | Interim policy; role labels still missing |

**Follow-on (2026-08-03):** chrono-safe **Platt** post-hoc maps on WF OOS
`p_over_*` — see `docs/research/prob_calibration_findings.md`. This does **not**
reopen 11.C’s soft bar verdict; it is an optional honesty layer selected by
expanding-window CV (mean ΔECE ≈ −0.008). Raw generative probs remain logged.

Artifacts: `artifacts/model_quality/phase11a_*`, `phase11b_*`, `phase11c_*`,
`phase_d_population/`.

## Why this came next (not live assembly)

Feature selection is closed (`production` = **184**, Step 11 discipline lift). That does
**not** mean the *models* or *decision stack* are ready. In a betting / pricing
system the product is a **probability**, not a parquet of features. The correct
sequence after a feature freeze:

```text
Frozen feature spine
    → (1) Tune estimators under chrono / nested folds
    → (2) Walk-forward backtest of the full stack
          k_rate × TBF → expected_K → P(K ≥ L)
    → (3) Calibration + reliability diagnostics
    → (4) Population hygiene (Phase D openers) before pristine claims
    → (5) Only then: live inference assembly + monitoring
    → (6) Optional: market de-vig / Kelly (needs prices + edge distribution)
```

Live assembly is **operationalization**. Tuning + backtesting + calibration are
**whether the system is allowed to make decisions**. Shipping inference first
optimizes for a demo; this phase optimizes for not fooling yourself.

## How to attack this (priority order)

Think in three layers of risk, then spend engineering time in that order:

| Risk | Failure mode | Attack |
|---|---|---|
| **Estimation** | Defaults leave MAE / Brier on the table | Small nested HPO on *frozen* 184; persist TBF α |
| **Stack coherence** | Rate looks fine, props don't | Walk-forward `k_rate × TBF → expected_K → lines` as one object |
| **Decision quality** | Probabilities are miscalibrated / sliced | ECE, reliability, residual slices before any Kelly talk |

**Do first (11.A):** nested LightGBM tune + Ridge α grid + joblib TBF. This is
cheap, chrono-safe, and unblocks reproducible backtests.

**Do second (11.B):** expanding-window stack backtest with fold variance. Report
`expected_K` and line Brier as first-class — component MAE alone is not a
product metric.

**Do third (11.C):** calibration. Only then argue for live assembly or market
grading. Phase D (openers) runs in parallel but blocks “v1 baseline” claims.

**Do not reopen** feature families, windows, or 2025 selection unless a gate
fails hard and the failure is clearly feature-limited (then: new nested cycle,
not silent registry edits).

## Locked inputs (do not reopen casually)

| Component | Lock |
|---|---|
| K-rate features | `production` 184 (`docs/research/step11_discipline_registry_freeze.md`) |
| K-rate family | Unweighted LightGBM (Step 5) |
| TBF | Ridge + `workload_context_bullpen` |
| Count identity | `expected_K = k_rate × projected_tbf` |
| Research seasons | 2023–2024 nested / chrono only for selection |
| 2025 | Historical only — **not** a selection fold |

If a tune or backtest *requires* new features, that is a new research cycle with
nested promotion — not silent registry edits.

---

## Gate 11.A — Estimator tuning (frozen features)

**Goal:** improve predictive metrics without leaking future information.

### K-rate (LightGBM)
- Search space (small, chrono-safe): `learning_rate`, `num_leaves`,
  `min_child_samples`, `subsample`, `colsample_bytree`, `reg_lambda`
  (± `max_depth` if used).
- Protocol: **inner** selection on `nested_research_folds` (or expanding-window
  chrono CV); **outer** confirmation never used for search.
- Objective: minimize validation **MAE** on `k_rate` (primary); log RMSE/R².
- Early stopping stays on the *inner* validation partition only.
- Deliverable: tuned hyperparams JSON + refit artifact under
  `artifacts/models/`; compare vs current freeze
  `lightgbm_krate_20260803_155401` on the **same** outer/test cut.

### TBF (Ridge / thin pen)
- Search `alpha` (log grid) on the same chrono train/val discipline.
- Optional one-shot ElasticNet / Poisson *challenger* only if nested MAE wins
  on both outer folds (prior bake-off already favored thin Ridge — bar is high).
- Deliverable: **persist** coefficients (joblib) — required for reproducible
  backtests and later live scoring.

### Explicit non-goals for 11.A
- No new rolling windows / families.
- No Optuna over the full feature space.
- No 2025 in the search loop.

---

## Gate 11.B — Walk-forward stack backtest

**Goal:** evaluate the *decision object*, not just component MAE.

### Unit of evaluation
For each chronological test fold / expanding window:

| Layer | Metric |
|---|---|
| Rate | MAE / RMSE of `k_rate` |
| Volume | MAE / RMSE of `projected_tbf` vs actual PA (starters) |
| Count | MAE / RMSE of `expected_K` vs actual K |
| Lines | Brier, log loss, and reliability for `P(K ≥ L)` at L ∈ {3.5…7.5} |
| Slice | By month, rest bucket, TBF quintile, home/away |

### Protocol
1. Expanding or rolling **train → validate → test** blocks on 2023–2024
   (reuse `chronological_split` / custom walk-forward; no random CV).
2. At each step: fit (or load tuned) k-rate + TBF on past only; score future.
3. Aggregate with time weights or report per-window — never pool then claim
   one number without fold variance.
4. Optional stretch: simulate announced-lineup *availability* (confirmed vs
   projected) as a stress test — not required for Gate 11.B pass.

### Pass / fail (research bar)
- Stack `expected_K` MAE not worse than frozen baseline (~1.79) after tuning,
  within fold noise.
- Line Brier not systematically worse across 3.5–7.5.
- No single slice (e.g. long-rest, low-TBF) collapses without documentation.

---

## Gate 11.C — Calibration & reliability

**Goal:** probabilities that mean what they say.

1. Reliability diagrams + ECE (or equivalent) for line probs on walk-forward
   out-of-sample predictions.
2. Rate residual checks by predicted-rate bins (bias / variance).
3. Recalibration only if justified (isotonic / temperature) **fit on train/val**,
   applied to test — never fit on the reported test.
4. Document whether binomial with `n = round(TBF)` remains adequate vs Poisson
   (current evidence: BB collapses to binomial).

---

## Gate 11.D — Population hygiene (interim policy frozen)

**Done (audit + policy):** `docs/research/phase_d_population_findings.md`.

- ~**3.5%** of 2023–2024 first-pitcher appearances have `PA < 9` (excluded).
- Metrics remain **conditional** on the `PA ≥ 9` research cohort.
- Pregame role labels (opener / piggyback) are still missing — required before
  pristine “v1 baseline” claims, not before live assembly with out-of-support flags.

---

## What comes after Phase 11

| Phase | When |
|---|---|
| **Live assembly** | 11.A–C passed; optional with opener out-of-support flags |
| **Pristine holdout** | Future games + pregame role labels (Phase D completion) |
| **Market / Kelly** | Only with closing lines + calibrated probs + edge distribution |
| **Park cleanup / NB challenger** | Opportunistic; not on the critical path |

---

## Engineering deliverables (checklist)

- [x] `models/Strikeout-Model/research/tune_lightgbm_production.py` (nested HPO)
- [x] TBF `alpha` grid + **joblib persist** in `Models/TBF-Model/train.py`
- [x] `models/Strikeout-Model/research/walkforward_stack_backtest.py`
- [x] `models/Strikeout-Model/research/calibrate_stack.py`
- [x] Keep baseline LGBM defaults (11.A HPO did not beat outer baseline)
- [x] Phase D population audit + interim policy (`phase_d_population_audit.py`)
- [x] Live assembly v1 (`live_assembly.py` + `predict_slate.py`)
- [ ] Pregame role ingestion before pristine “v1 baseline” claims
- [ ] Refresh Savant / Level 1–2 through yesterday for true live slates
- [ ] Doubleheader-safe schedule join in `daily_lineups`

## Pickup

```powershell
python models/Strikeout-Model/research/tune_lightgbm_production.py --refit
python Models/TBF-Model/train.py --model ridge --tune-alpha --persist
python models/Strikeout-Model/research/walkforward_stack_backtest.py
python models/Strikeout-Model/research/calibrate_stack.py
python models/Strikeout-Model/research/phase_d_population_audit.py
```

See `docs/diagrams/04-roadmap.md` and `docs/diagrams/03-modeling-and-evaluation.md`.
