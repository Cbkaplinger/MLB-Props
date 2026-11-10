# NEXT - current action

Owner: architect. Updated 2026-11-10. Chat 3 closed; cleanup integrated.
Chat 1 active: both parity lanes and the registered paired comparison are
CLOSED/reproduced; current deliverable is the harness-to-market seam
analysis. ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your
card. EXECUTION_BACKLOG remains the single queue.

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

All VERIFIED; full records in `docs/EXECUTION_BACKLOG.md` and
`docs/reference/reports/experiment_impact_ledger_2026-10-22.md`:
workload w0v1 (pooled W0 favored), historical starter-outcome derivation
(9,714 starts), history-sensitivity scorecard, Ref0-vs-Ref1, Stage-A
reconciliation (implemented; real run authorization-gated), binary-K /
LGBM / platoon lanes (control retained / retained / challenger favored),
lane stack integrated at `2ca8aef`.

## Current action: paired comparison CLOSED - seam task proposed (2026-11-10)

- Decision (no code change, no new PR): the registered
  `platoon_comparison.py` CLI already performs the exact paired
  comparison; harness equivalence proven by both parity runs (exact
  zero). Packet: `execution_packet_platoon_v1.md`.
- **REPRODUCTION EXECUTED ONCE (owner-authorized, checkpoint
  `7e6d03c`, fresh write-once destination
  `platoon_information_v1_reproduction_20261110`): BIT-EXACT** - exit
  0, delta -0.0008712364... CI95 [-0.0012622, -0.0005038], K guard
  within margin, every output artifact byte-identical (receipt_final
  = `b1b91357...224ba`). No further comparison execution needed.
- Corrections (Chat 2): `c7428375...` = the reproduction's per-start
  OUTPUT hash (registered output record byte-identical); the pinned
  reconstruction REFERENCE hash is `ae971758...`. Weighting: per-PA
  means are unweighted over 43,565 matched PAs; the primary contrast
  + CI use equal-weight per-start means (challenger 1.2285053,
  control 1.2293765) with the per-start paired bootstrap; the K RPS
  guard uses the same per-start weighting.
- **Next gap:** the harness's keyed 24-bucket K-count PMFs are not
  bridged to the production line-probability contract
  (`p_over_{line}` on `PROJECTION_K_LINES`). One concrete task is in
  backlog FORWARD (research-side bridge + synthetic integration test;
  zero live-path change). Input capture, checkpoint pin-loading, and
  both sides' tests already exist.
- confirm_2025H2 remains the reserved (INSPECTED) confirmation
  population; no next scientific task assigned until the owner picks.
