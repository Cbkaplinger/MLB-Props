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
- Repo cleanup governance: `docs/reference/repo_canonical_map.md`, `docs/reference/repo_waste_sweep_checklist.md`
- One-command notebook refresh script: `production/ops/run_analysis_notebooks.ps1`
- Daily KPI loop + calibration snapshots: `production/ops/run_daily_kpi_loop.py`,
  `production/ops/calibration_snapshot.py`
- Artifact dedupe utility (report-first): `production/ops/prune_artifacts.py`
- Streamlit operator app: `production/app/dashboard_streamlit.py`

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

## Live Odds Board Policy Mode

Use the ROI-mode preset for stable daily execution:

```powershell
.\.venv\Scripts\python.exe production/odds/odds_board.py --unit 50 --roi-mode balanced
```

Available modes:

- `aggressive` (edge floor 0.14)
- `balanced` (edge floor 0.16)
- `conservative` (edge floor 0.18)

Each mode auto-enables line-price correction, line-aware floors, and deploy-matrix filtering.

## Streamlit Operator Dashboard

Run from repo root:

```powershell
python -m streamlit run production/app/dashboard_streamlit.py
```

The app reads existing artifacts and presents:
- daily action + promotion blockers,
- calibration trend/snapshot deltas,
- policy sweep and side-profile scans,
- realized daily and rolling performance.

## Policy Simulation

Run scenario sweeps on edge-floor policy:

```powershell
python production/ops/policy_simulator.py --thresholds "0.08,0.10,0.12,0.14,0.16,0.18"
```

Run side-specific edge floors (for stricter `over`, looser `under`):

```powershell
python production/ops/policy_simulator.py --thresholds "0.08,0.10,0.12,0.14,0.16,0.18,0.20" --side-thresholds "over:0.18,under:0.12"
```

Writes:

- `artifacts/odds_log/policy_scenario_sweep.parquet` (historical snapshots)
- `artifacts/odds_log/policy_scenario_sweep_latest.csv` (latest run only)

Current live policy default (from `production/ops/kpi_policy.json`):

- profile: `D_over18_under12`
- over floor: `0.18`
- under floor: `0.12`
- context: keep this side-specific profile while `kpi_daily_action` remains in `RECALIBRATE`.

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
