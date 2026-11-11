# NEXT - current action

Owner: architect. Updated 2026-11-11. Chat 3 closed; cleanup integrated.
Chat 1 active: parity lanes and the paired comparison are CLOSED
(reproduced bit-exactly); the baseline K-PMF diagnostic is implemented
and synthetic-tested; the proposed execution packet awaits an owner
decision. ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your
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
lane stack integrated at `2ca8aef`. Paired comparison reproduced
bit-exactly (checkpoint `7e6d03c`; every artifact byte-identical,
receipt_final = `b1b91357...224ba`); harness-to-market bridge
implemented and merged (PR #81).

## Current action: baseline K-PMF diagnostic built (2026-11-11)

- **Implemented on this branch** (`count_pmf_diagnostic.py`): thin
  keyed glue over the existing registered scorers (count_logscore with
  1e-12 clip - POSITIVE log loss confirmed from code; summed-CDF RPS;
  model_p_over at the eight canonical half-lines; check_pmf; strict
  bucket labels). Exact key equality with both-direction reporting;
  explicit accounting; equal weight per matched start; K >= 23 =
  declared overflow; fixed declared reliability bins [0,.1)...[.9,1];
  per-arm + paired challenger-minus-control deltas.
- **Label source established:** `prepare_assessment_2025H1.py`
  preserves every completed PA of requested starters, so
  `assessment_2025H1_v1.parquet` supplies complete full-start realized
  K (registered derivation: class_label == 0 count).
- **Proposed execution packet in backlog FORWARD** (reproduction
  k-PMF + pinned assessment table; fresh
  `count_pmf_diagnostic_v1` destination). NOT RUN; needs fresh owner
  authorization. confirm_2025H2 stays the reserved (INSPECTED)
  confirmation population.
