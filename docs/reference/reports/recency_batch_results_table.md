# recency-batch-v1 — complete absolute score table + contrast verification (reviewer prep, 2026-10-15)

Source of truth: frozen run dir `C:\Users\ckaplinger\MLB-Props-Research\recency-batch-v1\c09890ae6c3d111f187fcd35d5b2bca17f27fa24fd13f683a9489bf5d3d0c3eb\metrics.json` (mirrored byte-identical at `research/offseason_2026/experiments/recency-batch-v1-2026-10-15/metrics.json`). RAW lane is the principal lane; log loss is secondary; CAL lane descriptive only (not shown here; see first-run-v1 supplemental-metrics precedent). Bootstrap: 2000 resamples, seed 20261001, slate-date block-stratified row-weighted ratio, one shared draw stream.

## Complete absolute score table (RAW lane)

### Per fold + pooled — Brier

| candidate | block_2024H1 (n=94,458) | block_2024H2 (n=87,808) | block_2025H1 (n=95,357) | pooled dev (n=277,623) |
| --- | ---: | ---: | ---: | ---: |
| P1_B_logreg (REFERENCE) | 0.169466 | 0.173029 | 0.167669 | 0.169976 |
| P1_H3_pitcher_ew_only | 0.169368 | 0.172933 | 0.167565 | 0.169876 |
| P1_H3_batter_ew_only | 0.169368 | 0.172909 | 0.167489 | 0.169843 |
| P1_H3_incumbent_refit | 0.169271 | 0.172813 | 0.167386 | 0.169744 |

### Per fold + pooled — log loss

| candidate | block_2024H1 (n=94,458) | block_2024H2 (n=87,808) | block_2025H1 (n=95,357) | pooled dev (n=277,623) |
| --- | ---: | ---: | ---: | ---: |
| P1_B_logreg (REFERENCE) | 0.519801 | 0.527642 | 0.515345 | 0.520750 |
| P1_H3_pitcher_ew_only | 0.519497 | 0.527358 | 0.515043 | 0.520454 |
| P1_H3_batter_ew_only | 0.519540 | 0.527309 | 0.514836 | 0.520382 |
| P1_H3_incumbent_refit | 0.519244 | 0.527029 | 0.514535 | 0.520089 |

Slate dates per fold: 95 / 88 / 98 (pooled 281). Full-precision values are in `metrics.json` (per_fold + pooled_dev).

## Predeclared RAW Brier contrasts (recomputed independently from the 12 preds parquets)

Signed delta = a - b (negative = a better). CIs are UNADJUSTED percentile intervals from the shared draw stream. p-values are two-sided null-centered approximate bootstrap: p = (1 + #{|delta* - delta| >= |delta|}) / (B + 1), B = 2000. Holm step-down at family alpha 0.05 across the 4 contrasts.

| contrast | a | b | delta (recomputed) | CI95 unadjusted | p (recomputed) | p_holm (recomputed) |
| --- | --- | --- | ---: | --- | ---: | ---: |
| C1_pitcher_ew_vs_B | P1_H3_pitcher_ew_only | P1_B_logreg | -0.0000996465 | [-0.00013246, -0.00006558] | 0.00049975 | 0.00199900 |
| C2_batter_ew_vs_B | P1_H3_batter_ew_only | P1_B_logreg | -0.0001330947 | [-0.00016008, -0.00010605] | 0.00049975 | 0.00199900 |
| C3_both_vs_pitcher_only | P1_H3_incumbent_refit | P1_H3_pitcher_ew_only | -0.0001322806 | [-0.00015966, -0.00010496] | 0.00049975 | 0.00199900 |
| C4_both_vs_batter_only | P1_H3_incumbent_refit | P1_H3_batter_ew_only | -0.0000988324 | [-0.00013141, -0.00006567] | 0.00049975 | 0.00199900 |

### Verification against the reported values

| check | result |
| --- | --- |
| Contrast deltas vs `metrics.json` | MATCH, max abs delta = 0.0 |
| Null-centered p-values vs `metrics.json` | MATCH, max abs delta = 0.0 |
| Holm adjustments vs `metrics.json` | MATCH, max abs delta = 0.0 |
| Resample matrix | replicated exactly: n_boot 2000, seed 20261001, block-stratified slate-date draws, row-weighted num/den, one shared stream |
| Absolute scores (16 cells: 4 candidates x {3 folds + pooled} x {Brier, log loss}) | MATCH, max abs delta = 0.0 (bit-exact) |
| Shared rows/labels | key sets `(game_pk, at_bat_number, batter, game_date)` + `y` IDENTICAL across all 4 candidates in all 3 blocks (sorted-frame equality) |
| Confirmation absence | 0 `*confirm*` files in run dir; manifest `include_confirm = false`; fold_order dropped confirm_2025H2 |

## Interpretation (owner-directed canonical wording)

Small, consistent development-only PA gains; no promotion. Practical downstream value remains unestablished by this batch. All four p-values sit at the 2000-resample resolution floor, approximately 0.00050; identical floor values are a resolution artifact, NOT evidence the contrasts' strengths are identical. P1_H3_incumbent_refit (both-EW) is the PROVISIONAL PA DEVELOPMENT LEADER among the four configurations - support for keeping its feature blocks, not a production-promotion decision. No new confirmation, no 2026 evidence.

Full verification detail: `research/offseason_2026/experiments/recency-batch-v1-2026-10-15/independent_recompute_verification.json`.
