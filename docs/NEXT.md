# NEXT - current action

Owner: architect. Updated 2026-10-31. ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your card. EXECUTION_BACKLOG remains the single queue.

## Scientific milestone

~~Complete prediction-path verification and produce a valid historical baseline benchmark~~ — **COMPLETED**: the Ref0-vs-Ref1 multiclass baseline comparison was executed, independently verified, and accepted with limitations.

## Current next task

**Workload personalization experiment** (W0 pooled league BF vs W1 pitcher-specific BF-workload-v1). The experiment card is at `docs/adr/PROPOSED-workload-personalization-experiment.md` (revised at `460dd353`). One authorized run was executed 2026-11-02 after explicit owner approval (checkpoint `45ed606`, packet `731f05c`); result is **BUILDER-REPORTED pending Chat 2 independent verification**.

**Builder-reported result (one authorized run, status COMPLETED, all guards passed):**
- Durable artifacts: `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\workload_personalization_w0v1\` (write-once; receipt chain verified, no failure record)
- Reconstruction gate PASSED: max per-start abs RPS diff **0.0** vs pinned accepted reference `3414d0d2…`, tolerance 1e-12, n=2,509
- Cohort: 2,509 starts, hash match true (registered `f77d7a66…`); requests 64,746 → 22,581 after restriction
- Primary: mean count-RPS W0 1.29525 vs W1 1.30765; **Δ = RPS(W1) − RPS(W0) = +0.012406, CI95 [+0.004410, +0.020368]** — entirely above zero → **pooled control favored on development data**; |Δ| > 0.005 engineering threshold
- BF diagnostics (denominator 2,509/arm): W1 has higher central-interval coverage (50%: 0.755 vs 0.644; 90%: 0.977 vs 0.939) but WORSE distribution score (RPS 2.544 vs 2.216) and point MAE (3.321 vs 3.057), and underpredicts mean BF more strongly (predicted E[BF] below observed BF by 1.03 vs 0.19). Both arms' central intervals overcover relative to nominal levels, more so for W1; higher coverage is not automatically better. (Correction of an earlier builder phrasing: W1 does NOT "over-predict" — it under-predicts mean BF; the "wider distribution buys coverage" claim is not established by the saved evidence and is retracted.)
- Output-hash manifest (sha256, on-disk verified): workload_per_start_v1.parquet `ae971758…`, workload_comparison_report.json `d105c7f9…`, keyed_pa_probabilities.parquet `425722d9…`, model_artifact.json `2471f69c…`, k_pmf_per_start_v1.parquet `d64d362d…`, bf37_by_start_v1.parquet `56f554ac…`, bf37_pooled_by_date_v1.parquet `16f49088…` (full hashes in `receipt_final.json` at the destination; manifest reconciliation true)
- No rescue variants, no additional candidate runs, no production changes, no retries.

**Pending:** Chat 2 independent verification of the run artifacts; then update this record ONCE to "workload experiment completed; pooled control favored on development data" (verified).

## Prior completed milestones in this lane

- **Historical starter-outcome derivation**: 9,714 starts derived from the expanded 2023–2024 PA source; overlap with the registered 2024H2 artifact confirmed (2,334/2,334 keys, zero discrepancies).
- **History-sensitivity scorecard**: the learned simple-pitcher reference beats the 2024H2-only population-rate control (Δ −0.0111 count-RPS, CI entirely below zero); accepted with limitations.
- **Ref0-vs-Ref1 multiclass baseline**: the regularized multinomial model's K marginal produces significantly better count forecasts than population proportions (Δ −0.0864 count-RPS, CI entirely below zero); accepted with limitations by Chat 2.
- **Stage-A prediction-path reconciliation**: implementation reviewed, real-artifact execution still authorization-gated.

## Completion and next phase

After the workload result: isolate one PA improvement → freeze selected features → bounded time-ordered tuning → locked evaluation → optional calibration → separately authorized confirmation/operations. Protected partitions and old registrations remain unchanged.

Report changed evidence, a checkpoint or a concrete blocker. Do not relay unchanged status, create another queue, or ask the owner to arbitrate routine implementation details.
