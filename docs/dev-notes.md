# MLB Pitcher Strikeout Model — Development Documentation

> **⚠️ Status banner (read first).** This document is the historical development
> record from the UNC Longleaf HPC phase (June 2026). Two things have changed
> since it was written:
>
> 1. **Environment moved off Longleaf.** Paths, model saving, and Optuna storage
>    are now portable via `src/mlb_props/config.py` (see `README.md`). Ignore the
>    hardcoded `/nas/longleaf/...` paths below — they are kept only for history.
> 2. **Same-game `PA` leakage was removed from the feature set.** Any Val/Test R²
>    reported below (notably §5 and §10, and the leakage claim in §2.4) was
>    produced *with* `PA` in the features and is **no longer valid**. Expect a
>    meaningful R² drop after retraining without `PA`; that lower number is the
>    honest pregame baseline. See `docs/model-card.md` for the current rules.

**Project:** LightGBM Strikeout Rate Prediction Model
**Author:** kapcam
**Original environment:** UNC Longleaf HPC · `/nas/longleaf/home/kapcam/` · Python 3.11 · `tf_env` conda
**Notebook:** `Models/Strikeout-Model/LightGBM.ipynb`
**Last Updated:** June 6, 2026 (migrated to portable repo July 2026)

***

## Overview

This project builds a machine learning model to predict a pitcher's
**strikeout rate (`k_rate = K / PA`)** for a given start, using only information
available *before* the game begins. The model is trained on 2023–2025 Statcast
pitcher start data and is the foundation for a downstream **projected K count**
tool using Poisson distribution inference.

The baseline beat: Ridge/Linear Regression — Val R² = 0.1274, Test R² = 0.1486.
Reported best at the time: **Val R² = 0.8113, Test R² = 0.8840** (LightGBM v9,
194 features, 6,290 trees).

> **⚠️ Invalid metrics.** The 0.8113 / 0.8840 figures included same-game `PA` as
> a feature and cannot be trusted for pregame projection. Retrain without `PA`
> to establish the real baseline.

***

## 1. Dataset

| Property | Value |
|---|---|
| **Source file** | `Pitcher2023-2025.parquet` (loaded via `PITCHER_STARTS_PATH`) |
| **Loaded via** | Polars → converted to Pandas |
| **Total rows** | ~13,662–14,352 pitcher starts (2023–2025 seasons) |
| **Target variable** | `k_rate = K / PA.clip(lower=1)` |
| **Train/Val/Test split** | Chronological 70 / 15 / 15 |
| **Train ends** | 2025-04-20 |
| **Val ends** | 2025-07-08 |
| **Test starts** | 2025-07-09 |

The chronological split is intentional and critical — random splitting would
leak future information into training, inflating performance metrics and
invalidating the model for real-world forecasting use.

***

## 2. Feature Engineering

### 2.1 Derived Features

| Feature | Formula | Notes |
|---|---|---|
| `k_rate` | `K / PA.clip(lower=1)` | Target variable |
| `ff_power_angle` | `ff_velo × abs(ff_vaa)` | Fastball velocity × vertical approach angle |
| `ch_effectiveness` | `throws_ch × abs(ch_vaa)` | Changeup usage × approach angle |
| `ff_ch_velo_diff` | `ff_velo − ch_velo` | Velocity separation (tunneling) |
| `ff_sl_velo_diff` | `ff_velo − sl_velo` | Velocity separation |
| `ff_si_velo_diff` | `ff_velo − si_velo` | Velocity separation |
| `ff_ch_ivb_diff` | `ff_ivb − ch_ivb` | Vertical break differential |
| `ff_sl_ivb_diff` | `ff_ivb − sl_ivb` | Vertical break differential |
| `ch_platoon_split` | `ch_usage_vL − ch_usage_vR` | Changeup handedness tendency |
| `sl_platoon_split` | `sl_usage_vL − sl_usage_vR` | Slider handedness tendency |

### 2.2 Rolling Windows

Rolling windows of **5, 10, and 20 games** are computed for each stat, shifted by
1 game to prevent same-game leakage. Minimum periods: 3 for P5/P10, 5 for P20.

**Outcome stats (windows: 5, 10, 20):**
`k_rate`, `Whiffs`, `CSW`, `CS`, `GB`, `BB`, `Strikes`, `Balls`, `BIP`, `PA`, `xBA_clipped`, `xwOBA_clipped`

**Physics stats (windows: 1, 3, 5, 10):**
All pitch types (ff, sl, ch, si, cu, fc, st) × (`velo`, `spinrate`, `ivb`, `hb`, `vaa`)

**Arsenal stats (window: 1):**
`ff_usage_vR/vL`, `sl_usage_vR/vL`, `ch_usage_vR/vL`

**Interaction/Tunneling stats (windows: 1, 3, 5):**
`ff_power_angle`, `ch_effectiveness`, `ff_ch_velo_diff`, `ff_sl_velo_diff`, `ff_si_velo_diff`, `ff_ch_ivb_diff`, `ff_sl_ivb_diff`, `ff_ch_vaa_diff`, `ch_platoon_split`, `sl_platoon_split`

Naming convention: `{stat}_P{window}` — e.g., `k_rate_P20`, `Whiffs_P10`.

> **Note on rolled `PA`.** Lagged `PA_P{w}` (a shift(1) rolling average of past
> volume) is legitimate pregame information. The problem was **same-game `PA`**
> (`context_features = ['PA']`), which has been removed. Keep the rolled versions;
> never reintroduce raw same-game `PA`.

### 2.3 Shrinkage (Empirical Bayes)

Two rolling features are shrunk toward the population mean to reduce small-sample
noise:

```
CSW_P20_shrunk = 0.58 × pitcher_CSW_P20 + 0.42 × league_avg_CSW
BB_P20_shrunk  = 0.51 × pitcher_BB_P20  + 0.49 × league_avg_BB
```

CSW (a sticky, reliable skill) receives 58% pitcher weight. BB rate (noisier) is
near-equal weighted — even 20 starts carries significant walk-rate luck.

### 2.4 Leakage Check

> **⚠️ This section's conclusion was wrong.** The original claim — "No live
> same-game data was found in the feature set" — is contradicted by §6, where
> `PA` appears as SHAP rank #4. Same-game `PA` was in `ALL_FEATURES`. It has now
> been removed. The forbidden-feature list is enforced in
> `src/mlb_props/features.py` and checked by `tests/test_feature_safety.py`.

A same-game correlation check was run on all features against `k_rate`. Top
correlated features were rolling k_rate windows (expected — they're lagged
versions of the target).

| Feature | Same-Game Correlation |
|---|---|
| `k_rate_P20` | 0.2097 |
| `k_rate_P10` | 0.2034 |
| `k_rate_P5` | 0.1942 |
| `Whiffs_P20` | 0.1799 |
| `ff_usage_vR` | 0.1205 |

***

## 3. Feature Set Evolution

| Version | Features | Notes |
|---|---|---|
| v3 | 79 | Full physics + rolling + arsenal + context + manual |
| v4 | 71 | SHAP-pruned: removed 8 dead binary throw-indicator features |
| v9 | 194 | Expanded: added physics P1/P3 windows, interaction/tunneling features, shrunk features, xBA/xwOBA rolling; pruned 36 low-signal features via `FEATURES_TO_DROP` |
| v10 (next) | TBD | v9 minus same-game `PA`; retrain to establish honest baseline |

The `FEATURES_TO_DROP` list in v9 removes features identified as noisy or
redundant across Optuna trials, including: `CS_P10`, `CS_P5`, `CS_P20`,
`Strikes_P20`, `Balls_P10/P20`, `BB_P5/P10`, `CSW_P5/P10`, `GB_P20`,
`BIP_P5/10/20`, `Whiffs_P5`, and all short-window `ch_usage`/`sl_usage` arsenal
features.

***

## 4. Monotone Constraints

`monotone_constraints` encode domain knowledge directly into LightGBM's
tree-growing logic. The model is **forbidden** from learning a relationship that
violates baseball reality — e.g., it cannot conclude that throwing harder leads
to fewer strikeouts.

Constraints are a **positional list** matched to `ALL_FEATURES` order. Must be
rebuilt every time the feature set changes (including after the `PA` removal).

```python
monotone_constraints = [monotone_map.get(f, 0) for f in ALL_FEATURES]
```

### Active Constraints (of the current feature set)

| Feature Group | Direction | Rationale |
|---|---|---|
| `ff_velo_Pw` (all windows) | +1 | Higher velocity → more Ks |
| `ff_vaa_Pw` (all windows) | +1 | Steeper downward angle → harder to hit |
| `ff_ivb_Pw` (all windows) | +1 | More vertical break → more Ks |
| `ff_spinrate_Pw` (all windows) | +1 | Higher spin → more movement |
| `sl_vaa_Pw` (all windows) | -1 | Slider with steeper drop → fewer Ks (slurve profile) |
| `k_rate_Pw` (all windows) | +1 | Recent K trend reinforces prediction |
| `Whiffs_Pw` (all windows) | +1 | More whiffs → more Ks |
| `CSW_Pw` (all windows) | +1 | Higher CSW rate → more Ks |
| `BB_Pw` (all windows) | -1 | More walks → fewer Ks |
| `BIP_Pw` (all windows) | -1 | More balls in play → fewer Ks |
| `ff_power_angle_Pw` | +1 | Combined velo/angle metric |
| `CSW_P20_shrunk` | +1 | Shrunk CSW retains monotone |
| `BB_P20_shrunk` | -1 | Shrunk BB retains monotone |

***

## 5. Model History & Results

> **⚠️ Metrics below predate the `PA` leakage fix and are invalid for pregame
> use.** Retrain v10 (v9 minus `PA`) and record the new numbers before relying on
> anything in this section.

### 5.1 Performance by Version

| Version | Features | Val RMSE | Val R² | Test RMSE | Test R² | Trees |
|---|---|---|---|---|---|---|
| Baseline (Ridge) | 79 | — | 0.1274 | — | 0.1486 | — |
| v3 | 79 | 0.0406 | 0.8562 | 0.0287 | 0.9318 | 6,704 |
| v4 (SHAP-pruned) | 71 | — | — | — | — | — |
| v9 | 194 | 0.0454 | 0.8113 | 0.0367 | 0.8840 | 6,290 |

> Note: v3's Test R² of 0.9318 likely reflects overfitting and/or same-game
> leakage plus a favorable test window. Treat both v3 and v9 numbers as
> contaminated until v10 is retrained.

### 5.2 v9 Hyperparameters (Hand-Tuned)

```python
lgb.LGBMRegressor(
    objective='regression',
    n_estimators=12000,        # cap; early stopping triggers at ~6,290
    learning_rate=0.02,
    num_leaves=63,
    min_child_samples=50,
    subsample=0.8,
    colsample_bytree=0.6,
    reg_alpha=0.1,
    reg_lambda=2.0,
    monotone_constraints=monotone_constraints,
    monotone_constraints_method='advanced',
    random_state=42,
)
```

### 5.3 Optuna Tuning Results

Two Optuna runs were completed:

**Run 1** — 75 trials, `n_estimators` capped at 1500, SSH disconnected at trial 69/75.
Best result at trial 34: **Val R² = 0.8130**

**Run 2** — 30 trials (tighter search ranges), `n_estimators` capped at 1500.
Best result at trial 22: **Val R² = 0.8134**

**Best Optuna Params (Run 2, saved):**

```python
best_params = {
    'learning_rate':      0.08469138193522512,
    'num_leaves':         86,
    'min_child_samples':  27,
    'subsample':          0.8504531335816663,
    'colsample_bytree':   0.7935904135362665,
    'reg_alpha':          0.003221329429464891,
    'reg_lambda':         2.161174132205377,
}
```

Key insight: these Optuna params were capped at 1500 trees and still matched the
hand-tuned val R². With a proper tree budget (3,000–5,000) at `lr=0.085`, this
param set likely exceeds the hand-tuned baseline — but re-tune after removing
`PA`, since the old objective was optimizing a leaked target.

***

## 6. SHAP Feature Importance (v3, 79 features)

`shap.TreeExplainer` was run on the validation set. Results guided feature
pruning decisions.

### Top 10 Features by Mean |SHAP|

| Rank | Feature | Mean \|SHAP\| |
|---|---|---|
| 1 | `ff_vaa` | 0.019019 |
| 2 | `ff_velo` | 0.013120 |
| 3 | `k_rate_P20` | 0.010648 |
| 4 | `PA` | 0.009826 |
| 5 | `k_rate_P5` | 0.009233 |
| 6 | `ff_power_angle` | 0.008818 |
| 7 | `ch_effectiveness` | 0.007308 |
| 8 | `ff_spinrate` | 0.007286 |
| 9 | `sl_vaa` | 0.006241 |
| 10 | `ff_ivb` | 0.006081 |

> **⚠️ Rank #4 `PA` is the leak.** This SHAP table is the direct evidence that
> same-game `PA` was driving predictions. After removal, re-run SHAP on v10 and
> expect the top of the table to be dominated by `ff_vaa`, `ff_velo`, and the
> lagged `k_rate` windows.

Fastball vertical approach angle (`ff_vaa`) is the single most important
legitimate feature — more predictive than raw velocity. This aligns with
biomechanics research showing that perceived rise (steep downward VAA) disrupts
batter timing more than velocity alone.

### Dead Features Pruned (v3 → v4)

All 8 pruned features were binary pitch-type indicators (`throws_ff`,
`throws_sl`, etc.) with mean |SHAP| < 0.0001. Arsenal composition was already
captured by usage rate rolling averages.

***

## 7. Infrastructure & Engineering Notes

> **⚠️ Superseded by the portable repo.** The Longleaf-specific details below are
> historical. Current paths come from `src/mlb_props/config.py` and environment
> variables documented in `README.md` and `.env.example`.

### 7.1 Original Environment (historical)

- **Cluster:** UNC Longleaf HPC
- **Kernel:** Python 3.11, `tf_env` conda environment
- **Key libraries:** `lightgbm`, `shap`, `polars`, `pandas`, `optuna`, `sklearn`, `scipy`, `tqdm`
- **Custom module:** `RosterScraper` (now loaded from the repo via `ROSTER_SCRAPER_DIR`)

### 7.2 Model Saving

Historical path: `/nas/longleaf/home/kapcam/MLB/Strikeout-model/SavedModels/lgb_v{N}_{ts}.txt`

Current path: `artifacts/models/lgb_<n>feat_<ts>.txt` via `MODEL_DIR`, using
`model.booster_.save_model(str(path))`. The timestamp guarantees unique
filenames across runs.

### 7.3 Crash Recovery (Optuna)

SQLite persistence lets a study auto-resume after an interruption. Current code
stores the study at `OPTUNA_DIR / "optuna_v9.db"`:

```python
storage = optuna.storages.RDBStorage(f"sqlite:///{study_path.as_posix()}")
study = optuna.create_study(
    study_name='lgbm_krate_v9',
    storage=storage,
    load_if_exists=True,   # auto-resume after crash
    direction='maximize'
)
```

### 7.4 Key Implementation Rules

- **Monotone constraints are positional** — rebuild from scratch after any
  feature set change via `[monotone_map.get(f, 0) for f in ALL_FEATURES]`.
- **`model_df` must carry `K` and `PA`** alongside `ALL_FEATURES` + `TARGET` for
  Poisson evaluation downstream — but `PA`/`K` are label/eval columns only, never
  model inputs.
- **`log_evaluation(-1)`** inside the Optuna objective silences per-round output.
- **`early_stopping(N)`** stops training when val L2 doesn't improve for N rounds;
  keeps the best iteration automatically.

***

## 8. What's Being Built Now

### 8.1 Optuna Final Model

Train the final model using the best Optuna params with an uncapped tree budget —
**after** removing `PA` and re-running the study against the honest target:

```python
final_model = lgb.LGBMRegressor(
    n_estimators=5000,   # proper headroom for lr=0.085
    **best_params,
    monotone_constraints=monotone_constraints,
    ...
)
```

### 8.2 Projected K Count via Poisson Distribution

The model predicts `k_rate`. To convert to a **projected K count**:

**Lambda:** $$\lambda = \hat{k\_rate} \times \text{E[TBF]}$$

> **⚠️ Use projected TBF, not actual PA.** The original doc used
> `λ = k_rate × PA` with *actual* same-game PA, which assumes knowledge you won't
> have pregame. For an honest prop backtest, estimate TBF (e.g. rolling `TBF_P5`)
> and use that. Actual PA/K may only be used *after* prediction, to score results.

**Expected K:** $$E[K] = \lambda$$

**Probability of exactly k strikeouts:** $$P(K = k) = \frac{e^{-\lambda} \lambda^k}{k!}$$

**Probability of at least k strikeouts:** $$P(K \geq k) = 1 - \text{CDF}(\lambda, k-1)$$

The Poisson residual (`actual_K − λ`) measures how much a start over- or
under-performed expectation, enabling game-level over/under analysis.

***

## 9. Next Steps

### Immediate (Next Session)

- [ ] **Retrain v10** = v9 minus same-game `PA`; record honest val/test R² (expect a drop)
- [ ] **Re-run SHAP** on v10; confirm `PA` is gone and update `FEATURES_TO_DROP` if new dead features appear
- [ ] **Rebuild `model_df`** to include raw `K`/`PA` as eval-only columns (not features)
- [ ] **Run Poisson evaluation** on the test set using **projected TBF**, not actual PA; plot residuals
- [ ] **Re-run Optuna** against the honest target with SQLite persistence and a proper tree budget

### Short-Term Feature Additions

- [ ] **Rolling TBF (Batters Faced)** — add `TBF` to the outcome rolling loop; use `TBF_P5` to calibrate K projection
- [ ] **Opponent lineup K%** — rolling strikeout rate of the opposing lineup (from batting data); highest-impact missing signal
- [ ] **Park factor** — park K-factor adjustment at inference time
- [ ] **Rest/fatigue proxy** — days since last start
- [ ] **Season-to-date trend** — full-season k_rate rolling average

### Medium-Term Architecture

- [ ] **Stacking ensemble** — LightGBM base + Ridge second-layer blender
- [ ] **Opponent lineup adjustment** — dampened post-prediction scalar vs. league average
- [ ] **Inference pipeline** — `project_start(pitcher_name, game_date)` returning `{pred_k_rate, expected_TBF, projected_K, P(K≥6), P(K≥7), P(K≥8)}`

### Production Goals

- [ ] **Betting market comparison** — projected K vs. sportsbook prop lines; find systematic edges
- [ ] **DFS integration** — K projections as pitcher DFS scoring inputs
- [ ] **2026 season live deployment** — daily Statcast pull → inference for probable starters → prop comparison table

***

## 10. Model Version Reference

> **⚠️ All R² values below predate the `PA` leakage fix.** v10 will be the first
> trustworthy pregame baseline.

| Version | Date | Feature Count | Val R² | Test R² | Notes |
|---|---|---|---|---|---|
| Ridge baseline | Jun 2026 | 79 | 0.1274 | 0.1486 | Linear model, no rolling features |
| v3 | Jun 3, 2026 | 79 | 0.8562 | 0.9318 | First full LightGBM with monotone constraints (leaked) |
| v4 | Jun 3, 2026 | 71 | — | — | SHAP-pruned; training cell was missing (bug) |
| v9 | Jun 4–5, 2026 | 194 | 0.8113 | 0.8840 | Expanded physics/tunneling; Optuna initiated (leaked) |
| v9 + Optuna | Jun 5–6, 2026 | 194 | 0.8134* | TBD | *Val-only; leaked |
| v10 | TBD | 193 (v9 − `PA`) | TBD | TBD | First leakage-free baseline |

***

*Development sessions June 3–6, 2026 on Longleaf HPC; migrated to a portable
cross-platform repo July 2026. Current rules of record live in
`docs/model-card.md`.*
