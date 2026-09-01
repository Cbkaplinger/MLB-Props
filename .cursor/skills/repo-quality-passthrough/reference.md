# Repo Quality Reference

## Protected-by-default families

- `production/ops/`
- `production/odds/`
- `production/projections/`
- `production/notebooks/`
- `src/Python/`
- `docs/EXECUTION_BACKLOG.md` (holy work-state file — never ignore / never delete)
- Local generated (prefer ignore, do not blind-delete):
  - `artifacts/models/`
  - `artifacts/projection_log/`
  - `artifacts/odds_log/`
  - `artifacts/feature_research/`
  - `artifacts/stabilization/`
  - `artifacts/count_layer/`
  - `artifacts/model_quality/`
  - `artifacts/notebook_exec/`

## Known risk surfaces

- Case drift on Windows (`Data/` vs `data/`, `Models/` vs `models/`, `Artifacts/` vs `artifacts/`). Prefer lowercase in all new docs/code; keep both casings in `.gitignore`.
- Duplicate notebook execution trees under `artifacts/notebook_exec/`.
- Repeated command references across root `README.md`, `production/README.md`, `production/RUNBOOK.md`, and `production/INDEX.md` — keep commands aligned; do not invent a second work queue.
- Competing “next steps” prose outside `docs/EXECUTION_BACKLOG.md` — always redirect to the backlog.

## Required pre-delete checks

1. Search path references across scripts, notebooks, docs, and tests.
2. Verify scheduler/task wrappers do not reference candidate paths.
3. If duplicate claim: verify hash or exact semantic equivalence.
4. Build rollback list for each delete/move batch.

## Smoke checks (MLB-Props)

Run these after approved cleanup/move batches (from repo root; venv is `.venv`):

```powershell
.\.venv\Scripts\python.exe -m py_compile production/ops/run_daily.py production/odds/grade_odds_ledger.py
.\.venv\Scripts\python.exe production/odds/grade_odds_ledger.py --status
# Heavier (only when ops path moved):
# .\.venv\Scripts\python.exe production/ops/run_daily.py --allow-stale
# powershell -ExecutionPolicy Bypass -File production/ops/run_analysis_notebooks.ps1
```

## Canonical docs to keep in sync

- `docs/EXECUTION_BACKLOG.md` (master work-state — wins over all other “next steps”)
- `AGENTS.md` + `.cursor/rules/execution-backlog.mdc`
- `docs/reference/repo_canonical_map.md`
- `docs/reference/daily_kpi_protocol.md`
- `docs/reference/reports/repo_quality_hold_inventory_2026-09-01.md` (latest hold ledger)
- `production/INDEX.md`
- `production/RUNBOOK.md`
- `production/README.md`
