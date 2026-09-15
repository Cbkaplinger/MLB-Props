# models/ — frozen training artifacts (do not retrain without sign-off)

## Purpose

Versioned model stems + training code for the k-rate ensemble and TBF ridge.
The live bundle is FROZEN (retrain path closed; reopen on new data/offseason).

## Live stems (sha-pinned, resolved by `src/Python/live_assembly.py`)

- k-rate LightGBM ensemble: `lightgbm_krate_20260803_155401`
  (sparse72×0.0 + sparse72_mono×0.6 + final58×0.4), train 2023–24.
- TBF ridge: `tbf_pa_ridge_workload_context_bullpen_20260728_035607`.
- Calibration: WS1c per-line Platt (`prob_calibration_ws1c_platt_20260910_012559`).
- Count layer: Poisson (`COUNT_LAYER_FAMILY_DEFAULT`).

## Layout

- `Strikeout-Model/` — k-rate training + research sidecars (never promoted).
- `TBF-Model/` — workload ridge training.
- `artifacts/models/` (repo `artifacts/`, gitignored) — pointers, WS1c bundles,
  pre-promotion backups (revert paths).

## Rules

- Retrain challengers live in sidecars with native splits + member-vs-member
  judging (single-feature rule; family dumps banned).
- Promotion needs a ledger gate (≥0.0005 Brier) + weekly-pack confirm + sign-off.
- Research bundles never touch the live pointer (one-line revert each).
