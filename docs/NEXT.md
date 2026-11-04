# NEXT - current action

Owner: architect. Updated 2026-11-03. ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your card. EXECUTION_BACKLOG remains the single queue.

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

## Integration - COMPLETE (2026-11-04)

The full verified lane stack is on main at **b32fd0c** (merge of PR #59): #57 (binary-K lane closeout), #58 (platoon lane: repaired checkpoint, verified run, closeout), #59 (LGBM lane: repaired fold calendar, verified attempt 2, closeout) - plus #56 (reconciliation + communication rule) merged earlier. Bases and destinations were verified before each parent merge; children were retargeted/merged per the recorded procedure by Chat 2/architect. No carrier duplication, no direct-main pushes. Both verified experiment records are closed; artifacts preserved.

## Next milestone: temporal-robustness evaluation of the retained candidate - SPECIFIED, awaiting review

temporal_robustness_v1 (card: docs/adr/PROPOSED-temporal-robustness-evaluation.md):

- **Retained candidate manifest:** 12-feature multinomial-plus-platoon pipeline (8 FEAT_H3 + 4 platoon-features-v1; StandardScaler + LogisticRegression C=1.0 lbfgs, identical softmax; equal per-PA training weights); states-v2 cutoff rules + bridge labels; W0 pooled BF37; projected-lineups-only assumptions with the modal-stand switch rule; registered 24-bucket aggregation; verified artifacts (platoon run + LGBM attempt-2 control); full code-identity table.
- **Temporal evaluation spec:** R1 = fit 2023-03-30..2024-06-30 (277 verified date clusters) -> score 2024-07-01..09-30 (88; EXPOSED); R2 = fit ..2024-12-31 (365) -> score 2025-01-01..06-30 (98; EXPOSED); R3 = fit ..2025-06-30 (463) -> score 2025-07-01..09-28 (86; UNEXPOSED confirm partition - REQUIRES a specific new owner authorization, NOT requested). Prior exposure disclosed per period; refit schedule (one fixed-recipe refit per period, no tuning); cohort/coverage accounting rules; metrics (per-PA multiclass log loss, per-start-mean weighting, paired bootstrap 2000/20261001; K point-estimate guard 0.002 - not noninferiority); calibration allocation = none in this evaluation, disjoint-chronological if later ordered; acceptance criteria pre-declared (direction consistency + guard + practical threshold; promotion never automatic).
- **Data-date feasibility established BEFORE fold declaration** (game_date column only, no outcome reads): offseason gaps verified (zero dates Oct-Dec 2024 and Jan-Mar 2023/25 - the recorded LGBM failure root); all proposed windows nonempty.
- Status: SPECIFICATION ONLY - no execution, no new learner/feature family/framework/run. Execution requires review + explicit owner approval.

## Lane results ledger (verified)

workload w0v1: pooled W0 favored (VERIFIED). binary objective: control retained (VERIFIED). platoon family: challenger favored, candidate registered (VERIFIED). LGBM bounded-selected vs fixed multinomial: control retained, guard failed, tradeoff recorded (VERIFIED). Full table: docs/reference/reports/experiment_impact_ledger_2026-10-22.md.

Report changed evidence, a checkpoint or a concrete blocker. Do not relay unchanged status, create another queue, or ask the owner to arbitrate routine implementation details.
