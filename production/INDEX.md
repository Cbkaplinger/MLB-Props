# Production Command Index

Quick routing: "I need to do X -> run Y".

## Core Daily Commands

- Refresh Statcast:
  - `python production/ops/refresh_statcast.py`
- Refresh features:
  - `python production/ops/refresh_features.py --skip-training`
- Score slate:
  - `python production/ops/score_slate.py --live --allow-stale`
- One-shot chain:
  - `python production/ops/run_daily.py --allow-stale`
- Daily KPI action recommendation:
  - `python production/ops/kpi_daily_action.py`
- Weekly KPI artifact refresh:
  - `python production/ops/weekly_kpi_report.py`

## Projection Logging and Grading

- Log projections:
  - `python production/projections/log_projections.py --allow-stale`
- Grade projections:
  - `python production/projections/grade_projections.py --all-logged --preferred-only`
- Frozen post-freeze monitor:
  - `python production/projections/post_freeze_holdout.py`

## Odds and CLV Workflow

- Build recommendation board:
  - `python production/odds/odds_board.py --unit 50`
  - diagnostic risk filter: `python production/odds/odds_board.py --unit 50 --quality-gate`
  - policy override: `python production/odds/odds_board.py --unit 50 --quality-gate --kpi-policy production/ops/kpi_policy.json`
- Open snapshot to ledger:
  - `python production/odds/poll_odds.py --snapshot open --unit 50`
  - gate-aware dry run: `python production/odds/poll_odds.py --snapshot open --unit 50 --quality-gate --dry-run`
- Close watcher (continuous):
  - `python production/odds/close_watcher.py`
  - or `production/odds/run_close_watcher.ps1`
- Grade/settle odds ledger:
  - `python production/odds/grade_odds_ledger.py --status --curve`

## Notebook Workflow

- Deep-dive dashboard:
  - `production/notebooks/results_dashboard.ipynb`
- Daily projections notebook:
  - `production/notebooks/daily_projections.ipynb`
- Focused monitors:
  - `production/notebooks/results_kpi_monitor.ipynb`
  - `production/notebooks/results_calibration_lab.ipynb`
  - `production/notebooks/results_gate_policy.ipynb`
  - `production/notebooks/results_pnl_clv.ipynb`
  - `production/notebooks/results_recommendation_audit.ipynb`
  - `production/notebooks/results_bettable_cohort.ipynb`
- Daily operator flow (execute essential notebooks in order):
  - `powershell -ExecutionPolicy Bypass -File production/ops/run_daily_operator_flow.ps1`
  - options:
    - `-SkipArtifactCheck`
    - `-IncludeCalibration`
    - `-IncludeGatePolicy`
    - `-IncludeDeepDive`
- Notebook routing map:
  - `production/notebooks/README.md`
- Concise model-results story:
  - `analysis/model_results/model_results_story.ipynb`
- One-command notebook refresh:
  - `powershell -ExecutionPolicy Bypass -File production/ops/run_analysis_notebooks.ps1`
  - dashboard only: `powershell -ExecutionPolicy Bypass -File production/ops/run_analysis_notebooks.ps1 -NoStory`

## Policy Simulation

- Edge-floor scenario sweep:
  - `python production/ops/policy_simulator.py --thresholds "0.08,0.10,0.12,0.14,0.16,0.18"`

## Exit-Anomaly Commands

- Build source-backed override table:
  - `python scripts/build_exit_anomaly_overrides.py`
- Rebuild training mask:
  - `python scripts/build_exit_anomaly_training_mask.py`
- Process impact report:
  - `python scripts/report_exit_anomaly_impact.py`
- Rolling contamination report:
  - `python scripts/report_rolling_anomaly_policy_impact.py`
- Walk-forward A/B:
  - `python scripts/run_walkforward_anomaly_ab.py`
- Walk-forward sensitivity grid:
  - `python scripts/run_walkforward_anomaly_sensitivity.py`

## Pre-Notebook Artifact Check

- `python scripts/check_notebook_artifacts.py`

## Further Reference

For detailed operations and rationale, see `production/RUNBOOK.md`.
