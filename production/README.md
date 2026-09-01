# Production Ops

Runtime entrypoints and notebooks for daily live scoring, projection logging,
odds/CLV tracking, and holdout monitoring.

## Overview

- `production/ops/` — refresh + scoring chain
- `production/projections/` — projection logging/grading + post-freeze holdout
- `production/odds/` — board, open/close polling, ledger grading
- `production/notebooks/` — deep-dive dashboards

## Metric lane definitions

- **Single-model MAE lane:** model-family accuracy ranking. Current best observed
  `mean_expected_k_mae` is about `1.7621`.
- **Ensemble deployment lane:** active king is selected on decision metrics
  (market-skill, ROI/risk path, fairness constraints), not expected-K MAE rank.
- **Legacy baselines:** prior freeze-era benchmark metrics are retained only as
  historical context and are not active deployment claims.

## Documentation Map

- **Work queue / approvals (master):** `docs/EXECUTION_BACKLOG.md` (see also root `AGENTS.md`)
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
- Model lineage logger: `production/ops/log_model_lineage.py`
- Monitoring cycle runner (`t=0` input + `t+1` quality): `production/ops/run_monitoring_cycle.py`
- Post-score automation wrapper: `production/ops/run_post_score_automation.py`

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

**Freeze stamp (active):** `KING_PROFILE_AUG2026` (frozen 2026-08-21).  
Treat this profile as fixed production policy until an explicit re-test/re-freeze cycle is completed.

Use the ROI-mode preset for stable daily execution:

```powershell
.\.venv\Scripts\python.exe production/odds/odds_board.py --unit 50 --roi-mode conservative
.\.venv\Scripts\python.exe production/odds/poll_odds.py --snapshot open --unit 50 --roi-mode conservative --from-recommendations
```

Available modes:

- `aggressive` (edge floor 0.08)
- `balanced` (edge floor 0.10)
- `conservative` (edge floor 0.12)
- `profit_lock` (edge floor 0.08; side floors over=0.10, under=0.08)

Each mode auto-enables line-price correction, line-aware floors, and deploy-matrix filtering.
Open-ledger execution is parity-locked to the board artifact via `--from-recommendations`.

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

- profile: `A_edge12`
- flat floor: `0.12`
- optional side profile for counterfactual runs: `E_over10_under8`
- context: open-snapshot counterfactual replay currently favors `production_sparse72` + `isotonic` + `edge_floor=0.12` under positive-skill gating.

## Open-Snapshot Counterfactual Replay

Use this when validating on the full 2025-2026 open opportunity universe (not manual tickets):

```powershell
python production/ops/run_open_snapshot_counterfactual.py --start-date 2025-01-01 --end-date 2026-12-31 --floors "0.05,0.06,0.07,0.08,0.09,0.10,0.12" --side-floor-over 0.10 --side-floor-under 0.08 --output-tag fullsnap_2025_2026
```

Primary outputs:

- `artifacts/odds_log/open_snapshot_counterfactual_fullsnap_2025_2026.csv`
- `artifacts/odds_log/open_snapshot_counterfactual_fullsnap_2025_2026_ranked.csv`
- `artifacts/odds_log/open_snapshot_counterfactual_fullsnap_2025_2026.json`

## Segment-Aware Calibration Offsets

To correct persistent weak pockets by line + price + maturity before edge/floor
evaluation, build segmented offsets from the open snapshot panel:

```powershell
python production/ops/build_segment_calibration_offsets.py --min-n 60 --shrink-prior-n 200 --offset-cap 0.08
```

Outputs:

- `artifacts/odds_log/line_price_correction_table_segmented.parquet`
- `artifacts/odds_log/line_price_correction_table_segmented_summary.json`

Runtime behavior:

- `src/Python/odds_board.py` automatically prefers segmented offsets when present.
- Lookup is exact on `(line, over_price_bucket, maturity_bucket)` with wildcard fallback on maturity.

## Deduped Ensemble Governance (Current Sharpest Path)

Use this to enforce one-opportunity-one-bet fairness on manual replay while still
training calibration on the larger 2025-2026 open panel:

```powershell
python production/ops/run_model_ensemble_sweep.py --feature-set production_sparse72 --feature-set production_sparse72_monotone --feature-set production_final58_consensus --calibration-mode isotonic --weight-step 0.05 --floor-min 0.005 --floor-max 0.12 --floor-step 0.005 --min-bets 25 --dedupe-manual --output-tag ensemble_full_aug21_deduped
python production/ops/recalibrate_top3_ensembles_open_to_manual.py --ranked-ensemble-csv artifacts/odds_log/ensemble_sweep_ranked_ensemble_full_aug21_deduped.csv --top-n 3 --calibration-mode isotonic --floors "0.08,0.10,0.12" --dedupe-manual --output-tag aug21_deduped_top3_from_dedupedsweep
```

Primary outputs:

- `artifacts/odds_log/ensemble_sweep_ranked_ensemble_full_aug21_deduped.csv`
- `artifacts/odds_log/open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.csv`
- `artifacts/odds_log/open_top3_transfer_bestfloor_picks_aug21_deduped_top3_from_dedupedsweep.csv`
- `artifacts/odds_log/open_top3_transfer_bestfloor_overlap_aug21_deduped_top3_from_dedupedsweep.csv`

## Live K-Rate Ensemble (Now Active)

Live scoring now defaults to an ensemble k-rate path in `src/Python/live_assembly.py`
using:

- config: `production/ops/live_krate_ensemble.json`
- winner weights: `0.00 sparse72 / 0.60 sparse72_monotone / 0.40 final58`
- artifacts:
  - `artifacts/models/lightgbm_krate_20260821_054152`
  - `artifacts/models/lightgbm_krate_mono_20260821_054127`
  - `artifacts/models/lightgbm_krate_20260821_054126`

Single-model fallback remains available if ensemble config is absent.

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
