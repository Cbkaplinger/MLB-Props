# PRE-REGISTRATION CARD (DESIGN ONLY) — Decision-flip analysis: exact PMF
# vs registered PMF on the 4,823 development starts (2026-10-21)
#
# STATUS: PROPOSED DESIGN — NOT EXECUTED, NO REAL OUTCOMES READ, NO BETTING
# SIMULATION RUN. This card specifies what one bounded analysis would
# compute IF authorized. Implementation requires Chat 2 review of this
# card plus explicit owner authorization.
#
# Derived from: count_agg_eval_v1 results (PR #29, the exact PB
# aggregator's count-RPS improvement of −0.0003333461) and
# eval_spec_count_aggregation_A_2026-10-20.md.

## 1. Hypothesis

The exact Poisson-Binomial aggregator improves count-RPS by −0.000333
(resolution floor), but count-RPS improvement is NOT a betting-layer
result. This card tests whether the distributional improvement changes
any BETTING DECISIONS at the registered line and policy thresholds. If
almost nothing flips, the Question A improvement is a documented
curiosity and effort moves elsewhere.

## 2. Population (frozen)

The same 4,823 eligible development starts from the preserved run ledger
(frozen start-key set sha256 618e8e75...). NO confirmation starts. NO
new eligibility. The 43 dev abstentions excluded (unchanged). The
original prediction run remains UNACCEPTED.

## 3. Arms (no new model, no new fit)

- BASELINE PMF: the registered cycled prefix-mean binomial count PMF
  (from the preserved run ledger, already computed in the Question A
  evaluation table).
- CHALLENGER PMF: the exact Poisson-Binomial count PMF (from
  count_agg_eval_v1.parquet, already computed in the same run).
- Both PMFs are already persisted in count_agg_eval_v1.parquet in the
  lake bundle. This diagnostic reads them; it does not regenerate them.

## 4. Decision definition

An over/under decision is defined as: the bettor takes the OVER when the
model's P(K >= line) exceeds a pricing threshold, and the UNDER when it
falls below the complementary threshold. The LINE is the registered
market line (e.g., 5.5, 6.5, 7.5 — the same milestones used in the
registered machinery). The price threshold is the pre-declared minimum
edge (model probability minus implied probability from a reference
price) that triggers a bet.

For this diagnostic:
- The LINE is set to the registered milestones (6.5, 8.5, 10.5, 12.5)
  which map to the registered K>=6/8/10/12 milestones.
- The PRICE threshold is NOT simulated (no real prices); instead, the
  decision is defined as a DIRECTIONAL signal: OVER if the model's
  P(K >= line) exceeds 0.5, UNDER otherwise. This is a simplification
  that isolates the flip count without requiring prices.
- A FLIP is defined as: baseline and challenger produce DIFFERENT
  directional signals for the same (start, line) pair.

## 5. Primary output

- **Flip count** per line: the number of starts where the baseline and
  challenger disagree on over/under direction.
- **Slate-date-clustered 95% interval** on the flip proportion (paired
  slate-date bootstrap, n=2000, seed 20261001, same registered
  machinery).
- **Direction of flips**: how many moved from UNDER to OVER vs OVER to
  UNDER per line.
- **Practical-significance threshold** (pre-declared): if the flip count
  is < 2% of starts per line (i.e., < 97 of 4,823), the distributional
  improvement is declared PRACTICALLY NEGLIGIBLE for betting purposes
  and the candidate is closed without further investment.

## 6. Stop conditions

- If the total flip count across all four lines is < 2% per line, stop
  and close: the exact aggregator is a documented curiosity with no
  betting-layer relevance.
- If the flip count is >= 2% per line, the result is INTERESTING and
  warrants a separate profit-replay card (which requires prices and is
  a separate authorization).
- No profit estimation in this diagnostic. The flip count is the ONLY
  output.

## 7. Metrics reported (descriptive, never gated)

- Per-line flip counts and directions.
- Slate-date-clustered 95% intervals on the flip proportion.
- The overlap between baseline and challenger PMF shapes for flipped
  starts (descriptive).

## 8. What this diagnostic does NOT do

- No profit estimation, no ROI, no bet sizing, no policy replay.
- No confirmation evaluation.
- No claim that Question A improves or hurts betting outcomes (the flip
  count is a NECESSARY but not SUFFICIENT condition for a betting-layer
  effect).
- No Question B implementation.

## 9. Relationship to the closed batter-history experiment

The batter-history candidate was REJECTED (log loss worse). This
decision-flip diagnostic uses the SAME baseline and challenger PMFs from
the Question A diagnostic (exact aggregator vs registered aggregator) —
it does NOT use the rejected batter-history challenger. The two are
separate candidates: the batter-history challenger was a PA-level
feature change (rejected); the Question A exact aggregator is a
count-layer aggregation change (count-RPS improved, now testing
decision relevance).

## 10. Provenance requirements (same as the batter-history diagnostic)

- Immutable receipt_initial.json written FIRST.
- receipt_final.json chains to the initial by sha256.
- Consumed inputs: the preserved run ledger (p9 + p_baseline +
  p_challenger), the registered BF artifact, the realized-count source
  (start_metrics_v2 lineage), and the count_agg_eval_v1 parquet (which
  already contains both PMFs).
- No in-place receipt repair.
- Write-once output directory.
- Failure records preserved.


## 11. Pre-run descriptive outputs (added 2026-10-21)

In addition to the primary flip-count output, the diagnostic reports these
pre-run descriptive statistics (never gated, always reported):

- |DP| distribution: for each (start, line) pair, |P_challenger(K>=line)
  - P_baseline(K>=line)| — reported as: min, p25, median, p75, max, mean,
  and the proportion of pairs with |DP| < 0.01, 0.01-0.05, and > 0.05.
- Per-line baseline and challenger P(K>=line) distributions (min, median,
  mean, max).
- The count of starts where both arms agree the probability is within
  0.01 of 0.5 (genuinely uncertain starts) vs where both agree it is
  clearly one side (|P-0.5| > 0.2).

These descriptives contextualize the flip count: a high flip count with
tiny |DP| values means the flips are noise-driven, while a high flip
count with large |DP| values means the aggregators genuinely disagree
about the outcome likelihood.
