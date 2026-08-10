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
| `reference/post_freeze_holdout.md` | Post-lock holdout protocol + latest scores |
| `reference/lineup_train_serve.md` | Historical first-9-by-PA vs live announced lineup |
| `reference/live_assembly_plan.md` | Live slate assembly → log / odds / CLV |
| `reference/research_assistant_instructions.md` | Agent operating instructions for this repo |

Ops runbook: `../production/README.md`.

Generated research + paper-trading artifacts live under `../artifacts/`
(gitignored): `projection_log/`, `odds_log/`, models, fold CSVs.
