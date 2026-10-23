# RESULT RECORD — market eval: pitcher_strikeouts vs the near-close line
# (executed once 2026-10-22; dev blocks only, confirm untouched)
#
# STATUS UPDATE (2026-10-22, later): the ladder benchmark CANNOT be run
# validly from the held archive - the alternate market is OVER-SIDE
# ONLY (under quotes were never captured), per-rung book coverage is
# sparse (1-4 books), and per-book de-vig margins are noisy (p10 =
# -0.021). The implied count distribution is therefore unreliable and
# the ladder falsification test is BLOCKED on data. The placebo check
# is DEGENERATE for the same structural reason: the close is so flat
# (std 0.052) that shuffling line-to-start changes almost nothing
# (placebo gap -0.040 vs real -0.0339) - it cannot falsify the result.
# The headline -0.0339 gap remains UNPROVEN: no leak was found
# (selection, timing, push, workload all audited clean), but the two
# falsification tests the owner ordered are unavailable from the held
# data. The 2026 holdout (defined, not run) is the remaining decisive
# test. Receipts for all ladder attempts preserved write-once
# (ladder_benchmark_v1 .. _attempt5).

## Answer first

On the 4,527 scored dev starts (93.9% of the 4,823 registered), the
REGISTERED frozen count layer beats the de-vigged near-close consensus
at its own line:

| metric | model | close | delta (model - close) |
| --- | --- | --- | --- |
| log loss (over/under) | 0.65723 | 0.69118 | **-0.03395** |
| Brier | 0.23379 | 0.24902 | -0.01523 |
| count-RPS (full distribution) | 1.31586 | n/a (line only) | - |

- 95% CI on the log-loss delta (paired slate-date bootstrap, n=2000,
  seed 20261001): **[-0.04216, -0.02590]** - entirely negative.
- p (null-centered) = 0.0005; Holm m=1 adjusted = 0.0005.
- decision: `model_better_than_close` (dev evidence; the confirmation
  block remains the final judge).

## Coverage (drops disclosed at every stage)

| stage | starts |
| --- | --- |
| registered model starts (dev) | 4,823 |
| window starts in the odds join | 4,866 (model frame covers 4,823) |
| starts without event/commence (tier B clock proxy) | 2,442 |
| scored vs a near-close consensus | **4,527 (93.9%)** |
| median two-sided books per start | 7 |

Drops: 296 model starts had no two-sided near-close consensus (late
scratches / no board); they are excluded symmetrically for both sides
and disclosed. Join chain reused UNCHANGED from the tested
odds-coverage machinery (16 tests). Cutoff policy: strict pre-cutoff
within 60 min (tier A, 2025-26) / vendor `close` snapshot (tier B,
2024). The close snapshot is a NEAR-close (p50 ~T-9.35min) - treat
all close comparisons as near-close.

## Reliability (model over-probability deciles)

The model is close to calibrated at the extremes and optimistic in
the middle-low buckets (e.g. p=0.27 -> observed 0.34; p=0.37 -> 0.44),
pessimistic around 0.51 -> 0.47. Direction of the miscalibration is
mixed; the owner's calibration plan (held per step 4) now has evidence
to act on for this market.

## Outputs (write-once, preserved)

`...\pregame-pa-ext-v2\diagnostics\market_eval_k_v1_attempt2\`:
receipt_initial `37411c8d...`, receipt_final / metrics / parquet
recorded in the receipt chain; the first attempt (`market_eval_k_v1`)
failed on a string-timestamp dtype defect, failure record preserved,
fixed at `e3c2e50`.

## Workload-leakage experiment (owner-ordered, 2026-10-22)

BF input answer: the per-start PMF used the REGISTERED PREGAME BF
forecast (bf-workload-v1 artifact, per-start pmf37 with prior_n /
prior_mean state columns; count_agg_eval.py:269-273) - never the
realized batters faced.

Workload A/B (same 4,527 joined starts, same consensus lines):

| workload input | model log loss | gap vs close (0.6912) |
| --- | --- | --- |
| A: registered per-start BF forecast (as scored) | 0.6572 | -0.0339 |
| B: POOLED workload (one shared BF distribution, zero per-start workload info) | 0.6564 | **-0.0348** |

The edge SURVIVES with all per-start workload information removed ->
workload leakage excluded as the cause.

## What the edge actually is (decomposition)

The close's de-vigged principal-line price carries almost no
discrimination: std(p_close) = 0.052 vs the model's std(p_model) =
0.152; the close sits between coin-flip (0.6931) and the oracle
constant (0.6904) - it beats coin-flip by only 0.0019, exactly the
owner's bias arithmetic. The model's 0.034 advantage is RESOLUTION
(knowing which starts lean over), not the bias term. CRITICAL CAVEAT:
the de-vigged price AT the settled principal line is ~50/50 partly BY
CONSTRUCTION (books balance the main line; the market's information
lives in the line choice and the ladder). The honest market benchmark
is therefore the ALTERNATE-LADDER-implied count distribution, not the
binary principal-line price. The ladder comparison is the corrected
test and supersedes the -0.0339 headline as a market benchmark.

- Dev evidence only: the frozen model's fit lineage (2023) predates
  the dev blocks, but the confirmation block is the pre-registered
  final judge; no claim of live edge until it confirms.
- The close comparison is at the line (binary over/under), not the
  full count distribution; the close cannot produce a count PMF from
  one line.
- 2024 events use the vendor close snapshot (no local commence times
  exist for 2024, documented in the odds-archive acceptance audit).
