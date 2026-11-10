# NEXT - current action

Owner: architect. Updated 2026-11-10. Chat 3 is closed and its cleanup is
integrated on main; Chat 1 is active on the assigned control-arm parity
task. ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your card.
EXECUTION_BACKLOG remains the single queue.

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

## Current action: control-arm parity EXECUTED - task CLOSED (2026-11-10)

The owner-assigned question is answered. PR #79 (explicit arm selection)
merged; reviewed head `05bab809...`; main `9c8fb63...`. The approved
single control-arm run executed once from wtsc at that HEAD:

- **PASS, EXACT ZERO** - 2,509 starts; 22,581 keyed PA rows; 60,216 PMF
  rows; key-set equality both grains; max abs diff 0.0 in all four
  classes and every K-PMF bucket (tolerance 1e-12). Receipt chain
  `7b239920...` -> status COMPLETED. Evidence (write-once, preserved):
  `...\diagnostics\parity_platoon_candidate_v1_control_arm\`.
- Chat 2 independently VERIFIED (supersedes its NOT VERIFIED interim;
  verdict: PR #79 comment
  https://github.com/Cbkaplinger/MLB-Props/pull/79#issuecomment-6779379426).
  Reviewer-recomputed: code lineage, scope, receipt/artifact
  identities, population arithmetic. Runner-asserted (not
  reviewer-recomputed): the pin gates and the 0.0 maxima.
- Reproducibility/identity evidence only, not predictive superiority.
  No further execution authorized; no next scientific task assigned
  (architect assigns; ablation queue closed).
