# MLB Props diagrams

Version-controlled architecture and roadmap diagrams for the strikeout-rate
pipeline. Prefer these over ad-hoc chat exports.

> **Live work-state / what to do next:** [`docs/EXECUTION_BACKLOG.md`](../EXECUTION_BACKLOG.md).
> These diagrams are architecture + research-status visuals — not the ops backlog.

Render the Mermaid blocks in GitHub, VS Code / Cursor Mermaid preview, or any
Mermaid-compatible viewer.

## Legend

| Style | Meaning |
|---|---|
| Green / `built` | EXISTING or RESEARCH-BUILT (see file header for which) |
| Amber / `partial` | Partial (shipped but sample/ops still building) |
| Red / `missing` | Not built or blocked |
| Purple / `risk` | Open methodological risk / UNRESOLVED |
| Blue / `research` or `proposed` / `next` | PROPOSED or PENDING-INTEGRATION (dashed edge; not production) |

Flow rules:

- Training pipelines read **top → bottom**.
- Live inference is a **side branch** and never feeds Level 3 historical training.
- Training and pregame inference are separate lanes; forecast cutoff marked per file.
- Solid edges = verified implemented paths; dashed edges = proposals.
- Research never feeds production automatically; REJECTED stays listed, never live.
- Keep the phase diagrams separate; do not collapse into one mega-chart.
  The three coordinated views map onto them (do not create a competing set).

## Diagrams

| File | Purpose | Coordinated view |
|---|---|---|
| [00-index.md](00-index.md) | Map + evidence/lessons table + verified-vs-unresolved | Map for A/B/C |
| [01-architecture.md](01-architecture.md) | As-built data → model artifact path | View A (operational) |
| [02-leakage-and-risks.md](02-leakage-and-risks.md) | Leakage gates, priors, population risks | Constraints for A/B/C |
| [03-modeling-and-evaluation.md](03-modeling-and-evaluation.md) | Splits, baselines, Steps 1–9 → Step 12 consensus freeze, TBF/counts + research chain | View B (built research) |
| [04-roadmap.md](04-roadmap.md) | Paper CLV shipped; focused monitor split + policy simulator; pristine needs roles + View C | View C (proposed) |
| [05-live-prediction-flow.md](05-live-prediction-flow.md) | Daily side branch (crons → board → ledger → grading) | View A companion |

Canonical prose: `docs/reference/model-card.md`, `docs/reference/dev-notes.md`,
`docs/reference/market_clv_gates.md`, `docs/reference/live_assembly_plan.md`,
and `docs/research/statistical_audit_and_sequencing_report.md`. When a diagram
and those docs disagree, fix both. Exit-anomaly governance canonical doc:
`docs/reference/exit_anomaly_protocol.md`. Ops runbook: `production/README.md`.
**Live plan:** `docs/EXECUTION_BACKLOG.md` (wins over any “next” language in diagrams).
