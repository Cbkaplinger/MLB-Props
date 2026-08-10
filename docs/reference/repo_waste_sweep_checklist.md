# Repo Waste Sweep Checklist

This checklist tracks low-value surface area and safe cleanup opportunities.

## Current findings

- **Environment noise:** `.gitignore` already excludes `.venv/`, `__pycache__/`, and `*.pyc`.
- **Legacy production root shims:** no active root-level shim scripts detected in `production/`.
- **Notebook output bloat risk:** keep outputs out of commits when possible; rely on artifacts for persistent metrics.
- **Docs drift risk:** policy text should link to canonical docs instead of duplicating long rationale.

## Safe keep/delete guidance

### Keep

- `production/ops/`, `production/odds/`, `production/projections/`, `production/notebooks/`
- `docs/reference/daily_kpi_protocol.md` as the daily decision source
- `production/ops/kpi_policy.json` as the single threshold/gate config source

### Candidate cleanup (after dependency check)

- Any saved terminal snippets/aliases still using pre-refactor `production/<script>.py` paths
- Historical one-off scratch scripts under `scripts/` (only if no runbook references remain)
- Large committed notebook outputs if they are not needed for review history

## Before deleting anything

1. Verify no scheduler/task/alias still references the target.
2. Search docs and scripts for path references.
3. Run a full morning loop + settle + notebook refresh once.
4. Remove file/path and rerun smoke checks.

## Smoke checks

- `.\.venv\Scripts\python.exe production/ops/run_daily.py --allow-stale`
- `.\.venv\Scripts\python.exe production/odds/grade_odds_ledger.py --auto-settle-api --void-scratches --status`
- `powershell -ExecutionPolicy Bypass -File production/ops/run_analysis_notebooks.ps1`
