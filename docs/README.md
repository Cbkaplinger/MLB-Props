# Documentation

Documentation is grouped by folder family:

| Family | Path | Role |
|---|---|---|
| Paper | `docs/paper/` | Modeling manuscript, resume summary, figures, PDF renderers |
| Research | `docs/research/` | Experiment log, step findings, audits, phase gates |
| Reference | `docs/reference/` | Living ops/reference docs (model card, feature notes, lineup, live plan) |
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
| `research/step*_findings.md` / `step*_*.md` | Closed feature-research step write-ups |
| `research/tbf_*.md` / `count_layer_findings.md` | TBF spine and count-layer findings |

## Reference (living)

| Doc | Role |
|---|---|
| `reference/model-card.md` | Intended use, leakage, frozen metrics |
| `reference/dev-notes.md` | Feature / pipeline implementation reference |
| `reference/post_freeze_holdout.md` | Post-lock holdout protocol + latest scores |
| `reference/lineup_train_serve.md` | Historical first-9-by-PA vs live announced lineup |
| `reference/live_assembly_plan.md` | Live slate assembly plan |

Generated research artifacts live under `../artifacts/` (gitignored); see
`../artifacts/README.md` for lifecycle.
