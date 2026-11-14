# NEXT - current state

Owner: architect. Updated 2026-11-13. Packet A closed/verified; Packet B
executed + Chat 2 VERIFIED. All single-run permissions consumed.
ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your card.
EXECUTION_BACKLOG remains the single queue. Full records: backlog +
experiment_impact_ledger_2026-10-22.md.

## Current state: Packet A + B verified (single-run permissions consumed)

- Packet A (paid-morning 2025H1 market-only baseline): EXECUTED, exit 0
  (main aa61986; receipt PR #90 comment 6861125006). 19,800 candidates;
  entry-eligible 5,441/19,797; valid close 4,934/5,441; mean movement
  -0.0869 pp; flat-1u entry ROI over -0.0452 / under -0.0782 units per
  unit (the 4,934 close-benchmarked contracts, NOT all 5,441
  entry-eligible). No model-edge claim.
- Packet B (control vs near-close books/LTBO; NEAR-CLOSE tier A/B
  timing, NOT Packet A's T-5h/T-5min gates): EXECUTED under the
  shared-population policy (main c3c0feb; receipt PR #92 comment
  6866892070) and Chat 2 VERIFIED (6866986855). RESULT on the
  2,154-start shared population (2,154 matched + 355 unmatched, ALL
  no_near_close_quotes = 2,509 cohort): control log loss 0.715358 vs
  consensus 0.688572, paired delta +0.026786, CI95 [+0.01727,
  +0.03672], Holm p 0.0005, model_not_better_than_close; Brier 0.25887
  vs 0.24772; Count-RPS 1.28006. Book-vs-LTBO paired deltas small in
  this sample (max |d| ~0.0012; denominators 453-2,178) - descriptive
  only, no formal equal-accuracy claim. Artifacts preserved in
  control_vs_books_v2.
- EXPLICIT GAPS: NO model-vs-individual-book comparison exists (books
  scored only vs LTBO). Morning (T-5h) model-input availability
  UNESTABLISHED. Strategy validation/betting thresholds unresolved.
  Consensus-coverage selection caveat: the paired delta describes the
  covered subset only.

## Current action: Packet C CLOSED/VERIFIED; ONE experiment proposal awaits owner decision (2026-11-13)

- Packet C EXECUTED once (exit 0; main 0909ed40; handoff PR #93
  comment 6872744340) and CLOSED. Descriptive finding (SUPPORTED, no
  loss decomposition): directional disagreement mean -0.0084 (-0.84
  pp); mean(p-y) model -0.0139 vs consensus -0.0055; extremity 0.0902
  vs 0.0488 (delta +0.0414; |p-0.5| >= 0.25 on 2.88% vs 0.00%). In
  the MODEL's own outer deciles the observed over rates (0.440
  bottom / 0.500 top) diverge from the model's bin means (0.307 /
  0.708; mean(p-y) -0.132 / +0.208) while the consensus tracks
  observed rates closely in the SAME bins. An earlier PR #93 comment
  described the deficit as concentrated in outer deciles - that
  wording is superseded here (no decomposition claim).
- ONE MODEL-ONLY EXPERIMENT PROPOSED (awaiting owner decision; full
  spec in the packet section "MODEL-ONLY EXPERIMENT PROPOSAL
  (2026-11-13)"): the registered pooled-prior STRENGTH (W0/BF37
  weight in start_count_pmfs) as the single changed component -
  hypothesis: the control's unsupported extremity reflects
  insufficient shrinkage toward the pooled mean; a stronger declared
  prior weight should reduce extremity and close part of the +0.0268
  paired log-loss deficit WITHOUT market information. Causal
  attribution NOT established - the experiment tests it. Awaiting
  owner decision before implementation.
- Packet C runner identity: run_packet_c_diagnostic.py (ack
  EXECUTE-PACKET-C-DIAGNOSTIC-V1; executed once, artifacts in
  control_vs_books_v2_bias_diagnostic).

## Delivery-boundary inventory (2026-11-13, pre-#93 observations)

- Worktrees: MLB-Props (research/control-arm-parity @05bab80, clean,
  3 untracked owner-local experiment files preserved), review-68
  (detached pin c1d770e, clean), wtsc (main, clean). All 7 lane tips +
  research/control-arm-parity REACHABLE from origin/main (c3c0feb);
  open PRs: none. Nothing deleted; deletion/reset needs separate
  scoped approval. Historical lanes (PRs #84/#86/#87/#89/#90/#92) all
  merged and recorded in the backlog's dated snapshots.

## Superseded/historical (evidence preserved)
