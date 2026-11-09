# NEXT - current action

Owner: architect. Updated 2026-11-08. ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your card. EXECUTION_BACKLOG remains the single queue.

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

## Current action: label-free prediction path (published; awaiting Chat 2 review)

PR #70 (`research/label-free-prediction`, base main): research-only
orchestration `label_free_prediction.run_prediction` connecting the
retained 12-feature candidate's existing construction seams (states-v2 +
prior features + platoon-features-v1) to the existing label-free inference
module (PR #68). After Chat 2's probe (identical per-class coefficients
made the original fixture feature-independent), the fixture now uses
distinct per-class coefficient rows: 10 synthetic tests green covering
same-date/future perturbation invariance, strictly-prior sensitivity
(max prob delta 0.0251), permutation invariance, adapter parity with the
registered seams, and refusals; zero-coef uniform case kept as a
degenerate arithmetic smoke test only. Synthetic only - no real/private
data, no fitting/scoring, no calibration, no promotion. Awaiting Chat 2
review; prior Stage A gate (PR #67) merged.

Report changed evidence, a checkpoint or a concrete blocker. Do not relay unchanged status, create another queue, or ask the owner to arbitrate routine implementation details.
