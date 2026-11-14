# NEXT - current state

Owner: architect. Updated 2026-11-13. Packet A closed/verified; Packet B
executed + Chat 2 VERIFIED. All single-run permissions consumed.
ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your card.
EXECUTION_BACKLOG remains the single queue. Full records: backlog +
experiment_impact_ledger_2026-10-22.md.

## Current state: Packet B VERIFIED; awaiting one bounded scientific assignment

- Packet A (paid-morning 2025H1 market-only baseline): EXECUTED, exit 0
  (main aa61986; receipt PR #90 comment 6861125006; artifact index
  6861289910). 19,800 candidates; entry-eligible 5,441/19,797; valid
  close 4,934/5,441; mean movement -0.0869 pp; flat-1u entry ROI over
  -0.0452 / under -0.0782 units per unit (the 4,934 close-benchmarked
  contracts, NOT all 5,441 entry-eligible). No model-edge claim.
- Packet B (current-control vs near-close books/LTBO; registered
  NEAR-CLOSE tier A/B timing - NOT Packet A's T-5h/T-5min gates):
  EXECUTED under the shared-population policy (main c3c0feb; receipt
  PR #92 comment 6866892070) and Chat 2 VERIFIED (6866986855; scores
  recomputed from preserved artifacts to <1e-9). RESULT on the
  2,154-start shared population (2,154 matched + 355 unmatched, ALL
  no_near_close_quotes = 2,509 cohort): control log loss 0.715358 vs
  consensus 0.688572, paired delta +0.026786, CI95 [+0.01727,
  +0.03672], Holm p 0.0005, decision model_not_better_than_close;
  Brier 0.25887 vs 0.24772; Count-RPS 1.28006. Book-vs-LTBO per-book
  paired deltas small in this sample (max |d| ~0.0012 log loss;
  denominators 453-2,178) - a DESCRIPTIVE observation only; no formal
  equal-accuracy claim is made. Artifacts preserved in
  control_vs_books_v2 (sha256 recorded in the receipt).
- EXPLICIT GAPS: NO model-vs-individual-book comparison exists (books
  scored only vs LTBO; a per-book direct comparison would be a
  separate declared comparison). Morning (T-5h) model-input
  availability UNESTABLISHED. Strategy validation/betting thresholds
  unresolved. Consensus-coverage selection caveat: the paired delta
  describes the covered subset only.
- All single-run permissions consumed (Packet A + both Packet B
  attempts). Awaiting ONE bounded scientific assignment before any
  implementation.

## Prepared next packet (pre-registered; NOT executed)

- CONTROL BIAS/EXTREMITY DIAGNOSTIC on the existing 2,154 matched
  starts - see the PACKET C section of
  docs/reference/reports/control_vs_books_evaluation_packet_2026-11-12.md
  (fixed summary definitions, saved-input hashes, fresh write-once
  destination, stop conditions). Awaits a new owner order.

## Delivery-boundary inventory (2026-11-13, pre-#93 observations)

- Worktrees: MLB-Props (research/control-arm-parity @05bab80, clean,
  3 untracked owner-local experiment files preserved), review-68
  (detached pin c1d770e, clean), wtsc (main, clean). All 7 lane tips +
  research/control-arm-parity REACHABLE from origin/main (c3c0feb) -
  fully integrated; open PRs: none. Nothing deleted; deletion/reset
  requires separate scoped approval.

## Superseded/historical (evidence preserved)

Identity-exclusion (PR #87), market-only T-5h replay (PR #86),
market-benchmark seam (PR #84), quote-integrity +
normalize_idempotent (PR #89), close-conflict drop-and-count
(PR #90), consensus shared-population policy (PR #92): all merged and
recorded in the backlog's dated snapshots. Older lane results (w0v1,
binary-K, LGBM, platoon; paired comparison reproduced bit-exactly
b1b91357...224ba) remain VERIFIED historical records.
