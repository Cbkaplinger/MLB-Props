# NEXT - current action

 Owner: architect. Updated 2026-11-09. ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your card. EXECUTION_BACKLOG remains the single queue.

## Workload personalization experiment - COMPLETED / VERIFIED

One authorized run (checkpoint `45ed606`, packet `731f05c`, card `460dd353`) was executed 2026-11-02 and is now **independently VERIFIED by Chat 2** (PR #52 comment `6595706937`; all checks recomputed from the saved artifacts). Verdict: **pooled league BF control (W0) favored over pitcher-specific workload personalization (W1) on development data** - mean count-RPS 1.29525 vs 1.30765; delta = RPS(W1) - RPS(W0) = **+0.012406, CI95 [+0.004410, +0.020368]**, entirely above zero; |delta| exceeds the 0.005 engineering threshold. Registered bf-workload-v1 reconstruction gate passed exactly (max per-start RPS diff 0.0 vs pinned reference `3414d0d2...`, n=2,509, cohort `f77d7a66...`).

BF interpretation (retained, per the architect's correction): negative mean BF error = **underprediction** (W1 -1.03, W0 -0.19); **higher interval coverage is not automatically better** (both arms overcover; W1 covers more yet scores worse); **interval width is not established by coverage alone** - the "wider distribution" claim is retracted; only distribution score, point MAE, and error are established.

Durable artifacts (write-once, preserved, do not modify): `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\workload_personalization_w0v1\` (9 artifacts; hashes in `receipt_final.json`; manifest reconciliation true). No refit, no rerun, no rescue variants.

Limitations: development evidence on the registered 2025H1 cohort - not a fresh final test; no production, betting-value, or causal claims.

## Prior completed milestones (this lane)

- Historical starter-outcome derivation: 9,714 starts (2023-2024); overlap with registered 2024H2 artifact 2,334/2,334, zero discrepancies.
- History-sensitivity scorecard: longer estimation history favored (delta -0.0111, CI below zero); accepted with limitations.
- Ref0-vs-Ref1 multiclass baseline: multinomial K marginal beats population proportions (delta -0.0864, CI below zero); accepted with limitations.
- Stage-A prediction-path reconciliation: implementation reviewed; real-artifact run remains separately authorization-gated.

## Integration - COMPLETE (2026-11-06)

The full verified lane stack is on main at **2ca8aef**: #60 (temporal-robustness lane, VERIFIED run) at `38da8aa`; #64 (result-summary harness slice, renderer PASS) at `290b0fa`; #65 (publication/dashboard/gate-rules consolidation) at `2ca8aef`; preceded by #56 (reconciliation + communication rule), #57 (binary-K closeout), #58 (platoon lane). Bases and destinations verified before each merge; merged by Chat 2 per architect delegation. No carrier duplication, no direct-main pushes.

## Lane results ledger (verified)

- workload w0v1: pooled W0 favored (VERIFIED).
- binary objective: control retained (VERIFIED).
- platoon family: challenger favored in both periods, candidate registered (VERIFIED).
- LGBM bounded-selected vs fixed multinomial: control retained, guard failed, tradeoff recorded (VERIFIED).

Full table: `docs/reference/reports/experiment_impact_ledger_2026-10-22.md`.

## Candidate parity - CLOSED / INDEPENDENTLY VERIFIED (2026-11-09)

The integrated prediction path (main `3a807a98`) reproduced the saved
platoon-candidate forecasts from the same fitted model and pinned inputs:
**PASS, exact zero** at both grains (2,509 starts; 22,581 PA-grain rows;
60,216 PMF rows; max abs diff 0.0 in all four classes and every K-PMF
bucket, tolerance 1e-12). Owner/Chat 2 independently verified and CLOSED
the record. Reference receipt attested as a **present-day verified
snapshot** (`b1b91357...`, four manifest artifacts MATCH) - no historical
byte continuity is claimed. Parity establishes reproducibility/identity
only, NOT predictive superiority. Evidence (write-once, preserved):
`...\diagnostics\parity_platoon_candidate_v1\` (receipt_initial ->
parity_comparison -> receipt_final, chain `b70a2f90...`).

## Baseline recipe for subsequent ablations (recommendation, 2026-11-09)

From the existing VERIFIED records only (no new experiment):

- **PA model:** 4-class multinomial logistic (strikeout /
  walk_hbp_interference / in_play_out / hit; K = class 0),
  StandardScaler + multinomial LR, no tuning. Supported by: binary-K
  lane (binary control retained), LGBM lane (fixed multinomial control
  retained; guard failed), Ref0-vs-Ref1 (K marginal beats population
  proportions).
- **Features (retained control):** the registered 8 prior-only FEAT_H3
  columns. **Unpromoted candidate:** + the 4 platoon columns
  (platoon-features-v1) - favored with CI entirely below zero in the
  platoon run (-0.0008712 [-0.0012622, -0.0005038]) and both temporal
  periods (R1 -0.000415, R2 -0.000870), K guard within margin in all
  three; registered CANDIDATE for a future frozen-contract decision,
  never promoted.
- **History recipe:** cutoff-correct states-v2 (strictly-prior aggregate
  at each cutoff; w150 shrinkage; EW decay 90d half-life); longer
  estimation history favored (history-sensitivity scorecard, delta
  -0.0111, CI below zero).
- **Workload distribution:** pooled league BF37 by date (W0) - favored
  over pitcher-specific W1 (+0.012406, CI [+0.004410, +0.020368],
  entirely above zero); `start_count_pmfs` for K-count PMFs.
- **Aggregation:** per-PA multiclass log loss primary; per-start means
  for contrasts; paired slate-date bootstrap 2000 draws / seed 20261001;
  K-count RPS non-degradation guard (0.002 margin).
- **Calibration status:** NONE - every verified arm is the uncalibrated
  softmax; no calibration comparison exists in any lane.

**Retained control = the registered 8-feature multinomial-plus-W0
recipe** (reconstruction-anchored). **Development control = the
12-feature multinomial-plus-platoon pipeline** (temporal lane). The
platoon family is a candidate, not a promoted component.

**Single most important unresolved question:** whether the 12-feature
multinomial-plus-platoon candidate replaces the 8-feature control as
the frozen baseline for subsequent ablations (the frozen-contract
decision the lanes have twice qualified but never taken). Standing
known-unknown behind it: no calibration comparison exists.

## Current action: owner/architect decision - baseline freeze for subsequent ablations

The baseline-recipe recommendation above is recorded in
`docs/EXECUTION_BACKLOG.md` (parity closure carried there too). Next
action: the owner/architect decides the frozen-contract question (8
vs 12 features; platoon promotion is never automatic). No ablation
work starts until that decision names the baseline.

Report changed evidence, a checkpoint or a concrete blocker. Do not relay unchanged status, create another queue, or ask the owner to arbitrate routine implementation details.