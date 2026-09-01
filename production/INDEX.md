# Production Command Index

Quick routing: "I need to do X -> run Y".

> **Work queue / approvals:** [`docs/EXECUTION_BACKLOG.md`](../docs/EXECUTION_BACKLOG.md) is the master plan (PAST/PRESENT/FORWARD/DEFERRED). This index is command routing only — not a competing backlog.

## Core Daily Commands

- Refresh Statcast:
  - `python production/ops/refresh_statcast.py`
- Refresh features:
  - `python production/ops/refresh_features.py --skip-training`
- Score slate:
  - `python production/ops/score_slate.py --live --allow-stale`
- One-shot chain:
  - `python production/ops/run_daily.py --allow-stale`
  - with monitoring + lineage:
    - `python production/ops/run_daily.py --allow-stale --run-monitoring --append-lineage --lineage-operator "kapcam"`
- Live k-rate ensemble config (active default):
  - `production/ops/live_krate_ensemble.json`
- Daily KPI action recommendation:
  - `python production/ops/kpi_daily_action.py`
- One-command daily KPI loop (settle/grade/notebooks/KPI summary):
  - `python production/ops/run_daily_kpi_loop.py`
- One-page operator summary artifacts:
  - `python production/ops/build_daily_operator_summary.py`
- Build non-K shadow diagnostics from watcher history:
  - `python production/ops/build_aux_market_shadow_score.py`
- Post-score automation only (monitoring + optional lineage):
  - `python production/ops/run_post_score_automation.py --append-lineage --operator "kapcam"`
- Artifact dedupe (report-first dry run):
  - `python production/ops/prune_artifacts.py --target artifacts/model_quality --dry-run`
- Artifact dedupe apply (after reviewing report):
  - `python production/ops/prune_artifacts.py --target artifacts/model_quality --apply`
- Capture calibration snapshot and day-over-day deltas:
  - `python production/ops/calibration_snapshot.py --compare`
- Weekly KPI artifact refresh:
  - `python production/ops/weekly_kpi_report.py`
- One-command morning workflow (model slate + board + open ledger + status):
  - `powershell -ExecutionPolicy Bypass -File production/ops/run_morning_workflow.ps1`
- Midday/second refresh chain (board + poll + shadow + monitoring + alert):
  - `powershell -ExecutionPolicy Bypass -File production/ops/run_market_refresh.ps1`
- One-command end-of-day settle:
  - `powershell -ExecutionPolicy Bypass -File production/ops/run_end_of_day_settle.ps1`
- Start close watcher in background:
  - `powershell -ExecutionPolicy Bypass -File production/ops/start_close_watcher_background.ps1`
- Create/update daily scheduled automation tasks:
  - `powershell -ExecutionPolicy Bypass -File production/ops/setup_automation_tasks.ps1 -MorningTime 08:30 -WatcherStartTime 11:30 -SettleTime 03:00`
- Run one-shot automation health snapshot:
  - `python production/ops/build_automation_self_check.py --notify-on-red`

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
  - champion mode: `python production/odds/odds_board.py --unit 50 --roi-mode conservative`
  - diagnostic risk filter: `python production/odds/odds_board.py --unit 50 --quality-gate`
  - policy override: `python production/odds/odds_board.py --unit 50 --quality-gate --kpi-policy production/ops/kpi_policy.json`
- Open snapshot to ledger:
  - `python production/odds/poll_odds.py --snapshot open --unit 50 --from-recommendations`
  - champion mode: `python production/odds/poll_odds.py --snapshot open --unit 50 --roi-mode conservative --from-recommendations`
  - gate-aware dry run: `python production/odds/poll_odds.py --snapshot open --unit 50 --quality-gate --dry-run`
  - diagnostics-only live polling override: `python production/odds/poll_odds.py --snapshot open --unit 50 --allow-live-open-poll`
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

## Streamlit App

- Operator dashboard app:
  - `streamlit run production/app/dashboard_streamlit.py`

## Policy Simulation

- Edge-floor scenario sweep:
  - `python production/ops/policy_simulator.py --thresholds "0.05,0.06,0.07,0.08,0.09,0.10,0.12"`
- Side-specific profile scan (stricter overs vs looser unders):
  - `python production/ops/policy_simulator.py --thresholds "0.05,0.06,0.07,0.08,0.09,0.10,0.12" --profile-over-floors "0.08,0.10,0.12" --profile-under-floors "0.06,0.08,0.10" --profile-min-bets 25`
  - current live profile in policy: `A_edge12` (`edge=0.12`)
- Full snapshot-level open-universe counterfactual replay:
  - `python production/ops/run_open_snapshot_counterfactual.py --start-date 2025-01-01 --end-date 2026-12-31 --floors "0.05,0.06,0.07,0.08,0.09,0.10,0.12" --side-floor-over 0.10 --side-floor-under 0.08 --output-tag fullsnap_2025_2026`
- Build segment-aware calibration offsets (line + price + maturity):
  - `python production/ops/build_segment_calibration_offsets.py --min-n 60 --shrink-prior-n 200 --offset-cap 0.08`
- Deduped ensemble winner sweep (one-opportunity-one-bet fairness):
  - `python production/ops/run_model_ensemble_sweep.py --feature-set production_sparse72 --feature-set production_sparse72_monotone --feature-set production_final58_consensus --calibration-mode isotonic --weight-step 0.05 --floor-min 0.005 --floor-max 0.12 --floor-step 0.005 --min-bets 25 --dedupe-manual --output-tag ensemble_full_aug21_deduped`
- Recalibrate top-3 from ranked sweep and compare recommended bets against manual set:
  - `python production/ops/recalibrate_top3_ensembles_open_to_manual.py --ranked-ensemble-csv artifacts/odds_log/ensemble_sweep_ranked_ensemble_full_aug21_deduped.csv --top-n 3 --calibration-mode isotonic --floors "0.08,0.10,0.12" --dedupe-manual --output-tag aug21_deduped_top3_from_dedupedsweep`
- One-command champion/challenger + ensemble transfer:
  - `python production/ops/run_champion_challenger_cycle.py --run-ensemble --output-tag cc_cycle_latest`

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
