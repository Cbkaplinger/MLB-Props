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

The integrated prediction path (main `3a807a98`) reproduced the saved platoon-candidate forecasts from the same fitted model and pinned inputs: **PASS, exact zero** at both grains (2,509 starts; 22,581 PA-grain rows; 60,216 PMF rows; tolerance 1e-12). Reference receipt attested as a **present-day verified snapshot** (`b1b91357...`, four manifest artifacts MATCH) - no historical byte continuity claimed. Reproducibility/identity only, NOT predictive superiority. Evidence (write-once, preserved): `...\diagnostics\parity_platoon_candidate_v1\` (chain `b70a2f90...`). Full record: `docs/EXECUTION_BACKLOG.md` (executed-parity block, 2026-11-09).

## Ablation baseline decision (owner, 2026-11-09)

- **Reference control:** registered 8-feature multinomial + pooled W0.
- **Development challenger:** registered 12-feature platoon recipe (platoon-features-v1).
- **No production promotion and no fresh-validation claim;** promotion never automatic. The challenger's three favored results remain candidate evidence, never a promotion.
- Scope limits on component support: the binary-K and LGBM lanes **retained the control within their declared comparisons** - that is not universal proof that multinomial is superior; Ref0-vs-Ref1 favored the K marginal over population proportions.
- **K-count aggregation vs evaluation metrics (separate layers):** `adapter.start_count_pmfs` builds per-start K-count PMFs from per-PA probabilities + pooled BF37 (construction machinery, not a metric); evaluation = per-PA multiclass log loss primary, per-start means, paired slate-date bootstrap 2000/20261001, K-count RPS non-degradation guard (0.002).
- Full recipe detail (history states-v2, W0 workload, calibration = none in every verified arm, control/challenger distinction): `docs/EXECUTION_BACKLOG.md` (ablation-baseline-decision block, 2026-11-09). Verified lane results table: `docs/reference/reports/experiment_impact_ledger_2026-10-22.md`.

## Current action: awaiting the architect's first assigned ablation

The ablation pairing is decided (control vs challenger above). No ablation work starts until the architect names the first question. Standing unresolved item: no calibration comparison exists; challenger production promotion remains unset.

Report changed evidence, a checkpoint or a concrete blocker. Do not relay unchanged status, create another queue, or ask the owner to arbitrate routine implementation details.
