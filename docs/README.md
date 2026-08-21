# Documentation

Documentation is grouped by folder family:

| Family | Path | Role |
|---|---|---|
| Paper | `docs/paper/` | Modeling manuscript, resume summary, figures, PDF renderers |
| Research | `docs/research/` | Experiment log, step findings, audits, phase gates |
| Reference | `docs/reference/` | Living ops/reference docs (model card, market/CLV, lineup, live plan) |
| Diagrams | `docs/diagrams/` | Phase-colored Mermaid architecture / leakage / modeling / roadmap |
| Archive | `docs/archive/` | Superseded process evidence (not current metrics) |

Meta:

| Doc | Role |
|---|---|
| `README.md` | This index |
| `CLEANUP_LOG.md` | Repository cleanup history |

## Research findings (closed steps)

| Doc | Role |
|---|---|
| `research/PAPER_NOTES.md` | Experiment log and sequencing decisions |
| `research/README.md` | Canonical research-doc index and dedup navigation |
| `research/statistical_audit_and_sequencing_report.md` | Formal audit / sequencing |
| `research/phase11_model_quality_gates.md` | Tune / walk-forward / calibration gates |
| `research/prob_calibration_findings.md` | Post-hoc Platt/isotonic on `p_over_*` (chrono CV) |
| `research/step*_findings.md` / `step*_*.md` | Closed feature-research step write-ups |
| `research/step11_discipline_registry_freeze.md` | **Current** LightGBM production freeze (184) |
| `research/step10_p1_registry_freeze.md` | Prior 180-feature freeze (`step10_180`) |
| `research/tbf_*.md` / `count_layer_findings.md` | TBF spine and count-layer findings |
| `research/floor_freeze_log.md` | Auditable record of every edge-floor / Kelly-fraction decision (canonical cell-hashes + stopping rules) |
| `research/notebook_change_log.md` | Per-batch log of `production/notebooks/results_dashboard.ipynb` additions |

## Reference (living)

| Doc | Role |
|---|---|
| `reference/model-card.md` | Intended use, leakage, frozen metrics |
| `reference/dev-notes.md` | Feature / pipeline implementation reference (incl. `skill_stats.py`) |
| `reference/market_clv_gates.md` | Paper-trading protocol (edge floor, CLV, dashboard §11-18, daily loop) |
| `reference/daily_kpi_protocol.md` | Daily KPI thresholds, WARN actions, and dynamic gate policy |
| `reference/repo_waste_sweep_checklist.md` | Cleanup checklist for low-value surface area |
| `reference/repo_canonical_map.md` | Canonical daily surfaces vs deep-dive/archive surfaces |
| `reference/repo_hold_inventory_2026-08-18.md` | Hold ledger for unresolved cleanup/reorg candidates |
| `reference/repo_quality_passthrough_report_2026-08-18.md` | Latest keep/hold/delete passthrough report |
| `reference/repo_quality_passthrough_report_2026-08-21.md` | Latest repository-wide documentation and hygiene sweep |
| `reference/post_freeze_holdout.md` | Post-lock holdout protocol + latest scores |
| `reference/lineup_train_serve.md` | Historical first-9-by-PA vs live announced lineup |
| `reference/live_assembly_plan.md` | Live slate assembly → log / odds / CLV |
| `reference/research_assistant_instructions.md` | Agent operating instructions for this repo |
| `reference/exit_anomaly_protocol.md` | Exit-anomaly tagging, mask build, rolling policy, and report workflow |

Ops runbook: `../production/README.md`.
Canonical command routing: `../production/INDEX.md` and `../production/RUNBOOK.md`.

Current production scorer posture:

- k-rate path: live ensemble config at `production/ops/live_krate_ensemble.json`
- policy mode: conservative routing documented in `production/README.md`
- model governance artifacts: `artifacts/odds_log/ensemble_sweep_*` and
  `artifacts/odds_log/open_top3_transfer_*`

Generated research + paper-trading artifacts live under `../artifacts/`
(gitignored): `projection_log/`, `odds_log/`, models, fold CSVs.

Anomaly model-quality artifacts:

- `artifacts/projection_log/exit_anomaly_impact_report.json`
- `artifacts/projection_log/rolling_anomaly_policy_impact.json`
- `artifacts/model_quality/anomaly_policy_ab/`
- `artifacts/model_quality/anomaly_policy_sensitivity/`
