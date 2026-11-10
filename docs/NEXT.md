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

## Current action: control-arm parity selection (PR #79)

Owner-assigned question: can the shared prediction harness reproduce
the saved reference-control forecasts (registered 8-feature multinomial
+ pooled W0) as it already reproduced the saved challenger forecasts?

- The harness (`label_free_prediction.run_prediction`) already supports
  both registered contracts; the saved reference dir carries both arms'
  forecasts. Only `parity_platoon_candidate_v1.py` was
  challenger-hard-wired; it now takes an explicit `--arm` selection
  (`platoon_challenger` default, `multinomial_control`, unsupported
  selection refuses pre-write) with unchanged challenger semantics.
- Synthetic only (17 parity tests + seam suites green). No real-data
  execution; control-arm execution still needs fresh owner
  authorization. No promotion implied.
- Checkpoint: PR #79 from `research/control-arm-parity`; main
  `f2ed15c` integrated; review pending on the superseding published
  head SHA.
- Footprint stays three worktrees (primary, `wtsc`, detached
  `review-68`); Chat 3 remains closed; primary's three unregistered
  owner-local experiment files remain preserved and untouched; no new
  cleanup lane, queue, or worktree is authorized by this entry.
