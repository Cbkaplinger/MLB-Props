# Repository Quality Passthrough Report (2026-08-18)

## Scope

- Applied a repository-wide quality pass with pipeline safety constraints.
- Integrated cleanup history into an executable Cursor skill.
- Used `keep` / `hold` / `delete` classification with safe-only deletion policy.
- Completed high-risk path canonicalization after explicit approval, then revalidated pipeline surfaces.

## Cleanup Results

- Added/expanded project cleanup skill:
  - `.cursor/skills/repo-quality-passthrough/SKILL.md`
  - `.cursor/skills/repo-quality-passthrough/reference.md`
- Executed top-level canonicalization rename batch:
  - `Data/` -> `data/`
  - `Models/` -> `models/`
  - used staged temporary names for Windows-safe rename sequencing
- Hardened ignore coverage for case/path drift and transient noise in `.gitignore`.
- Updated canonical cleanup guidance:
  - `docs/reference/repo_canonical_map.md`
  - `docs/reference/repo_waste_sweep_checklist.md`
- Synced paper-layer cleanup references:
  - `docs/paper/README.md`
  - `docs/paper/manuscript.md`

## Keep/Hold/Delete Ledger

| Path / Family | Decision | Evidence | Risk | Owner Action |
|---|---|---|---|---|
| `production/ops/` | keep | Direct pipeline orchestration and scheduler hooks | high if changed | none |
| `production/odds/` | keep | Live board, polling, grading, CLV tracking | high if changed | none |
| `production/projections/` | keep | Projection logging and grading chain | high if changed | none |
| `production/notebooks/*.ipynb` | keep | Referenced by runbook, operator flow, and app | high if moved/deleted | none |
| `src/Python/` | keep | Core package and pipeline internals | high if changed | none |
| `docs/archive/` | keep | Historical provenance references | medium | none |
| `analysis/` | hold | Research-narrative value, non-runtime | low | decide retention horizon |
| `playground/` | hold | Ad-hoc/manual scripts, future uncertain | medium | review per-file later |
| `data/Odds-Open-Close-2025-2026/` | hold | Large raw-ish data; likely useful | medium | confirm if canonical |
| cache artifacts (`__pycache__`, `.pyc`, `.pytest_cache`) | delete (safe) | Generated and reproducible | low | delete when convenient |

## Redundancy Findings

- Residual case-drift risk now mainly concerns accidental future mixed-case references, not tracked root folder casing.
- Operational command docs are intentionally duplicated across `README`/`RUNBOOK`/`INDEX`; this is acceptable only if index ownership remains clear.
- Notebook execution clones under `artifacts` remain generated surfaces and should be governed by retention policy (not by blind deletes).

## Pipeline Validation

Smoke checks run during this pass:

```powershell
.\.venv\Scripts\python.exe production/ops/run_daily.py --allow-stale
.\.venv\Scripts\python.exe production/odds/grade_odds_ledger.py --auto-settle-api --void-scratches --status
powershell -ExecutionPolicy Bypass -File production/ops/run_analysis_notebooks.ps1 -NoStory
```

Outcomes:

- `run_daily.py --allow-stale`: **failed due upstream Savant lag**, not path breakage (`missing official game_pk` in incremental Statcast fetch for 2026-08-17).
- `grade_odds_ledger.py --auto-settle-api --void-scratches --status`: **passed**.
- `run_analysis_notebooks.ps1 -NoStory`: **passed** (`results_dashboard.ipynb` executed and artifact checks passed).

Interpretation:

- No evidence of cleanup-induced path breakage in validated ops/notebook surfaces after canonicalization.
- Re-run the daily workflow once Savant data catch-up resolves.

## Approval Queue (not executed in this pass)

1. Physical relocation of `hold` families (`analysis/`, `playground/`, historical data slices)
   - Risk: medium/high (unknown future dependencies)
2. Aggressive artifact pruning beyond generated caches
   - Risk: medium (possible evidence loss)
