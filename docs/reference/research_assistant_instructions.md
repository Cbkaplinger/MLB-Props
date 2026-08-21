# MLB Props Research Assistant Instructions

## Purpose

Audit, refactor, document, and operate an MLB pitcher strikeout stack
(`k_rate × projected_TBF → expected_K → P(K ≥ L)`). Prefer notebooks/CLIs that
call canonical `src/Python` functions over reimplemented logic. Assume advanced
Python/Polars/Statcast/leakage/chronological-ML knowledge.

## Repository and constraints

Work only in: `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props`

- Package stays at `src/Python` (never `src/mlb_props`). Preserve the three-level
  pipeline. Prefer **Polars**; pandas only at plot/sklearn/LightGBM boundaries.
- No commit/push/reset/amend/discard unless the owner asks. Never `git push` —
  give the owner the exact command.
- Keep generated data/models local (`data/`, `artifacts/`). Notebooks may be
  stale; verify/rerun. Notebooks and `production/` call library functions —
  never reimplement trainers, features, or splits.

| Family | Path |
|---|---|
| Package | `src/Python/` (incl. `market.py` + `skill_stats.py`) |
| Pipeline notebooks | `src/Notebooks/` |
| Models | `models/Strikeout-Model/` (+ `research/`), `models/TBF-Model/` |
| Production | `production/` (incl. `results_dashboard.ipynb` — CLV skill suite) |
| Playground / scripts / tests | `playground/`, `scripts/`, `tests/` |
| Docs | `docs/paper/`, `research/`, `reference/`, `diagrams/`, `archive/` |

Trainers: `models/Strikeout-Model/train.py`, `models/TBF-Model/train.py`.
Research runners: `models/Strikeout-Model/research/` (ex-`Strikeout-EDA/`).

## Architecture

**Target:** game-level `k_rate = K / PA` for first pitchers with
`PA ≥ MIN_STARTER_BATTERS_FACED` (9) — a **postgame cohort filter** on a
pregame model (~3.5% of 2023–2024 first-pitcher appearances excluded). Claims
do not cover every announced starter until pregame role labels exist.

**Seasons:** 2022 = prior-only park/league context (never model rows).
`TRAIN_SEASONS = (2023, 2024)`. 2025 was consulted by early baselines —
historical benchmark only, not a pristine final holdout. Projection year may
include 2026 features as configured.

Levels (do not collapse):

1. **games** — `pipeline/games.py`: pitcher/batter/pitch-type games, park, bullpen L1.
2. **rolling** — `pipeline/rolling.py`: lagged rolling + season-to-date form.
3. **training** — `pipeline/training.py`: pitcher form + opponent-lineup aggregates
   from `batter_rolling.is_initial_lineup` (first nine by first PA — **not**
   `daily_lineups.py`) + prior-season parks.

Live RG+MLB assembly (`daily_lineups.py` / `live_assembly.py`) is
**inference-only**. Train uses first-9-by-PA; live uses announced RG order
(`docs/reference/lineup_train_serve.md`).

**Frozen stack (2026-08-03):**

| Piece | Model | Notes |
|---|---|---|
| Rate | Unweighted LightGBM | **`production` = 184** (Step 10 P1 + Step 11 discipline) |
| TBF | Ridge | Thin bullpen (**24** feats); α persisted |
| Counts | Binomial/Poisson | On **projected** TBF only |

Artifacts: `lightgbm_krate_20260803_155401`,
`tbf_pa_ridge_workload_context_bullpen_20260728_035607`.
Companions: `step10_180`, `step7_185`, `pre_freeze_248`, `ridge_vif` (73).

Chrono test (from 2024-08-06): MAE/RMSE/R² ≈ **0.0780 / 0.0982 / 0.156**.
Marcel-lite ≈ **0.0826**; mean floor ≈ **0.0854**. Walk-forward expected-K
MAE ≈ **1.775** (discipline challenger screen); mean ECE ≈ **0.024** (Phase 11.C).

Paper: `docs/paper/manuscript.md`. Summary: `docs/paper/resume-summary.md`.
Status: `docs/diagrams/00-index.md`.
Freeze: `docs/research/step11_discipline_registry_freeze.md`.

## Leakage and feature safety

Everything must be known before first pitch. **Never as features:** same-game
`K`/`PA`/`Outs`/`k_rate`/actual TBF; current-game rolling contributions; future
dates/seasons/lineups/park outcomes; raw IDs/names/teams/dates/join keys.
Labels/metadata/eval only for those.

Player-form: prior games only; exclude current-date games (incl. doubleheaders);
yearly STD reset; rates from summed priors. Park Y uses seasons `< Y`; unseen →
1.0. Neutral/international parks **not filtered** (~0.2% special-event share —
open risk). Rays 2025 Steinbrenner override is fixed.

Gate: `features.py` + registries; unexpected numerics fail loudly. Research-only
columns need nested promotion / `include_experimental=True`.
**No SHAP** (no leakage-safe path) — use leave-family-out / permutation.
Flag unsafe proposals explicitly.

## Modeling and evaluation

- Chronological, date-disjoint splits only; never split a calendar date.
  Nested folds: `models/Strikeout-Model/research/nested_cv.py`.
- Fit preprocessing on train only. Select on inner folds — never final test or
  recycled 2025.
- Unweighted LightGBM beat PA-weight and binomial/beta-binomial nested screens;
  keep unless overturned.
- Ablations: two outer folds; within-fold bootstrap B=2000 for ΔMAE. Opponent
  lineup is the only both-fold bootstrap keep; do not oversell other families.
- `expected_K = k_rate_hat × tbf_hat` with projected exposure only.
- Markets/CLV/Kelly are a **product layer** (odds never train LightGBM) —
  see `docs/reference/market_clv_gates.md` and `production/README.md`.
  Statistical skill checks on the CLV ledger live in
  `src/Python/skill_stats.py` (z-test, BCa CI, stake-weighted bootstrap,
  rolling SE ribbon) — used by `production/notebooks/results_dashboard.ipynb`
  Sections 11-18. Floor and Kelly freezes are pre-registered and recorded in
  `docs/research/floor_freeze_log.md`; dashboard additions in
  `docs/research/notebook_change_log.md`.

## Production daily ops

```text
refresh_statcast → refresh_features [--skip-training] → log_projections
→ odds_board → poll_odds --snapshot open
→ (tip window) close_watcher  OR  poll_odds --snapshot close
→ grade_odds_ledger [--auto-settle-api]
→ (next day) refresh + grade_projections --all-logged --preferred-only
```

Catch-up opens: `poll_odds --snapshot open --append` (does **not** start the
watcher). Formal log from **2026-07-28**:
`artifacts/projection_log/{projections,graded}.parquet`. Odds ledger:
`artifacts/odds_log/ledger.parquet`. Morning board:
`production/notebooks/daily_projections.ipynb`.

## Reviews and notebooks

**Reviews:** cite functions; separate bugs vs cleanup. Order: `statcast` →
pitcher/batter features → rolling → `ballpark`/`bullpen` → pipeline
games/rolling/training → `features`/`registries` → rate/TBF `train` →
`count_layer`/`live_assembly` → `production/*`.

**Notebooks:** visual audits only — import canonical code; shapes/nulls/
distributions; uniqueness/coverage/leakage checks; no huge dumps; no duplicated
split/model/metric/persistence. Train notebook under `models/Strikeout-Model/`.
Level 3 construction audit: `src/Notebooks/pipeline/training.ipynb`.

## Remaining work

**Done** (do not reopen without evidence): Steps 1/3/4/5/7–10; Phase 11
tune/WF/calibrate; Phase D PA≥9 interim; TBF + count layer; post-hoc Platt
`p_over_*` calibration (production pointer); live dual scoring; projection
log/grade; paper-trading board/ledger/CLV closes; manuscript;
**2026-08-06 dashboard CLV skill suite** (`results_dashboard.ipynb` §11-18 +
`src/Python/skill_stats.py` z-test / BCa / stake-weighted / rolling-SE) and
the pre-registered floor-freeze log (`docs/research/floor_freeze_log.md`).

**Open:** (1) grow post-freeze holdout — don’t sell recycled 2025 as pristine;
(2) pregame role labels before broader population claims; (3) filter
neutral/international parks; (4) grow CLV skill sample to **n_clv ≥ 150
at floor ≥ 12%** before real bankroll; check the **BCa CLV CI on
floor ≥ 12% excludes zero AND win-rate > 0.524 break-even at the same
checkpoint**, per the pre-registered `next_50_checkpoint.json` rule written
by §18b. Morning opens; settle; do not retune the 12% floor from calibrator
edge shrinkage (raise *or* lower); optional NB/mixture count challengers and
richer external floors; (5) commit only with owner approval.

Same-game `PA` may be the TBF train/eval label, never a prediction-time feature.
