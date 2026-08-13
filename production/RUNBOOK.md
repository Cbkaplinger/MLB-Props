# Production Runbook

Detailed operations reference for daily production workflow.

## Scope

This runbook covers operational commands only.
Policy and statistical gating are maintained in `docs/reference/market_clv_gates.md`
and should not be duplicated here.

## Canonical Morning Loop

```text
1. refresh_statcast
2. refresh_features --skip-training
3. log_projections --allow-stale
4. grade_projections --all-logged --preferred-only
5. odds_board --unit 50
6. poll_odds --snapshot open --unit 50
7. grade_odds_ledger --status
```

## Core Commands

From repo root:

```powershell
.\.venv\Scripts\python.exe production/ops/refresh_statcast.py
.\.venv\Scripts\python.exe production/ops/refresh_features.py --skip-training
.\.venv\Scripts\python.exe production/projections/log_projections.py --allow-stale
.\.venv\Scripts\python.exe production/projections/grade_projections.py --all-logged --preferred-only --exclude-abbreviated --exclude-out-of-support
.\.venv\Scripts\python.exe production/odds/odds_board.py --unit 50
.\.venv\Scripts\python.exe production/odds/poll_odds.py --snapshot open --unit 50
.\.venv\Scripts\python.exe production/odds/grade_odds_ledger.py --status
```

Diagnostics-first risk gating (optional, not default):

```powershell
.\.venv\Scripts\python.exe production/odds/odds_board.py --unit 50 --quality-gate
.\.venv\Scripts\python.exe production/odds/poll_odds.py --snapshot open --unit 50 --quality-gate --dry-run
# optional policy override:
# .\.venv\Scripts\python.exe production/odds/odds_board.py --unit 50 --quality-gate --kpi-policy production/ops/kpi_policy.json
```

## CLV Close Watcher

```powershell
.\.venv\Scripts\python.exe production/odds/close_watcher.py
# or:
.\production\odds\run_close_watcher.ps1
```

One-shot close fill fallback:

```powershell
.\.venv\Scripts\python.exe production/odds/poll_odds.py --snapshot close
```

## Late-Open Catch-Up

Append only; do not replace open snapshot after morning lock:

```powershell
.\.venv\Scripts\python.exe production/odds/poll_odds.py --snapshot open --append --unit 50
```

## Settle and Skill Curve

```powershell
.\.venv\Scripts\python.exe production/odds/grade_odds_ledger.py --auto-settle-api --void-scratches --status --curve
```

The settle script also writes a gate-monitoring artifact each run:

- `artifacts/odds_log/gate_next_n_comparison.parquet`
- default window: latest `100` settled props (override with `--gate-next-n N`)

Manual overrides:

```powershell
.\.venv\Scripts\python.exe production/odds/grade_odds_ledger.py --settle "Logan Webb,2026-07-29,4"
.\.venv\Scripts\python.exe production/odds/grade_odds_ledger.py --close "Logan Webb,2026-07-29,+115,-120"
```

## Notebook Entry Points

- Deep-dive dashboard: `production/notebooks/results_dashboard.ipynb`
- Morning board: `production/notebooks/daily_projections.ipynb`
- KPI monitor: `production/notebooks/results_kpi_monitor.ipynb`
- Calibration monitor: `production/notebooks/results_calibration_lab.ipynb`
- Gate policy monitor: `production/notebooks/results_gate_policy.ipynb`
- PnL + CLV monitor: `production/notebooks/results_pnl_clv.ipynb`
- Recommendation audit: `production/notebooks/results_recommendation_audit.ipynb`
- Bettable cohort profile monitor: `production/notebooks/results_bettable_cohort.ipynb`
- Concise model results story: `analysis/model_results/model_results_story.ipynb`
- Notebook routing map: `production/notebooks/README.md`

## Required Artifact Check

```powershell
.\.venv\Scripts\python.exe scripts/check_notebook_artifacts.py
```

## One-Command Analysis Refresh

```powershell
powershell -ExecutionPolicy Bypass -File production/ops/run_analysis_notebooks.ps1
# options:
#   -NoStory            # run dashboard only
#   -SkipArtifactCheck  # skip scripts/check_notebook_artifacts.py
```

## One-Command Daily Operator Notebook Flow

```powershell
powershell -ExecutionPolicy Bypass -File production/ops/run_daily_operator_flow.ps1
# options:
#   -SkipArtifactCheck
#   -IncludeCalibration
#   -IncludeGatePolicy
#   -IncludeDeepDive
```

## Daily KPI Protocol

- Operational KPI policy and dynamic gate behavior:
  - `docs/reference/daily_kpi_protocol.md`
- Waste-sweep checklist:
  - `docs/reference/repo_waste_sweep_checklist.md`

Automation helpers:

```powershell
.\.venv\Scripts\python.exe production/ops/kpi_daily_action.py
.\.venv\Scripts\python.exe production/ops/weekly_kpi_report.py
.\.venv\Scripts\python.exe production/ops/policy_simulator.py --thresholds "0.08,0.10,0.12,0.14,0.16,0.18"
```

## Exit-Anomaly Labels (Ejections / Weather / Suspensions)

Use anomaly labels for model-evaluation/training hygiene, not for PnL overrides.

- Override table (manual + automated tags):  
  `production/ops/exit_anomaly_overrides.csv`
- Training mask artifact output:  
  `artifacts/projection_log/exit_anomaly_training_mask.parquet`

Build/rebuild mask:

```powershell
.\.venv\Scripts\python.exe scripts/build_exit_anomaly_overrides.py
.\.venv\Scripts\python.exe scripts/build_exit_anomaly_training_mask.py
.\.venv\Scripts\python.exe scripts/report_exit_anomaly_impact.py
.\.venv\Scripts\python.exe scripts/report_rolling_anomaly_policy_impact.py
# optional historical-status backfill for WF studies
.\.venv\Scripts\python.exe scripts/backfill_historical_exit_anomaly_overrides.py --start-season 2023 --end-season 2024
# optional model-quality checks:
.\.venv\Scripts\python.exe scripts/run_walkforward_anomaly_ab.py
.\.venv\Scripts\python.exe scripts/run_walkforward_anomaly_sensitivity.py
```

The script reports:

- override rows by `type/confidence/source`
- `include_for_training` row counts
- matched vs unmatched override keys (check `game_pk`, `pitcher`, `game_date` when unmatched)
- all-vs-core impact snapshots (`all`, `last_30d`, `last_7d`) in:
  `artifacts/projection_log/exit_anomaly_impact_report.json`
- rolling-policy contamination impact + PASS/WARN in:
  `artifacts/projection_log/rolling_anomaly_policy_impact.json`
- current walk-forward result under present historical tag density: neutral vs baseline

Notebook behavior:

- `production/notebooks/results_pnl_clv.ipynb` now shows both all-row and anomaly-filtered side-health views.
- Toggle `EXCLUDE_EXIT_ANOMALIES_FOR_PROCESS` in the setup cell to switch active analysis view.
- `production/notebooks/results_calibration_lab.ipynb` applies the same toggle to full decomposition diagnostics and prints all-vs-core comparison.
- `production/notebooks/results_bettable_cohort.ipynb` applies the same toggle to active cohort views and prints all-vs-core cohort health comparison.

## Key Artifact Outputs

- `artifacts/projection_log/projections.parquet`
- `artifacts/projection_log/graded.parquet`
- `artifacts/projection_log/exit_anomaly_training_mask.parquet`
- `artifacts/odds_log/ledger.parquet`
- `artifacts/odds_log/threshold_curve.parquet`
- `artifacts/odds_log/clv_reliability.parquet`
- `artifacts/odds_log/clv_floor_bca.parquet`
- `artifacts/odds_log/next_50_checkpoint.json`
- `artifacts/odds_log/k_error_decomposition.parquet`
- `artifacts/odds_log/k_error_decomposition_daily.parquet`
- `artifacts/odds_log/model_health_scorecard_daily.parquet`

## Changelog

- **2026-08-07**: Production paths finalized to role-based layout:
  `production/ops`, `production/odds`, `production/projections`,
  `production/notebooks`. Legacy root-level script/notebook paths removed.
