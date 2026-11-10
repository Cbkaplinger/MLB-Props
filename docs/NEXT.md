# NEXT - current action

Owner: architect. Updated 2026-11-10 for the post-closeout handoff after this
docs checkpoint integrates. Chat 3 then closes; Chats 1 and 2 may resume.
ROLES_REV 2026-10-28-r1. Read
docs/roles/README.md and your card. EXECUTION_BACKLOG remains the single
queue.

## Ablation baseline decision (owner, 2026-11-09)

- Control: registered 8-feature multinomial plus pooled W0.
- Challenger: registered 12-feature platoon recipe; no production promotion
  or fresh-validation claim.
- Evaluation uses per-PA multiclass log loss, per-start means, paired
  slate-date bootstrap, and the K-count RPS guard; calibration remains absent.
- Full recipe and verified results: `docs/EXECUTION_BACKLOG.md` and
  `docs/reference/reports/experiment_impact_ledger_2026-10-22.md`.

## Candidate parity - CLOSED / INDEPENDENTLY VERIFIED (2026-11-09)

PASS at both grains (2,509 starts; 22,581 PA rows; 60,216 PMF rows;
tolerance 1e-12). This is reproducibility/identity evidence, not predictive
superiority. The write-once receipt and full record are preserved in
`docs/EXECUTION_BACKLOG.md`.

## Prior completed milestones (this lane)

- Workload w0v1: pooled W0 favored over W1 (VERIFIED; delta +0.012406, CI [+0.004410, +0.020368]); BF interpretation correction retained (see ledger); artifacts `...\workload_personalization_w0v1\`.
- Historical starter-outcome derivation: 9,714 starts (2023-2024); 2,334/2,334 overlap with the registered 2024H2 artifact.
- History-sensitivity scorecard: longer history favored (delta -0.0111, CI below zero).
- Ref0-vs-Ref1: multinomial K marginal beats population proportions (delta -0.0864, CI below zero).
- Stage-A reconciliation: implementation reviewed; real-artifact run remains authorization-gated.
- Binary-K lane: control retained in its declared comparison (VERIFIED). LGBM lane: control retained, guard failed (VERIFIED). Platoon lane: challenger favored, candidate registered (VERIFIED).
- Lane stack integrated on main at 2ca8aef (#56-#60, #64, #65); details in `docs/EXECUTION_BACKLOG.md`.

## Current action: restart from canonical main

The consolidation is complete. `origin/main` and the primary checkout are
at `57ce8b2f67130329bc894de2b8bfa50e5e1b83f4`, including the reviewed
test-signal cleanup in PR #77. No scientific execution, promotion, model
change, or review reopening is authorized by this entry.

- The normal footprint is three worktrees: primary `main`, Chat 1's `wtsc`,
  and detached Chat 2 reviewer workspace `review-68`.
- The only active branch refs are `main` and
  `research/dual-arm-prediction`; no maintenance branch remains.
- Primary's three unregistered experiment files remain preserved and
  untouched. Historical ignored storage remains outside the active workspace
  set at the preservation location recorded in `EXECUTION_BACKLOG.md`.
- Chat 1 should fast-forward `wtsc` from fetched `origin/main` before a new
  task. Chat 2 should review only the exact published builder SHA.
- No new cleanup lane, queue, or worktree is authorized by this entry.

## Scientific queue hold

The completed candidate-parity evidence above remains historical evidence.
Any future scientific task resumes only after the architect assigns one
question; this closeout does not reopen a review or authorize execution.

Report changed evidence, a checkpoint or a concrete blocker. Do not relay unchanged status, create another queue, or ask the owner to arbitrate routine implementation details.
