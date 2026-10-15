# EXPERIMENT CARD — recency-batch-v1 (development-only EW-recency ablation, EXECUTED)

- **Batch:** `recency-batch-v1` (frozen config `research/offseason_2026/specs/count-eval-v2-spec/harness/freeze_recency_batch_v1.json`, config sha256 `4b11e4b7...f810`, status FROZEN-NOT-EXECUTED at registration; executed 2026-10-15 under the frozen literal command)
- **Canonical run dir:** `C:\Users\ckaplinger\MLB-Props-Research\recency-batch-v1\c09890ae6c3d111f187fcd35d5b2bca17f27fa24fd13f683a9489bf5d3d0c3eb\` (write-once; untouched by this card)
- **Scope:** DEVELOPMENT-ONLY. Three dev folds (block_2024H1 / block_2024H2 / block_2025H1, n = 94,458 / 87,808 / 95,357; pooled 277,623 PA rows over 281 slate dates). confirm_2025H2 EXCLUDED-BY-CONFIG (`include_confirm=False`; no preds_confirm file written; not fitted, not scored, not bootstrapped).
- **Candidates (all RAW principal lane; log loss + CAL descriptive only):** `P1_B_logreg` (6-feature REFERENCE), `P1_H3_pitcher_ew_only` (B + ew_pitcher), `P1_H3_batter_ew_only` (B + ew_batter), `P1_H3_incumbent_refit` (B + both EW columns). EW half-life 90d FIXED; half-life search PROHIBITED.
- **Primary metric:** Brier on pooled dev; paired slate-date block-stratified row-weighted bootstrap, 2000 resamples, seed 20261001, ONE shared draw stream. C3.8 null-centered approximate bootstrap test + Holm step-down over the 4 predeclared RAW Brier contrasts.

## INTERPRETATION (owner-directed correction, canonical wording 2026-10-15)

**Small, consistent development-only PA gains; no promotion. Practical downstream value remains unestablished by this batch.**

- All four EW-bearing candidates beat the 6-feature `P1_B_logreg` reference on BOTH Brier and log loss in EVERY fold and in pooled dev, and every contrast CI lies entirely below zero. The gains are small (pooled-dev Brier deltas of order 1e-4) but directionally consistent across all folds and both metrics.
- The four null-centered p-values all sit at the 2000-resample resolution floor, **approximately 0.00050** (each = (1+1)/(2000+1) because zero centered resamples exceeded the observed delta in magnitude). **Identical floor values are an artifact of the resample resolution and are NOT evidence that the four contrasts' strengths are identical.**
- **`P1_H3_incumbent_refit` (both-EW) is the PROVISIONAL PA DEVELOPMENT LEADER among the four configurations** (best pooled-dev Brier 0.169744 and log loss 0.520089, best in every fold). This supports **keeping its feature blocks in the development harness**; it is **NOT a production-promotion decision**.
- **No new confirmation and no 2026 evidence** was produced by this batch: confirm_2025H2 was excluded by config, and the three dev folds are the same development windows already used by the harness. The C3.8 test is an approximate centered-bootstrap procedure with no finite-sample-validity guarantee.
- Superseded phrasing note: an earlier draft framing ("practically negligible; reject adoption") was never committed to the repo or the lake run dir; per owner direction the corrected wording above is the canonical interpretation at materialization. The frozen run-dir files (metrics.json / metrics.md) are byte-preserved; this card carries the interpretation.

## Results (absolute scores, RAW lane; full table in `report/recency_batch_results_table.md`)

Pooled dev, n = 277,623, 281 dates:

| candidate | log loss | Brier |
| --- | ---: | ---: |
| P1_B_logreg (REFERENCE) | 0.520750 | 0.169976 |
| P1_H3_pitcher_ew_only | 0.520454 | 0.169876 |
| P1_H3_batter_ew_only | 0.520382 | 0.169843 |
| **P1_H3_incumbent_refit (PROVISIONAL LEADER)** | **0.520089** | **0.169744** |

Predeclared RAW Brier contrasts (signed delta = a - b; negative = a better; CIs unadjusted percentile; Holm family alpha 0.05; p-values at the 2000-resample resolution floor, approx 0.00050 each, Holm-adjusted approx 0.00200 each):

| contrast | a | b | delta | CI95 | p | p_holm |
| --- | --- | --- | ---: | --- | ---: | ---: |
| C1 | pitcher_ew_only | B_logreg | -0.0000996 | [-0.000132, -0.000066] | ~0.00050 | ~0.00200 |
| C2 | batter_ew_only | B_logreg | -0.0001331 | [-0.000160, -0.000106] | ~0.00050 | ~0.00200 |
| C3 | incumbent_refit | pitcher_ew_only | -0.0001323 | [-0.000160, -0.000105] | ~0.00050 | ~0.00200 |
| C4 | incumbent_refit | batter_ew_only | -0.0000988 | [-0.000131, -0.000066] | ~0.00050 | ~0.00200 |

## Verification record (independent recompute, 2026-10-15)

From the 12 saved preds parquets only (`independent_recompute_verification.json` in this dir):

- Shared rows/labels: `(game_pk, at_bat_number, batter, game_date)` key sets and `y` vectors are IDENTICAL across all 4 candidates in all 3 blocks (verified by sorted-frame equality).
- Absolute scores: RAW-lane per-fold + pooled log loss and Brier recomputed from preds reproduce `metrics.json` BIT-EXACTLY (max |delta| = 0.0 across all 16 score cells).
- Resampling: draw stream replicated exactly (seed 20261001, n_boot 2000, block-stratified slate-date multinomial, row-weighted num/den; `slate_date_draws` semantics).
- Contrasts: all 4 deltas, null-centered p-values, and Holm adjustments reproduce the reported values exactly (max |delta| = 0.0 on delta, p, and p_holm).
- Confirmation absence: zero `*confirm*` files in the run dir; manifest `include_confirm = false`.

## MLflow status

NOT LOGGED. `C:\Users\ckaplinger\MLB-Props-Research\mlflow.db` (experiment `pa-k-probability-v1`, id 1) contains exactly 21 runs: the first-run-v1 parent `e2194b6b...` + 20 children (`first-run-v1-e59da946da21`). Zero runs and zero tags reference `recency` in any form. The recency batch was neither logged automatically (the harness `comparison.py` does not write to MLflow; MLflow logging for first-run-v1 was a separate post-hoc import step) nor imported afterward. The existing lake importer can be run post-hoc against the frozen run dir without refitting, per the first-run-v1 precedent.
