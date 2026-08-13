# Exit Anomaly Protocol

Purpose: prevent exogenous exits (ejections, weather-shortened starts, suspensions) from distorting model-evaluation and retraining decisions.

## Principles

- **PnL truth is unchanged.** Settled ledger outcomes remain official.
- **Process diagnostics split views.** Always inspect:
  - all rows
  - anomaly-filtered core rows
- **Pregame leakage safety remains intact.** Exit anomaly labels are postgame QC tags, not inference-time features.

## Override table

Path: `production/ops/exit_anomaly_overrides.csv`

Required key columns:

- `game_pk`
- `pitcher`
- `game_date`

Recommended metadata:

- `exit_anomaly_flag` (bool)
- `exit_anomaly_type` (e.g., `ejection`, `weather_shortened`, `suspension_shortened`, `other_exogenous`)
- `exit_anomaly_confidence` (`high`, `medium`, `low`)
- `exit_anomaly_source` (`manual_override`, `mlb_feed_event`, `game_status`)
- `note`

## Build training mask

```powershell
.\.venv\Scripts\python.exe scripts/build_exit_anomaly_overrides.py
.\.venv\Scripts\python.exe scripts/build_exit_anomaly_training_mask.py
.\.venv\Scripts\python.exe scripts/report_exit_anomaly_impact.py
.\.venv\Scripts\python.exe scripts/report_rolling_anomaly_policy_impact.py
# optional historical backfill for walk-forward studies
.\.venv\Scripts\python.exe scripts/backfill_historical_exit_anomaly_overrides.py --start-season 2023 --end-season 2024
```

Output: `artifacts/projection_log/exit_anomaly_training_mask.parquet`

The override/mask scripts print:

- counts by anomaly `type/confidence/source`
- counts by `include_for_training`
- override match diagnostics (matched/unmatched rows)
- PASS/WARN status fields in process/rolling impact artifacts

If unmatched rows exist, check key alignment (`game_pk`, `pitcher`, `game_date`) against `graded.parquet`.

## Verification checklist

1. **Key match integrity**
   - unmatched override count should be 0 unless intentionally future-dated
2. **Tag-rate sanity**
   - anomaly rate should be low and plausible by season/date
3. **Downstream impact**
   - compare all-row vs anomaly-filtered metrics (MAE/RMSE/R², calibration, side bias)
4. **Policy stability**
   - avoid retraining solely on one incident; require sustained impact

## Retraining policy

- Do **not** retrain immediately after a single anomaly.
- Retrain only if anomaly-filtered diagnostics show consistent, material improvement over a meaningful sample.
- Prefer phased adoption:
  1. diagnostics split only
  2. optional training exclusion/downweight experiments
  3. promotion if out-of-sample benefits persist

## Rolling-window contamination policy

To prevent exogenous exits from tainting future rolling priors:

- `high` confidence anomaly rows are excluded from rolling-feature updates (weight `0.0`)
- `medium` confidence rows are downweighted in rolling-feature updates (weight `0.5`)
- `low` confidence rows keep full rolling weight (`1.0`)

This policy affects **feature updates only**; true labels remain unchanged for
evaluation and settled-PnL accounting.

## Current evidence (2026-08)

- Walk-forward A/B and medium-weight sensitivity runners are implemented.
- Historical 2023-2024 status backfill currently yields low anomaly density.
- Under present tag coverage, walk-forward aggregate metrics remain neutral vs baseline.
