# MLB Props diagrams

**Diagram list and status: [00-index.md](00-index.md) — the only index for
this directory.** Canonical work state: `docs/EXECUTION_BACKLOG.md` +
`docs/NEXT.md`; the backlog wins over any "next" language in diagrams.

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

## Reading conventions

- Training pipelines read **top → bottom**.
- Live inference is a **side branch** and never feeds Level 3 historical training.
- Training and pregame inference are separate lanes; forecast cutoff marked per file.
- Solid edges = verified implemented paths; dashed edges = proposals.
- Research never feeds production automatically; REJECTED stays listed, never live.
- Keep the phase diagrams separate; do not collapse into one mega-chart.

## Canonical prose

`docs/reference/model-card.md`, `docs/reference/dev-notes.md`,
`docs/reference/market_clv_gates.md`, `docs/reference/live_assembly_plan.md`,
`docs/reference/exit_anomaly_protocol.md`, and
`docs/research/statistical_audit_and_sequencing_report.md`. When a diagram
and those docs disagree, fix both. Ops runbook: `production/README.md`.
