# RESULT RECORD — market eval: pitcher_strikeouts vs the near-close line
# (executed once 2026-10-22; dev blocks only, confirm untouched)
#
# STATUS 3 (owner-ordered join-validity audit, 2026-10-22, latest) —
# **THE MARKET COMPARISON IS UNDER AUDIT; THE JOIN FAILED VALIDITY.**
# RETRACTED: any framing that the -0.034 gap is model skill. Evidence:
# (a) line<->realized-K correlation is only 0.206 and line<->model-mean
# only 0.381 over the 2,245 true-close starts (a correctly matched
# closing line should sit ~0.5-0.7 against realized K) — the attached
# lines carry almost no start-specific information;
# (b) the line's MAE (1.985) EQUALS a constant league-mean predictor's
# MAE (1.985) — the matched lines add nothing over a constant;
# (c) 505 of 2,161 matched events (23%) are matched at a +/-1 DAY date
# tolerance, where doubleheaders and adjacent series make wrong-event
# matches likely (the earlier 48.9% exact-name figure was a check-side
# fan-out artifact, not a join defect — the id map is clean);
# (d) a one-parameter baseline "beats" the close by -0.0305 — with
# uninformative lines, ANY model with real signal beats them.
# CONSEQUENCE: the close, dumb-baseline and model gaps in this record
# are NOT interpretable until the event join is fixed (date-tolerance
# redesign + per-start event verification) and all three are rescored.
# The dumb-baseline test (owner hypothesis) is nevertheless CONFIRMED
# in its purpose: the earlier headline was not model skill.
#
# STATUS 1 (earlier): the ladder benchmark CANNOT be run validly from
# the held archive - the alternate market is OVER-SIDE ONLY (under
# quotes were never captured), per-rung book coverage is sparse (1-4
# books), and per-book de-vig margins are noisy (p10 = -0.021). The
# implied count distribution is therefore unreliable and the ladder
# falsification test is BLOCKED on data. The line-shuffle placebo is
# DEGENERATE (the close is so flat that shuffling line-to-start is a
# no-op). Receipts for all ladder attempts preserved write-once
# (ladder_benchmark_v1 .. _attempt5).

## Follow-up checks (owner-ordered, 2026-10-22, later still)

- 2024 relabeled **"prior-evening line"**; it is excluded from every
  close comparison. THE close comparison is 2025H1 true T-5 closes
  only: n=2,245, model 0.6610 vs close 0.6947, gap -0.0337.
- LABEL AUDIT: PASS - realized_k matches the OFFICIAL starter K from
  the frozen pa_table on 100% of joined starts (0 differing; mean K
  4.80; mean official BF 21.96). The 17.2 eval-PAs-per-start figure is
  the projected-lineup slot frame (the per-PA feature population), not
  the outcome label.
- ENCOMPASSING (over_hit ~ const + p_model + p_close, OLS White SE,
  n=2,245): p_model coef +0.846 (t=+1.75, NOT significant at 5%);
  p_close coef +0.087 (t=+0.19). The model keeps its weight with the
  close included, but not at conventional significance - the edge
  stays UNPROVEN by this test.
- MAE/RMSE (2025H1): model mean K 1.857/2.348 beats the market line
  1.985/2.492 vs actual K.
- CORRECTED PLACEBO (shuffle the MODEL's predictions across starts,
  20 seeds): shuffled model LOSES to the close (close - shuffled =
  -0.062, i.e. ll 0.757 vs 0.695); the real model beats the close by
  +0.034 - far outside the placebo range. The matched pairing carries
  real information.
- KALSHI: the exchange ladder (11,929 rows, 676 closes, two-sided) is
  2026-season ONLY (2026-07-30..2026-09-05) - no dev overlap. It
  becomes the two-sided distribution benchmark for the 2026 holdout
  run, where the sportsbook ladder cannot serve.
- Net position: promising dev evidence that passes the label and
  corrected-placebo checks; the encompassing test does not reach
  significance; the extraordinary-claim bar is unmet. The 2026 holdout
  (with Kalshi as the ladder benchmark) is the decisive test.

## Bias check (owner-ordered, 2026-10-22, latest)

2025H1 (n=2,245): mean line 4.9009, mean model K 4.5262, mean realized
K 4.8134. Line bias +0.0875 K; model bias -0.2871 K (the model
under-predicts on average).

| predictor | MAE | RMSE |
| --- | --- | --- |
| market line (raw) | 1.985 | 2.492 |
| market line (bias-adjusted) | 1.980 | 2.490 |
| model mean K (raw) | 1.857 | 2.348 |
| model mean K (bias-adjusted) | 1.849 | 2.330 |

The constant line bias explains almost NOTHING of the model's RMSE
advantage (2.492 -> 2.490; the gap stays ~6%). Log loss at the
bias-adjusted line (ladder-sampled at line - bias, n=856 with usable
curves): close 0.6835 vs model 0.6321 on the same starts - the gap
WIDENS to -0.0514 under the location correction. The model's advantage
is distributional shape, not line location; it survives the bias
check.

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
