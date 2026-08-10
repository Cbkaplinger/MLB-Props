# Production Ops

Runtime entrypoints and notebooks for daily live scoring, projection logging,
odds/CLV tracking, and holdout monitoring.

## Overview

- `production/ops/` — refresh + scoring chain
- `production/projections/` — projection logging/grading + post-freeze holdout
- `production/odds/` — board, open/close polling, ledger grading
- `production/notebooks/` — deep-dive dashboards

## Documentation Map

- Quick command map: `production/INDEX.md`
- Detailed operating runbook: `production/RUNBOOK.md`
- CLV policy + gates: `docs/reference/market_clv_gates.md`
- Model diagnostics workflow: `docs/reference/results_dashboard_diagnostics.md`
- One-command notebook refresh script: `production/ops/run_analysis_notebooks.ps1`

## Notebook Entry Points

- Deep dive: `production/notebooks/results_dashboard.ipynb`
- Morning board: `production/notebooks/daily_projections.ipynb`
- Concise narrative view: `analysis/model_results/model_results_story.ipynb`
