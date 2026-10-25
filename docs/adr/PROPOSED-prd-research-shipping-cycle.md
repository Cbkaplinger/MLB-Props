# PRD: next research and shipping cycle

**Status:** PROPOSED (2026-10-21; pending owner approval)
**Goal:** Decide with evidence whether the count layer, workload model or
aggregation should change before the 2027 season.
**Assumed deadline:** season opening late March 2027 (owner to confirm).

## Requirements

- **R1. DONE 2026-10-21: PR #25 merged at `71a1c5c` (one dated status note for this PRD below; mutable research state is not copied into the other architecture files - their PROPOSED status labels are the only live markers).**
- **R2.** Review the Question A implementation and spec. Then the owner decides
  whether to authorize one real-data evaluation: count-RPS primary, paired
  bootstrap, confirmation untouched.
- **R3.** Pre-register Question B (workload dependence) as a design card with the two named subjects C-B1 (exposure-index heterogeneity with the supplied BF distribution) and C-B2 (endogenous exit/workload coupling) - see ADR-0002. Do not implement it until R2 reports.
- **R4.** Define the abstain-versus-handle policy for newcomers (owner
  decision; 57 debut-date newcomers plus Enns 608650 / Hart 606996).
- **R5.** Finish the cleanup sweep and reconcile the docs and diagrams.
- **R6.** Promotion path: calibration, policy replay and a paper-trading
  window. Nothing is promoted without an owner gate.

## Non-goals

Retuning the rejected R60/m30 recipe, touching the confirmation block, or any
production change this cycle.

## Success criteria

Each question has a closed verdict with valid provenance. Any promoted change
beats the frozen baseline on the pre-registered metric and survives replay.

## Risks

Provenance defects; scope creep (the Question A work is already inside
PR #25); a small expected gain from Question A.


## Status note (one dated note for this PRD; 2026-10-21)

- PR #25 (batter-history diagnostic closed REJECTED; Question A exact
  Poisson-binomial aggregator built with synthetic tests; publication fix
  included) MERGED at `71a1c5c`. Question A evaluation on real outcomes
  remains UNAUTHORIZED and unrun (owner gate, R2). Abstain-vs-handle (R4)
  remains the open owner decision.
