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

## Integration - COMPLETE (2026-11-03)

The reviewed stack is on main at **`8399f2c`** (actual merge SHA): #51 (`7764ac1`), #53 (`4f2490c`), and the #52 content via PR #54 (`1a1790c` + `8399f2c`; #52's own merge had landed on its base branch, so PR #54 carried it to main; carrier PR #55 was closed redundant). CI `test-and-validate` + `tracking` PASS on the integrated heads; 97 targeted tests green on the merged tree; open-PR count is zero. Verified present on main: the accepted closeout (below), the roles approval-requests amendment, the cohort-test determinism fix, and the full reviewed baseline-stack code. No production/policy/model change was made or authorized by this integration.

## Next experiment: platoon-information value (assigned, checkpoint below)

Binary-K vs multinomial-K: CLOSED 2026-11-04 - Chat 2 artifact verdict VERIFIED; control retained (delta +0.0000969, CI overlapping zero, far below the 0.005 practical threshold); artifacts preserved; PR #57 ready for integration through the existing process (merge via architect delegation).

## Next experiment: platoon-information value - EXECUTED ONCE; BUILDER-REPORTED, pending Chat 2

The comparison ran once 2026-11-04 (owner-approved packet revision 2, code checkpoint `37ce4d2`). **Status: BUILDER-REPORTED, pending Chat 2 independent verification.** Builder-reported: reconstruction gate exact (control = accepted W0, max abs diff 0.0); primary per-PA multiclass log loss control 1.2245976 vs platoon challenger 1.2238507; per-start-mean paired delta **-0.0008712, CI95 [-0.0012622, -0.0005038] - entirely below zero** (challenger favored statistically) and |delta| above the declared 0.0005-nat practical threshold; **K-count non-degradation guard satisfied at point estimate (+0.0000409, margin 0.002; not a noninferiority claim)**. Per the pre-declared rule: the platoon family registers a CANDIDATE feature-family addition for a FUTURE frozen-contract decision; promotion never automatic; no production/policy/live-model change. After Chat 2 verification: close the record once and prepare the reviewed PR for integration under the existing process. Artifacts preserved write-once; single run, no retry. The m0/workload_comparison two-class softmax repair remains DEFERRED.

Report changed evidence, a checkpoint or a concrete blocker. Do not relay unchanged status, create another queue, or ask the owner to arbitrate routine implementation details.
