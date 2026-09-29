# Production Runbook

Detailed operations reference for daily production workflow.

> **Work queue / approvals:** [`docs/EXECUTION_BACKLOG.md`](../docs/EXECUTION_BACKLOG.md) is the master instruction file. This runbook is how to run commands — not what to prioritize next.

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
6. poll_odds --snapshot open --unit 50 --from-recommendations
7. grade_odds_ledger --status
```

One command equivalent:

```powershell
powershell -ExecutionPolicy Bypass -File production/ops/run_morning_workflow.ps1
```

Optional post-score automation (free-tier MLOps):

```powershell
.\.venv\Scripts\python.exe production/ops/run_post_score_automation.py --append-lineage --operator "kapcam"
```

## Canonical Daily Process (linear, cloud primary since 2026-09-16 cutover)

1. **03:00** settle (post-game only) → **05:30** drift + grading → **08:00**
   morning (heal → projections → board → poll → always-fire alert) →
   **09:00–22:00** hourly (heal → re-log on fresh lineups → board → poll →
   watch → flips-only alert) → **q20min 12:00–22:12** close sweeps →
   next 03:00. All ET (`America/New_York` on Modal; see cloud README timing).

Backwards restart paths (in order, stop at the first that fixes it):
- Missed board: re-run the chain step (Modal) or laptop `run_morning_workflow.ps1`
  fallback; never fabricate a missed slate.
- Stale slate mid-day: `heal_stale_slate.py` (one repair cycle, always exit 0),
  then re-run board; residual staleness rides tags + banner, never a quit.
- Missing closes: `run_close_sweep.py --dry-run` to preview, then live; or
  `backfill_closes_from_cloud.py` for the one-way cloud→laptop merge.
- Unsettled yesterday: `grade_odds_ledger.py --auto-settle-api --void-scratches`;
  multi-day gap: `run_catchup.ps1` (grades only) or `run_wake_recovery.ps1`
  (full rebuild, never settles intraday, never fabricates).
- Silence (no heartbeat): Modal dashboard → volume `cloud_heartbeat.jsonl`
  recency per schedule; laptop tasks only on owner order (disabled at cutover).
- Duplicate pages: exactly one alerter must own sends (cloud primary;
  `MLB_PROPS_NO_ALERT=1` on whichever host is secondary).

## Core Commands

From repo root:

```powershell
.\.venv\Scripts\python.exe production/ops/refresh_statcast.py
.\.venv\Scripts\python.exe production/ops/refresh_features.py --skip-training
.\.venv\Scripts\python.exe production/projections/log_projections.py --allow-stale
.\.venv\Scripts\python.exe production/projections/grade_projections.py --all-logged --preferred-only --exclude-abbreviated --exclude-out-of-support
.\.venv\Scripts\python.exe production/odds/odds_board.py --unit 50 --roi-mode conservative
.\.venv\Scripts\python.exe production/odds/poll_odds.py --snapshot open --unit 50 --roi-mode conservative --from-recommendations
.\.venv\Scripts\python.exe production/odds/grade_odds_ledger.py --status
```

One-shot daily chain with monitoring + lineage:

```powershell
.\.venv\Scripts\python.exe production/ops/run_daily.py --allow-stale --run-monitoring --append-lineage --lineage-operator "kapcam"
```

Live scorer default:

- `production/ops/live_krate_ensemble.json` is active for k-rate blending in `score_slate.py` / `predict_slate.py`.
- If the file is missing, scoring falls back to the single frozen artifact.

Diagnostics-first risk gating (optional, not default):

```powershell
.\.venv\Scripts\python.exe production/odds/odds_board.py --unit 50 --quality-gate
.\.venv\Scripts\python.exe production/odds/poll_odds.py --snapshot open --unit 50 --quality-gate --dry-run
# optional policy override:
# .\.venv\Scripts\python.exe production/odds/odds_board.py --unit 50 --quality-gate --kpi-policy production/ops/kpi_policy.json
```

## CLV Close Watcher

> Laptop daemon = fallback only. Cloud close sweeps (q20min, ET-gated) are
> primary since the 2026-09-16 cutover. Keep the daemon files; do not run
> both primaries at once.

```powershell
.\.venv\Scripts\python.exe production/odds/close_watcher.py
# or:
.\production\odds\run_close_watcher.ps1
# or background launcher:
powershell -ExecutionPolicy Bypass -File production/ops/start_close_watcher_background.ps1
```

One-shot close fill fallback:

```powershell
.\.venv\Scripts\python.exe production/odds/poll_odds.py --snapshot close
```

## Late-Open Catch-Up

Append only; do not replace open snapshot after morning lock:

```powershell
.\.venv\Scripts\python.exe production/odds/poll_odds.py --snapshot open --append --unit 50 --allow-live-open-poll
```

## Settle and Skill Curve

```powershell
.\.venv\Scripts\python.exe production/odds/grade_odds_ledger.py --auto-settle-api --void-scratches --status --curve
# or:
powershell -ExecutionPolicy Bypass -File production/ops/run_end_of_day_settle.ps1
```

Hard guard (#113.1): `--auto-settle-api` settles only Live/Final games
(unstarted tickets log `API skip (unstarted)` and stay open; postponements
still void). Only post-game tasks pass the flag (end-of-day 03:00, nightly
drift 05:30) — `run_catchup.ps1` and morning/midday wrappers must not.

Paid-history clocks (observability, #113.0):

```powershell
.\.venv\Scripts\python.exe production/odds/grade_odds_ledger.py --attach-paid-clocks
```

Backfills friend-open / consensus-morning / consensus-close fair probs +
canonical `clv_paid_*_pp` onto ledger rows (fill-null, idempotent). Runs
warn-only at the end of `pull_regular_season_closeout.py`.

## Daily Scheduler (Windows Task Scheduler)

> Laptop tasks DISABLED at the 2026-09-16 cloud cutover; the laptop is
> fallback-only. Re-register below only on owner order (e.g. cloud outage).
> The 04:00–12:00 settle-backfill task is covered on cloud by the 03:00
> settle + 05:30 drift auto-settle pair — no cloud backfill job needed.

Create/update automated tasks:

```powershell
powershell -ExecutionPolicy Bypass -File production/ops/setup_automation_tasks.ps1 -MorningTime 08:00 -WatcherStartTime 11:30 -SettleTime 03:00
```

Recommended schedule:

```powershell
powershell -ExecutionPolicy Bypass -File production/ops/setup_automation_tasks.ps1 -MorningTime 08:00 -WatcherStartTime 11:30 -SettleTime 03:00
```

Creates:

- `MLBProps_MorningWorkflow`
- `MLBProps_CloseWatcherStart`
- `MLBProps_EndOfDaySettle`
- `MLBProps_NightlyDrift` (05:30 — best-effort settle→grade→drift→self-check
  + warn-only policy-freshness + stacker-gate shadow;
  pages ntfy on RED/step-failure only; YELLOW nights file quietly to
  `artifacts/odds_log/nightly_drift_latest.json` for morning review)

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
- Gate policy simulator audit: section inside `production/notebooks/results_bettable_cohort.ipynb` (`results_gate_policy.ipynb` retired 2026-09-17)
- PnL + CLV monitor: `production/notebooks/results_pnl_clv.ipynb`
- Recommendation audit: `production/notebooks/results_recommendation_audit.ipynb`
- Bettable cohort profile monitor: `production/notebooks/results_bettable_cohort.ipynb`
- Concise model results story: `analysis/model_results/model_results_story.ipynb`
- Notebook routing map: `production/notebooks/README.md`

## Required Artifact Check

```powershell
.\.venv\Scripts\python.exe scripts/check_notebook_artifacts.py
```

## Data Freshness Doctrine (never-again rule, 2026-09-28)

Savant, L1, L2, and L3 move in lockstep — same max game_date within 1 day,
always. L3 is rebuilt with every refresh (full `refresh_features.py`, never
`--skip-training` for the standing dataset); `--skip-training` is a live-scoring
shortcut only and must never be mistaken for dataset state.

```powershell
.\.venv\Scripts\python.exe production/ops/check_data_freshness.py
# exit 0 GREEN / 1 YELLOW / 2 RED; --refresh pulls + rebuilds when stale, then re-checks
```

In season (Apr–Sep) every artifact must sit within 2 days of yesterday ET; a
3+ day gap flags YELLOW/RED, never passes silently. Offseason the max must be a
completed season end (Sep 20+). Cancelled/unmade-up games are excluded only by
schedule-verified game_pk (`--exclude-pk`, logged in the report) — the coverage
gate itself is never weakened. 2027 guard: this check runs before the first
2027 scoring chain and weekly thereafter; any RED blocks the morning board until
a refresh clears it (chain wiring is a separately-approved deploy change).

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
.\.venv\Scripts\python.exe production/ops/run_daily_kpi_loop.py
.\.venv\Scripts\python.exe production/ops/calibration_snapshot.py --compare
.\.venv\Scripts\python.exe production/ops/build_daily_operator_summary.py
.\.venv\Scripts\python.exe production/ops/weekly_kpi_report.py
.\.venv\Scripts\python.exe production/ops/policy_simulator.py --thresholds "0.05,0.06,0.07,0.08,0.09,0.10,0.12"
.\.venv\Scripts\python.exe production/ops/policy_simulator.py --thresholds "0.05,0.06,0.07,0.08,0.09,0.10,0.12" --profile-over-floors "0.08,0.10,0.12" --profile-under-floors "0.06,0.08,0.10" --profile-min-bets 25
.\.venv\Scripts\python.exe production/ops/run_open_snapshot_counterfactual.py --start-date 2025-01-01 --end-date 2026-12-31 --floors "0.05,0.06,0.07,0.08,0.09,0.10,0.12" --side-floor-over 0.10 --side-floor-under 0.08 --output-tag fullsnap_2025_2026
.\.venv\Scripts\python.exe production/ops/run_model_ensemble_sweep.py --feature-set production_sparse72 --feature-set production_sparse72_monotone --feature-set production_final58_consensus --calibration-mode isotonic --weight-step 0.05 --floor-min 0.005 --floor-max 0.12 --floor-step 0.005 --min-bets 25 --dedupe-manual --output-tag ensemble_full_aug21_deduped
.\.venv\Scripts\python.exe production/ops/recalibrate_top3_ensembles_open_to_manual.py --ranked-ensemble-csv artifacts/odds_log/ensemble_sweep_ranked_ensemble_full_aug21_deduped.csv --top-n 3 --calibration-mode isotonic --floors "0.08,0.10,0.12" --dedupe-manual --output-tag aug21_deduped_top3_from_dedupedsweep
```

Current operating profile (champion, promoted 2026-09-11):

- `A_edge12` (from `production/ops/kpi_policy.json`)
  - `edge_min=0.12` + line floors; `edge_cap=0.24`; `under_lean_premium=0.04` (overs)
  - `fill_books=[draftkings, fanduel]`; `offset_cap=0.02`
- open-snapshot counterfactual optional side profile: `E_over10_under8`
  - `edge_min_over=0.10`
  - `edge_min_under=0.08`
- current **live** stack (2026-09-11): same blend `0.00 / 0.60 / 0.40`, juiced `edge_floor=0.12`, **Poisson** count layer, **WS1c Platt** pointer (not isotonic), 4.5-over veto, 2.5/3.5 probation `0.18`, postseason HOLD after `2026-09-27`.
- Aug-21 search-lane labels (historical, not live quality): open-universe winner was `production_sparse72` + `isotonic` + `edge_floor=0.12`; deduped-manual transfer winner used the same blend + isotonic. Do not cite those as the production calibrator.
- run this check at least once per day:

```powershell
.\.venv\Scripts\python.exe production/ops/kpi_daily_action.py --json
```

Artifact dedupe (report-first, safe workflow):

```powershell
.\.venv\Scripts\python.exe production/ops/prune_artifacts.py --target artifacts/model_quality --dry-run
# review artifacts/odds_log/prune_artifacts_last_report.json
# then apply:
.\.venv\Scripts\python.exe production/ops/prune_artifacts.py --target artifacts/model_quality --apply
```

Recalibration promotion gate check:

```powershell
.\.venv\Scripts\python.exe production/ops/kpi_daily_action.py --json
```

Promote only when `recalibration_promote_ready` is true and blockers are empty.

## Streamlit Operator App

```powershell
.\.venv\Scripts\python.exe -m streamlit run production/app/dashboard_streamlit.py
```

App intent:
- fast daily action + blocker visibility,
- calibration day-over-day tracking,
- side-floor scenario + profile scans,
- realized performance drilldown.

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
- `artifacts/odds_log/monitoring_cycle_latest.json`
- `artifacts/odds_log/monitoring_cycle_history.jsonl`
- `artifacts/model_registry/model_lineage_log.jsonl`
- `artifacts/model_registry/model_lineage_log.csv`

## Changelog

- **2026-08-07**: Production paths finalized to role-based layout:
  `production/ops`, `production/odds`, `production/projections`,
  `production/notebooks`. Legacy root-level script/notebook paths removed.
