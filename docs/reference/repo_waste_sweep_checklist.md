# Repo Waste Sweep Checklist

This checklist tracks low-value surface area and safe cleanup opportunities.

## Current findings

- **Environment noise:** `.gitignore` already excludes `.venv/`, `__pycache__/`, and `*.pyc`.
- **Legacy production root shims:** no active root-level shim scripts detected in `production/`.
- **Notebook output bloat risk:** keep outputs out of commits when possible; rely on artifacts for persistent metrics.
- **Docs drift risk:** policy text should link to canonical docs instead of duplicating long rationale.
- **Dashboard sprawl risk:** deep-dive cells are now complemented by focused monitors (`results_kpi_monitor`, `results_calibration_lab`, `results_gate_policy`, `results_pnl_clv`).
- **2026-08-11 dependency audit:** every `production/notebooks/*.ipynb` and `production/ops/*.py` file is still referenced by docs/scripts/notebooks; no safe deletions in those folders yet.
- **2026-08-18 quality passthrough:** `keep/hold/delete` workflow formalized in `.cursor/skills/repo-quality-passthrough/`; canonical casing policy set to lowercase references (`data`, `models`, `artifacts`) with staged migration only.

## Safe keep/delete guidance

### Keep

- `production/ops/`, `production/odds/`, `production/projections/`, `production/notebooks/`
- `docs/reference/daily_kpi_protocol.md` as the daily decision source
- `production/ops/kpi_policy.json` as the single threshold/gate config source

### Candidate cleanup (after dependency check)

- Any saved terminal snippets/aliases still using pre-refactor `production/<script>.py` paths
- Historical one-off scratch scripts under `scripts/` (only if no runbook references remain)
- Large committed notebook outputs if they are not needed for review history
- Verbose duplicate guidance across markdown docs when canonical path already exists in:
  - `docs/reference/repo_canonical_map.md`
  - `docs/reference/daily_kpi_protocol.md`
  - `production/README.md`
- Date-tagged non-protected artifact files (dry-run + allowlist):
  - `python scripts/prune_artifacts.py --min-age-days 45`
- Cache-only files/folders (`__pycache__`, `.pyc`, `.pytest_cache`) whenever present outside virtual env.

### Explicitly protected (do not delete)

- `production/notebooks/*.ipynb` current set (deep-dive + focused monitors)
- `production/ops/*.py` current set (daily ops + KPI/policy tooling)
- Core model/data pipeline modules under `src/Python/`
- `artifacts/{models,projection_log,odds_log,feature_research,stabilization,count_layer}/`
- `production/ops/kpi_policy.json` and `production/ops/exit_anomaly_overrides.csv`

## Before deleting anything

1. Verify no scheduler/task/alias still references the target.
2. Search docs and scripts for path references.
3. Run a full morning loop + settle + notebook refresh once.
4. Remove file/path and rerun smoke checks.

## Smoke checks

- `.\.venv\Scripts\python.exe production/ops/run_daily.py --allow-stale`
- `.\.venv\Scripts\python.exe production/odds/grade_odds_ledger.py --auto-settle-api --void-scratches --status`
- `powershell -ExecutionPolicy Bypass -File production/ops/run_analysis_notebooks.ps1`
