# Daily KPI Protocol (Dynamic Gating + Priorities)

This protocol defines the daily decision loop for model calibration and quality-gate
behavior. It is intentionally dynamic: thresholds are operational guardrails that can
be tightened or relaxed as sample size and date coverage grow.

Policy values are sourced from:

- `production/ops/kpi_policy.json`

## Purpose

- Keep day-to-day work focused on the highest-ROI fixes.
- Avoid feature churn while calibration and workload bias are unresolved.
- Tie gate strictness to observed model health rather than fixed intuition.

## Inputs (artifacts)

- `artifacts/odds_log/model_health_scorecard_daily.parquet`
- `artifacts/odds_log/k_error_decomposition_daily.parquet`
- `artifacts/odds_log/k_error_decomposition.parquet`
- `artifacts/odds_log/gate_next_n_comparison.parquet`

## Core KPI checks

| Metric | Default threshold | Status meaning |
|---|---|---|
| `n_joined` | `>= 100` | If below threshold, diagnostics are still building sample. |
| `mae_err_k_rate` | `<= 0.075` | Higher values indicate k-rate calibration/modeling drift. |
| `abs(under_bias_tbf)` | `<= 1.50` | Larger magnitude indicates under-side workload bias risk. |
| `worst_matchup_tier_mae_err_k_rate` | `<= 0.078` (only if tier n is sufficient) | Flags concentrated matchup-tier failure pockets. |
| `abs(long_rest_bias_tbf)` | `<= 3.00` when `n_long_rest >= 8` | Flags long-rest workload instability. |
| chrono dates for Section 19 | `>= 15` | Below this, do not promote recalibration winner yet. |

## Action policy (if WARN persists)

- `mae_err_k_rate` WARN for 3+ snapshots:
  - Open a recalibration task (raw vs Platt-style vs isotonic).
  - Freeze new feature creation during this cycle.
- `abs(under_bias_tbf)` WARN for 3+ snapshots:
  - Prioritize TBF/workload fixes (especially under-side behavior).
  - Keep or tighten under-side gate controls until bias improves.
- matchup-tier WARN for 3+ snapshots:
  - Run targeted matchup-family diagnostics and ablations.
- `n_dates < 15`:
  - Keep accumulating settled dates; no calibration promotion decision.

## Recalibration Promotion Checklist

Promotion decision should be explicit and repeatable (no ad-hoc pointer flips).

- Use `production/ops/kpi_daily_action.py --json` and require:
  - `recalibration_promote_ready=true`
  - empty `recalibration_promote_blockers`
- Default blockers (policy-driven via `production/ops/kpi_policy.json`):
  - not enough chronological dates,
  - WARN count still elevated,
  - k-rate MAE still above warn threshold,
  - over-side CLV quality not yet stable.
- If blockers remain, continue accumulating + diagnostics; do not repoint production calibration.
- If promotion is ready, run a documented repoint step and record:
  - prior pointer artifact,
  - new pointer artifact,
  - supporting KPI snapshot hashes
  in `docs/research/floor_freeze_log.md`.

## Dynamic gate policy

Quality-gate settings should respond to diagnostics:

- **Healthy state (0-1 WARN):**
  - softer policy, prioritize candidate generation.
- **Caution state (2-3 WARN):**
  - hold under + long-rest risk, require stronger edge in risky tiers.
- **Risk state (4+ WARN):**
  - strict policy, block known-risk slices and increase minimum edge floor.

Current side-policy note (2026-08-15):

- default live operating profile is `D_over18_under12`
  - `edge_min_over=0.18`
  - `edge_min_under=0.12`
- rationale: side asymmetry (over-side instability vs under-side strength) while recalibration promotion blockers remain active.

Use `gate_next_n_comparison.parquet` to monitor whether gating is helping:

- `gate_pnl_delta > 0` over successive windows supports current strictness.
- `gate_pnl_delta <= 0` over multiple windows suggests over-filtering and should
  trigger policy review.

## Threshold maintenance cadence

- Review thresholds weekly (not daily) to avoid overreacting to noise.
- Update thresholds only when both are true:
  - date coverage is adequate for the test in question, and
  - change is supported by repeated snapshots (not a single-day move).

Whenever thresholds are changed, log the reason and supporting snapshot hashes in:

- `docs/research/floor_freeze_log.md`

## Daily execution checklist

1. Run settle: `production/odds/grade_odds_ledger.py --auto-settle-api --void-scratches --status --curve`
2. Refresh notebooks: `production/ops/run_analysis_notebooks.ps1`
3. Read latest scorecard row and note `n_warn`.
4. Apply action policy above (accumulate vs recalibrate vs workload fix).
5. If threshold/policy changed, record it in freeze log.
6. Optional automation:
   - `production/ops/kpi_daily_action.py`
   - `production/ops/run_daily_kpi_loop.py`
   - `production/ops/weekly_kpi_report.py`
   - `production/ops/policy_simulator.py --thresholds "0.08,0.10,0.12,0.14,0.16,0.18"`
  - `production/ops/policy_simulator.py --thresholds "0.08,0.10,0.12,0.14,0.16,0.18,0.20" --side-thresholds "over:0.18,under:0.12"`
   - `production/ops/policy_simulator.py --thresholds "0.08,0.10,0.12,0.14,0.16,0.18" --profile-over-floors "0.12,0.14,0.16,0.18" --profile-under-floors "0.10,0.12,0.14" --profile-min-bets 25`
   - `production/ops/build_daily_operator_summary.py`

## Focused notebook split (faster monitoring loop)

Use these focused notebooks for repeatable, lower-latency monitoring:

- `production/notebooks/results_kpi_monitor.ipynb` (daily KPI/WARN scan)
- `production/notebooks/results_calibration_lab.ipynb` (matchup/rest pockets)
- `production/notebooks/results_gate_policy.ipynb` (edge-floor policy simulation)
- `production/notebooks/results_pnl_clv.ipynb` (bankroll + CLV trend)

Keep `production/notebooks/results_dashboard.ipynb` as the deep-dive archive view.
