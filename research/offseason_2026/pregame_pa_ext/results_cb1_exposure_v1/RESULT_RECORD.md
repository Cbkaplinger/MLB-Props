# RESULT RECORD — C-B1 exposure-profile heterogeneity (executed once, CLOSED)

## Answer first

C-B1 executed once on real data (2026-10-22, owner-delegated
authorization) and is **CLOSED** per the card's stop condition (b):
the paired count-RPS delta CI entirely favors the frozen baseline.

| quantity | value |
| --- | --- |
| executed code SHA | `b026646` (PR #34 head at run time) |
| paired population | 4,823 eligible dev starts (2,312 confirm-block starts excluded, disclosed) |
| count-RPS C-B1 | 1.403500 |
| count-RPS frozen baseline | 1.317613 (matches the registered baseline exactly) |
| delta (C-B1 - frozen) | +0.085887 (positive = worse) |
| 95% CI (slate-date bootstrap, n=2000, seed 20261001) | [+0.071850, +0.099742] |
| p (null-centered), Holm m=1 | 0.0005 |
| decision | `cb1_not_better` -> CLOSE |

## Outputs (write-once, preserved)

`MLB-Props-Research\pregame-pa-ext-v2\diagnostics\cb1_exposure_v1_attempt2\`:

| file | sha256 |
| --- | --- |
| receipt_initial.json | `18c98d818f54410c9eea67f6b93b86b2cb96cbe5f74246e5179cf46e7fc5cff9` |
| receipt_final.json | `1d125e6faacc55219a51a0a81098d9d046ccef36750cc734149d7384489496da` |
| metrics.json | `59033a8e6712af66f3a319783df0e3b4d7803d0284d4770fb529a603b66f5676` |
| cb1_eval_v1.parquet | `cd84ca3abb847ab5180758418a6a90f74810beebd54e81a37a1c260b30298185` |

First authorized attempt (`cb1_exposure_v1`) failed on a runner defect
(confirm-block starts present in the ledger raised instead of being
excluded); failure record preserved untouched; fixed at `b026646` with
a regression test.

## What was estimated (the exposure signal itself)

Per dev block, band rates shrunk toward the frozen cycled prefix-mean
prior (w150):

| block | lineage rows | band 1-9 | band 10-18 | band 19-27 | band 28-36 | band 37-60 |
| --- | --- | --- | --- | --- | --- | --- |
| 2024H2 prior | 460,613 | 0.2190 | 0.2190 | 0.2190 | 0.2190 | 0.2174 |
| 2024H2 q | | 0.2380 | 0.2071 | 0.1946 | 0.1928 | 0.2174 (n=0) |
| 2025H1 prior | 87,808 | 0.2190 | 0.2190 | 0.2190 | 0.2190 | 0.2174 |
| 2025H1 q | | 0.2411 | 0.2133 | 0.2027 | 0.1809 | 0.2174 (n=0) |

The REAL exposure signal exists and points the expected way (the K rate
declines through the order: 0.238 first pass vs 0.195 third pass), but
it is a LEAGUE-LEVEL effect. C-B1 replaces the per-PA sequence with
this population profile, discarding pitcher-specific slot probabilities
- that cost 0.086 RPS, far larger than the exposure gain.

## Structural findings for the record

- Starters' BF distribution is concentrated below 28: band 3
  (BF 28-36) has 1,431 lineage rows in 2024H2 and 225 in 2025H1; band
  4 (BF 37-60) has ZERO (relievers take over). Any exposure-profile
  candidate only has purchase on BF 1-27.
- The frozen arm's RPS (1.317613) matches the M0 descriptive baseline
  to full precision - the comparison machinery is exact.

## Future direction (needs a NEW registration; not scheduled)

A pitcher-conditional exposure profile (per-pitcher band rates shrunk
toward the league profile) would keep pitcher skill AND add the
turnover effect. That is a materially different candidate with an
overfitting risk at pitcher-band sparsity; it requires a new card, not
a C-B1 reopen.
