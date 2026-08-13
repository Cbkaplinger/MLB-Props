# Production Notebook Map

Use this as the canonical notebook routing map.

## Daily Operator Path (in order)

1. `daily_projections.ipynb`
   - Future slate and today's candidate props.
2. `results_kpi_monitor.ipynb`
   - Daily PASS/WARN health checkpoint.
3. `results_pnl_clv.ipynb`
   - Performance trajectory (PnL, ROI, CLV).
4. `results_bettable_cohort.ipynb`
   - Operating profile comparison (A/B/C) and filtered cohort metrics.
   - Includes all-vs-core exit-anomaly scope comparison.
5. `results_recommendation_audit.ipynb`
   - Full-context weak-point analysis (all recommendations / contexts).

## Targeted Investigation Notebooks

- `results_calibration_lab.ipynb`
  - Where calibration/workload errors concentrate.
  - Includes all-vs-core decomposition comparison.
- `results_gate_policy.ipynb`
  - Threshold and policy simulation details.

## Archive / Reference

- `results_dashboard.ipynb`
  - Deep-dive archive view. Use when focused notebooks indicate an unresolved issue.

## Notes

- Keep threshold sweeps in `results_gate_policy.ipynb`.
- Keep profile-level go/no-go decisions in `results_bettable_cohort.ipynb`.
- Keep daily slate view in `daily_projections.ipynb` concise and execution-focused.
- Use `EXCLUDE_EXIT_ANOMALIES_FOR_PROCESS` in calibration/cohort notebooks to
  switch active scope between all rows and anomaly-filtered core rows.
