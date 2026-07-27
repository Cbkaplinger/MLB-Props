# MLB Props diagrams

Version-controlled architecture and roadmap diagrams for the strikeout-rate
pipeline. Prefer these over ad-hoc chat exports.

Render the Mermaid blocks in GitHub, VS Code / Cursor Mermaid preview, or any
Mermaid-compatible viewer.

## Legend

| Style | Meaning |
|---|---|
| Green / `built` | Implemented on the production research path |
| Amber / `partial` | Partial (ingestion exists; assembly missing) |
| Red / `missing` | Not built or blocked |
| Purple / `risk` | Open methodological risk |
| Blue / `research` | Research-only proposal (not production gate) |

Flow rules:

- Training pipelines read **top → bottom**.
- Live inference is a **side branch** and never feeds Level 3 historical training.
- Dashed edges mean future / not implemented.
- Keep the four phase diagrams separate; do not collapse into one mega-chart.

## Diagrams

| File | Purpose |
|---|---|
| [00-index.md](00-index.md) | Map of the four phases |
| [01-architecture.md](01-architecture.md) | As-built data → model artifact path |
| [02-leakage-and-risks.md](02-leakage-and-risks.md) | Leakage gates, priors, population risks |
| [03-modeling-and-evaluation.md](03-modeling-and-evaluation.md) | Splits, baselines, Step 1/3/4/5 → Step 7 |
| [04-roadmap.md](04-roadmap.md) | Remaining work: TBF, counts, live assembly |

Canonical prose lives in `docs/model-card.md`, `docs/dev-notes.md`, and
`docs/statistical_audit_and_sequencing_report.md`. When a diagram and those
docs disagree, fix both.
