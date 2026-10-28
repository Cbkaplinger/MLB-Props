# Diagrams

> Navigation page only. Each diagram answers a distinct question about the
> system. Canonical work state: `docs/EXECUTION_BACKLOG.md` + `docs/NEXT.md`.

## Architecture

| Diagram | Shows |
|---|---|
| [01 - Architecture](01-architecture.md) | Training + pregame inference pipeline (View A) |
| [02 - Leakage and risks](02-leakage-and-risks.md) | Leakage boundaries and risk classification |
| [03 - Modeling and evaluation](03-modeling-and-evaluation.md) | Model quality, calibration, evaluation gates |
| [05 - Live prediction flow](05-live-prediction-flow.md) | Daily ops: ingestion → model → board → ledger |

## Research and governance (PROPOSED)

| Diagram | Shows |
|---|---|
| [06 - Count-eval harness](06-count-eval-harness-2026-10-16.md) | Count-eval-v2 comparison harness |
| [07 - Lanes and roles](07-lanes-and-roles.md) | Who builds, reviews, authorizes, approves |
| [08 - Research decision flow](08-research-decision-flow.md) | Frozen baseline → challenger → evaluation → promotion/stop |
| [10 - System paths](10-system-paths.md) | Production vs research boundary |
| [11 - Experiment flow](11-experiment-flow.md) | Frozen inputs → paired arms → scoring → decision |
| [12 - Delivery and agent control](12-delivery-and-agent-control.md) | Checkpoint-based delivery (TARGET-STATE) |
| [13 - Experiment evidence lifecycle](13-experiment-evidence-lifecycle.md) | Full lifecycle incl. rejected/invalid/promotion |
| [14 - Research-to-decision boundaries](14-research-to-decision-boundaries.md) | Source data → evaluation/health evidence |

## Model pipeline (PROPOSED, 2026-10-23)

| Diagram | Shows |
|---|---|
| [15 - System map](15-system-map.md) | Layer-by-layer map with file citations |
| [16 - Data lineage](16-data-lineage.md) | Raw sources → lake → tables → odds archive |
| [17 - Model pipeline](17-model-pipeline.md) | Features → ensemble → count layer → policy |
| [18 - Market identity chain](18-market-identity-chain.md) | Historical defect + repaired identity flow |
| [19 - Pipeline stages](19-pipeline-stages.md) | Six stages with market timing documentation |
