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
- Daily KPI and dynamic gate policy: `docs/reference/daily_kpi_protocol.md`
- One-command notebook refresh script: `production/ops/run_analysis_notebooks.ps1`

## Notebook Entry Points

- Deep dive: `production/notebooks/results_dashboard.ipynb`
- Morning board: `production/notebooks/daily_projections.ipynb`
- Concise narrative view: `analysis/model_results/model_results_story.ipynb`
- KPI monitor (fast daily scan): `production/notebooks/results_kpi_monitor.ipynb`
- Calibration pocket monitor: `production/notebooks/results_calibration_lab.ipynb`
- Gate policy simulator view: `production/notebooks/results_gate_policy.ipynb`
- PnL + CLV progress monitor: `production/notebooks/results_pnl_clv.ipynb`
- Recommendation audit (all contexts, weak points): `production/notebooks/results_recommendation_audit.ipynb`
- Bettable cohort (filtered execution slice): `production/notebooks/results_bettable_cohort.ipynb`
- Notebook routing map: `production/notebooks/README.md`
- One-command daily operator flow: `production/ops/run_daily_operator_flow.ps1`

## Policy Simulation

Run scenario sweeps on edge-floor policy:

```powershell
python production/ops/policy_simulator.py --thresholds "0.08,0.10,0.12,0.14,0.16,0.18"
```

Run side-specific edge floors (for stricter `over`, looser `under`):

```powershell
python production/ops/policy_simulator.py --thresholds "0.08,0.10,0.12,0.14,0.16,0.18" --side-thresholds "over:0.14,under:0.10"
```

Writes:

- `artifacts/odds_log/policy_scenario_sweep.parquet` (historical snapshots)
- `artifacts/odds_log/policy_scenario_sweep_latest.csv` (latest run only)

## Exit-Anomaly Governance

Postgame anomaly labeling is live for process hygiene (not pregame inference features):

- Build/refresh overrides:
  - `python scripts/build_exit_anomaly_overrides.py`
- Rebuild training mask:
  - `python scripts/build_exit_anomaly_training_mask.py`
- Process impact report (all vs core + quality checks):
  - `python scripts/report_exit_anomaly_impact.py`
- Rolling contamination policy report (PASS/WARN):
  - `python scripts/report_rolling_anomaly_policy_impact.py`

Model-quality evaluators:

- Walk-forward A/B (baseline vs anomaly rolling policy):
  - `python scripts/run_walkforward_anomaly_ab.py`
- Medium-weight sensitivity + local-effect checks:
  - `python scripts/run_walkforward_anomaly_sensitivity.py`
