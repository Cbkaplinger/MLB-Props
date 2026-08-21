# Research Docs Map

This folder is evidence-first and intentionally detailed. To reduce navigation
bloat, treat this file as the canonical index instead of repeating long context
inside each finding file.

## Canonical current references

- `step11_discipline_registry_freeze.md` — current production k-rate freeze (184).
- `final58_consensus_freeze_2026-08-20.md` — consensus merged-pool MAE freeze candidate (58) + ablation.
- `feature_selection_handoff_2026-08-20.md` — cycle closeout and pre-tuning validation checklist.
- `experiment_matrix_2026-08-20.md` — canonical run matrix (window, baseline, policy assumptions, outputs).
- `phase11_model_quality_gates.md` — model-quality gate outcomes and rationale.
- `prob_calibration_findings.md` — post-hoc Platt/isotonic calibration evidence.
- `phase_d_population_findings.md` — PA>=9 population and role-label caveats.
- `count_layer_findings.md` — expected_K and line-probability stack behavior.
- `floor_freeze_log.md` — auditable edge/Kelly policy decisions.
- `notebook_change_log.md` — dashboard/monitor change history.
- `../reference/exit_anomaly_protocol.md` — anomaly override/mask/rolling policy operating standard.

## Historical but still useful

- `PAPER_NOTES.md` — chronological research log and bug evidence.
- `step1_*` through `step10_*` findings — closed feature-research progression.
- `statistical_audit_and_sequencing_report.md` — consolidated methods audit.

## Usage guidance

- For day-to-day decisions, start in:
  - `analysis/model_results/model_results_story.ipynb`
  - `production/notebooks/results_kpi_monitor.ipynb`
- Use this folder to verify *why* a decision policy exists, not as a daily
  execution checklist.
- Anomaly model-quality runners live in `scripts/run_walkforward_anomaly_ab.py`
  and `scripts/run_walkforward_anomaly_sensitivity.py`; reports are written under
  `artifacts/projection_log/`.
