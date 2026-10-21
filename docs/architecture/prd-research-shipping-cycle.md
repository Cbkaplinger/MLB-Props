# PRD: next research and shipping cycle

**Status:** PROPOSED (2026-10-21; pending owner approval)
**Goal:** Decide with evidence whether the count layer, workload model or
aggregation should change before the 2027 season.
**Assumed deadline:** season opening late March 2027 (owner to confirm).

## Requirements

- **R1.** Close PR #25 with an accurate publication.
- **R2.** Review the Question A implementation and spec. Then the owner decides
  whether to authorize one real-data evaluation: count-RPS primary, paired
  bootstrap, confirmation untouched.
- **R3.** Pre-register Question B (workload dependence) as a design card. Do
  not implement it until R2 reports.
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
