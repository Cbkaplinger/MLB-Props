# count-eval-v2 comparison metrics

Baseline: `P0_log5`; bootstrap 2000 resamples, seed 20261001, block-stratified slate-date (repaired method).

## block_2024H1

| candidate | n | dates | log loss | Brier |
| --- | ---: | ---: | ---: | ---: |
| P1_B_logreg | 94458 | 95 | 0.519801 | 0.169466 |
| P1_H3_pitcher_ew_only | 94458 | 95 | 0.519497 | 0.169368 |
| P1_H3_batter_ew_only | 94458 | 95 | 0.519540 | 0.169368 |
| P1_H3_incumbent_refit | 94458 | 95 | 0.519244 | 0.169271 |

## block_2024H2

| candidate | n | dates | log loss | Brier |
| --- | ---: | ---: | ---: | ---: |
| P1_B_logreg | 87808 | 88 | 0.527642 | 0.173029 |
| P1_H3_pitcher_ew_only | 87808 | 88 | 0.527358 | 0.172933 |
| P1_H3_batter_ew_only | 87808 | 88 | 0.527309 | 0.172909 |
| P1_H3_incumbent_refit | 87808 | 88 | 0.527029 | 0.172813 |

## block_2025H1

| candidate | n | dates | log loss | Brier |
| --- | ---: | ---: | ---: | ---: |
| P1_B_logreg | 95357 | 98 | 0.515345 | 0.167669 |
| P1_H3_pitcher_ew_only | 95357 | 98 | 0.515043 | 0.167565 |
| P1_H3_batter_ew_only | 95357 | 98 | 0.514836 | 0.167489 |
| P1_H3_incumbent_refit | 95357 | 98 | 0.514535 | 0.167386 |

## pooled dev (block_2024H1, block_2024H2, block_2025H1)

| candidate | n | dates | log loss | Brier |
| --- | ---: | ---: | ---: | ---: |
| P1_B_logreg | 277623 | 281 | 0.520750 | 0.169976 |
| P1_H3_pitcher_ew_only | 277623 | 281 | 0.520454 | 0.169876 |
| P1_H3_batter_ew_only | 277623 | 281 | 0.520382 | 0.169843 |
| P1_H3_incumbent_refit | 277623 | 281 | 0.520089 | 0.169744 |

confirm_2025H2 is reported per-fold only and is never pooled into dev.
