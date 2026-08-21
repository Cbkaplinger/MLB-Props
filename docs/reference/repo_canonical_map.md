# Canonical Surface Map

This file is the cleanup anchor for "what is canonical vs optional vs archive."

## Canonical casing policy

- Canonical root naming is lowercase for family references in code/docs:
  - `data/`
  - `models/`
  - `artifacts/`
- Top-level tracked roots were canonicalized in the 2026-08-18 passthrough (`Data` -> `data`, `Models` -> `models`); keep new references lowercase.

## Canonical daily surfaces

- `production/ops/run_daily.py` (morning refresh/score entrypoint)
- `production/odds/grade_odds_ledger.py` (settle + CLV updates)
- `production/ops/kpi_daily_action.py` (daily model action recommendation)
- `production/ops/policy_simulator.py` (edge-floor policy sweeps)
- `production/notebooks/daily_projections.ipynb` (today board and gate diagnostics)
- `production/notebooks/results_kpi_monitor.ipynb` (10-second health check)
- `production/notebooks/results_calibration_lab.ipynb` (matchup/rest miss pockets)
- `production/notebooks/results_gate_policy.ipynb` (BET/HOLD scenario tuning)
- `production/notebooks/results_pnl_clv.ipynb` (bankroll + CLV progress)

## Deep-dive but non-canonical daily reads

- `production/notebooks/results_dashboard.ipynb` (full deep-dive, archive-level detail)
- `analysis/model_results/model_results_story.ipynb` (narrative summary)

## Keep but do not treat as production

- `playground/` scripts (what-if and manual dry-runs only)
- `docs/archive/` (historical evidence only)
- `analysis/` notebooks (research narrative surface)

## Keep/Hold/Delete classification protocol

Apply one status per candidate file:

- `keep`: currently referenced, pipeline-critical, or provenance-critical.
- `hold`: uncertain value, possible future use, or pending owner decision.
- `delete`: proven duplicate/generated/disposable with zero critical references.

Required checks before `delete`:

1. No references in `production/`, `docs/`, `scripts/`, notebooks, or scheduler wrappers.
2. No imports/usages in `src/Python/` or `tests/`.
3. Duplicate claims are verified by hash or byte-equivalence.
4. Morning + settle smoke commands remain runnable.

## Deletion policy for bloat control

Delete only after all checks pass:

1. No references remain in `production/`, `docs/`, or scheduled scripts.
2. No import remains in `src/Python/` or `tests/`.
3. Morning loop + settle loop still run end-to-end.

## Current high-confidence cleanup targets

- Stale notebook outputs and duplicate ad-hoc analysis cells that are now covered by focused notebooks.
- One-off artifacts copied into tracked docs when the canonical source is in `artifacts/`.
- Dated non-protected artifacts via dry-run first:
  - `python scripts/prune_artifacts.py --min-age-days 45`

## Explicit non-targets for deletion

- `src/Python/` modeling and ops modules.
- `production/odds/` and `production/projections/`.
- Frozen model docs under `docs/research/` that are cited by manuscript/reference docs.
- Current `production/notebooks/*.ipynb` set.
- Policy/config surfaces under `production/ops/` (including `kpi_policy.json` and anomaly overrides).
