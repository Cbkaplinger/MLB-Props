# NEXT - current action

Owner: architect. Updated 2026-11-10. Temporary cleanup owner: Chat 3 while
Chats 1 and 2 are paused. ROLES_REV 2026-10-28-r1. Read
docs/roles/README.md and your card. EXECUTION_BACKLOG remains the single
queue.

## Ablation baseline decision (owner, 2026-11-09)

- **Reference control:** registered 8-feature multinomial + pooled W0.
- **Development challenger:** registered 12-feature platoon recipe (platoon-features-v1).
- **No production promotion and no fresh-validation claim;** promotion never automatic.
- Scope limits: the binary-K and LGBM lanes retained the control within their declared comparisons - not universal proof of multinomial superiority; Ref0-vs-Ref1 favored the K marginal over population proportions.
- **K-count aggregation vs evaluation metrics (separate layers):** `adapter.start_count_pmfs` builds per-start K-count PMFs from per-PA probabilities + pooled BF37 (construction, not a metric); evaluation = per-PA multiclass log loss primary, per-start means, paired slate-date bootstrap 2000/20261001, K-count RPS guard (0.002).
- Calibration: none in every verified arm (uncalibrated softmax; no calibration comparison exists).
- Full recipe, workload/history detail, and the control/challenger distinction: `docs/EXECUTION_BACKLOG.md` (ablation-baseline-decision block, 2026-11-09). Verified lane results: `docs/reference/reports/experiment_impact_ledger_2026-10-22.md`.

## Candidate parity - CLOSED / INDEPENDENTLY VERIFIED (2026-11-09)

PASS, exact zero at both grains (2,509 starts; 22,581 PA rows; 60,216 PMF rows; tolerance 1e-12). Reference receipt = a present-day verified snapshot (`b1b91357...`); no historical byte continuity claimed. Reproducibility/identity only, NOT predictive superiority. Evidence (write-once, preserved): `...\diagnostics\parity_platoon_candidate_v1\` (chain `b70a2f90...`). Full record: `docs/EXECUTION_BACKLOG.md` (executed-parity block, 2026-11-09).

## Prior completed milestones (this lane)

- Workload w0v1: pooled W0 favored over W1 (VERIFIED; delta +0.012406, CI [+0.004410, +0.020368]); BF interpretation correction retained (see ledger); artifacts `...\workload_personalization_w0v1\`.
- Historical starter-outcome derivation: 9,714 starts (2023-2024); 2,334/2,334 overlap with the registered 2024H2 artifact.
- History-sensitivity scorecard: longer history favored (delta -0.0111, CI below zero).
- Ref0-vs-Ref1: multinomial K marginal beats population proportions (delta -0.0864, CI below zero).
- Stage-A reconciliation: implementation reviewed; real-artifact run remains authorization-gated.
- Binary-K lane: control retained in its declared comparison (VERIFIED). LGBM lane: control retained, guard failed (VERIFIED). Platoon lane: challenger favored, candidate registered (VERIFIED).
- Lane stack integrated on main at 2ca8aef (#56-#60, #64, #65); details in `docs/EXECUTION_BACKLOG.md`.

## Current action: repository consolidation closeout

Chat 3 is the sole active maintenance owner. The verified integration
reference is `origin/main` at
`731a32e56a494e778ea0e45d51ea18f3362ac975`; no scientific execution,
promotion, model change, or review reopening is authorized by this entry.

- Primary `main` was fast-forwarded to that SHA without reset, stash, clean,
  or deletion. Its three untracked experiment files and ignored storage
  remain in place; a path collision check against `origin/main` found zero
  collisions.
- `wtsc` is the protected Chat 1 builder workspace at
  `research/dual-arm-prediction@165b7a9`. It has one uncommitted
  `docs/EXECUTION_BACKLOG.md` edit. That edit contains stale pause/open-PR
  statements, is preserved at
  `C:\Users\ckaplinger\Downloads\MLB-Props-preservation-20261109\patches\wtsc-backlog-uncommitted.patch`,
  and is not current authority.
- `review-68` is the protected Chat 2 reviewer workspace, detached at
  `165b7a9`. Do not use it for cleanup.
- `distribution-spec`, `main-active`, and `paext-v2` remain named
  preservation holds because their dirty, unique, ignored, or MLflow state
  has not been authorized for deletion or merge.

The next action is one owner-approved branch/worktree removal batch recorded
in `docs/EXECUTION_BACKLOG.md`. Until that approval arrives, preserve all
holds and do not create another inventory, archive, worktree, or framework.

## Scientific queue hold

The completed candidate-parity evidence above remains historical evidence.
Any future scientific task resumes only after the architect assigns one
question and Chat 1/Chat 2 receive a fresh restart handoff from
`origin/main`; this closeout does not reopen a review or authorize execution.

Report changed evidence, a checkpoint or a concrete blocker. Do not relay unchanged status, create another queue, or ask the owner to arbitrate routine implementation details.
