# NEXT - current action

Owner: architect. Updated 2026-10-31. ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your card. EXECUTION_BACKLOG remains the single queue.

## Scientific milestone

~~Complete prediction-path verification and produce a valid historical baseline benchmark~~ — **COMPLETED**: the Ref0-vs-Ref1 multiclass baseline comparison was executed, independently verified, and accepted with limitations.

## Current next task

**Workload personalization experiment** (W0 pooled league BF vs W1 pitcher-specific BF-workload-v1). The experiment card is at `docs/adr/PROPOSED-workload-personalization-experiment.md` (revised at `460dd353`). Implementation requires one authorized run with the shared PA model inference, prediction serialization, and both BF variant vectors. No execution authorization yet.

## Prior completed milestones in this lane

- **Historical starter-outcome derivation**: 9,714 starts derived from the expanded 2023–2024 PA source; overlap with the registered 2024H2 artifact confirmed (2,334/2,334 keys, zero discrepancies).
- **History-sensitivity scorecard**: the learned simple-pitcher reference beats the 2024H2-only population-rate control (Δ −0.0111 count-RPS, CI entirely below zero); accepted with limitations.
- **Ref0-vs-Ref1 multiclass baseline**: the regularized multinomial model's K marginal produces significantly better count forecasts than population proportions (Δ −0.0864 count-RPS, CI entirely below zero); accepted with limitations by Chat 2.
- **Stage-A prediction-path reconciliation**: implementation reviewed, real-artifact execution still authorization-gated.

## Completion and next phase

After the workload result: isolate one PA improvement → freeze selected features → bounded time-ordered tuning → locked evaluation → optional calibration → separately authorized confirmation/operations. Protected partitions and old registrations remain unchanged.

Report changed evidence, a checkpoint or a concrete blocker. Do not relay unchanged status, create another queue, or ask the owner to arbitrate routine implementation details.
