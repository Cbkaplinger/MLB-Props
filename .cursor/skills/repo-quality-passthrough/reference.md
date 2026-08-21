# Repo Quality Reference

## Protected-by-default families

- `production/ops/`
- `production/odds/`
- `production/projections/`
- `production/notebooks/`
- `src/Python/`
- `artifacts/models/`
- `artifacts/projection_log/`
- `artifacts/odds_log/`
- `artifacts/feature_research/`
- `artifacts/stabilization/`
- `artifacts/count_layer/`

## Known risk surfaces

- Case drift: `data/` vs `data/`, `models/` vs `models/`, `artifacts/` vs `artifacts/`
- Duplicate notebook execution trees under `artifacts/notebook_exec/`
- Repeated command references across root `README.md`, `production/README.md`, `production/RUNBOOK.md`, and `production/INDEX.md`

## Required pre-delete checks

1. Search path references across scripts, notebooks, docs, and tests.
2. Verify scheduler/task wrappers do not reference candidate paths.
3. If duplicate claim: verify hash or exact semantic equivalence.
4. Build rollback list for each delete/move batch.

## Smoke checks (MLB-Props)

Run these after approved cleanup/move batches:

```powershell
.\.venv\Scripts\python.exe production/ops/run_daily.py --allow-stale
.\.venv\Scripts\python.exe production/odds/grade_odds_ledger.py --auto-settle-api --void-scratches --status
powershell -ExecutionPolicy Bypass -File production/ops/run_analysis_notebooks.ps1
```

## Canonical docs to keep in sync

- `docs/reference/repo_canonical_map.md`
- `docs/reference/daily_kpi_protocol.md`
- `production/INDEX.md`
- `production/RUNBOOK.md`
- `production/README.md`
