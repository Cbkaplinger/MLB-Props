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

- Workload w0v1: pooled W0 favored over W1 (VERIFIED; delta +0.012406, CI [+0.004410, +0.020368]); BF interpretation correction retained (see ledger); artifacts `...\workload_personalization_w0v1\`.
- Historical starter-outcome derivation: 9,714 starts (2023-2024); 2,334/2,334 overlap with the registered 2024H2 artifact.
- History-sensitivity scorecard: longer history favored (delta -0.0111, CI below zero).
- Ref0-vs-Ref1: multinomial K marginal beats population proportions (delta -0.0864, CI below zero).
- Stage-A reconciliation: implementation reviewed; real-artifact run remains authorization-gated.
- Binary-K lane: control retained in its declared comparison (VERIFIED). LGBM lane: control retained, guard failed (VERIFIED). Platoon lane: challenger favored, candidate registered (VERIFIED).
- Lane stack integrated on main at 2ca8aef (#56-#60, #64, #65); details in `docs/EXECUTION_BACKLOG.md`.

## Current action: paired comparison - existing CLI sufficient (2026-11-10)

Owner-assigned question: smallest reusable entry point to evaluate the
registered control vs challenger through the shared harness.

- Decision: **no code change, no new PR.** The registered
  `platoon_comparison.py` CLI (`platoon_information_v1`) already
  performs the exact paired comparison (both registered arms, same
  rows, eligible 2025H1 cohort `f77d7a66...`, pooled W0, per-PA
  multiclass log loss primary, K-count RPS guard, paired bootstrap
  2000/20261001, reconstruction gate, write-once receipts). Harness
  equivalence is proven evidence (both parity runs, exact zero).
- The registered result already exists and is CLOSED (challenger
  favored: per-PA delta -0.0008712, CI below zero; K guard satisfied).
  Exact invocation + packet: committed
  `execution_packet_platoon_v1.md`; snapshot PRESENT carries it.
- **REPRODUCTION EXECUTED ONCE 2026-11-10 (owner-authorized,
  checkpoint `7e6d03c`, fresh destination
  `platoon_information_v1_reproduction_20261110`): BIT-EXACT -
  exit 0, delta -0.0008712364... CI95 [-0.0012622, -0.0005038], K
  guard within margin, and every output artifact byte-identical to
  the registered run (receipt_final = `b1b91357...224ba`).** The
  registered comparison result stands reproduced; no further
  comparison execution needed.
- **Weighting labels (corrected):** the reported per-PA means (control
  1.2245976, platoon 1.2238507) are UNWEIGHTED averages over the 43,565
  matched PAs; the primary contrast and its CI use EQUAL-WEIGHT
  PER-START means (challenger 1.2285053, control 1.2293765) with the
  per-start paired bootstrap (2000/20261001); the K-count RPS guard
  uses the same per-start equal weighting.
- **Hash label corrected (Chat 2 finding):** `c7428375...` is the
  reproduction's per-start OUTPUT hash (byte-identical to the
  registered run's own output record); the pinned reconstruction
  REFERENCE hash is `ae971758...` (workload_personalization_w0v1).
- **Next gap (identified):** the seam between the harness's keyed
  24-bucket K-count PMFs and the production count layer's
  line-probability output contract (`p_over_{line}` on
  `PROJECTION_K_LINES`) - see backlog FORWARD for the one concrete
  task. Input capture (pregame_lineup_capture), checkpoint
  pin-loading, and both sides' tests already exist.
- Both parity lanes CLOSED/VERIFIED; confirm_2025H2 remains the
  reserved (INSPECTED) confirmation population; no next scientific
  task assigned until the owner decides the next question.
