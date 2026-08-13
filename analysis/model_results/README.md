# Model Results Analysis

This folder is the streamlined analysis surface for daily model-result review.
It is intentionally smaller and more narrative than
`production/notebooks/results_dashboard.ipynb`.

## Files

- `model_results_story.ipynb`
  - concise, ordered notebook for daily decision-making
  - focuses on model-quality diagnostics and actionable next steps

## Purpose split

- `production/notebooks/results_dashboard.ipynb`
  - full operational dashboard and deep-dive research cells
- `analysis/model_results/model_results_story.ipynb`
  - executive storyline and highest-ROI diagnostics only

## Recommended daily flow

1. Run settle flow so ledger state is current:
   - `production/odds/grade_odds_ledger.py --auto-settle-api --void-scratches --status --curve`
2. Refresh analysis notebooks:
   - `powershell -ExecutionPolicy Bypass -File production/ops/run_analysis_notebooks.ps1`
3. Read `model_results_story.ipynb` scorecard section first, then review flagged slices.
4. Open focused ops monitors for faster triage when needed:
   - `production/notebooks/results_kpi_monitor.ipynb`
   - `production/notebooks/results_calibration_lab.ipynb`
   - `production/notebooks/results_gate_policy.ipynb`
   - `production/notebooks/results_pnl_clv.ipynb`
5. Promote chrono recalibration winner only after `>=15` distinct settled dates.
6. Use daily action helper for next-step focus:
   - `production/ops/kpi_daily_action.py`
