# EVALUATION SPEC — count-aggregation Question A (exact heterogeneous
# aggregator), 2026-10-20. Compact pre-registration draft derived from
# note_count_aggregation_future_2026-10-20.md (findings section) and the
# closed batter-history card's discipline. NOT AUTHORIZED: no real-outcome
# evaluation has run; this spec defines what one bounded approval would
# execute.

## Hypothesis (ONE change at a time)

The registered aggregation models the first N batters faced as i.i.d.
Binomial(K; N, pbar_n) with pbar_n = cycled prefix mean of the nine slot
probabilities (homogenization; separation tests show heterogeneous
prefixes are mis-dispersed: tails overstated, middle understated). The
challenger replaces ONLY that within-n aggregation with the EXACT
heterogeneous Poisson-Binomial over the same cycled per-PA probabilities.
Pitcher features, PA probabilities, lineups, BF workload inputs, and
eligibility are UNCHANGED. Workload/performance dependence (Question B) is
OUT of scope.

## Arms

- Baseline: the registered aggregation (adapter.cycled_cond_mean +
  count_pmf_from_mixture) on the preserved run's p9 arms (H3-raw primary
  arm; L5 mirrored for completeness, never gated).
- Challenger: exact_count_pmf (Poisson-Binomial DP over cycled[:n]) on the
  SAME p9 values and the SAME BF workload per start (bf_pmf_from_37
  extension, cap 60, unchanged).
- Exactly ONE challenger configuration (no bucket-cap, decay, or
  mixing-parameter search).

## Population (frozen)

The 4,823 eligible development starts / their realized strikeout counts K
per start from existing frozen sources; identical keys for both arms.
Development = block_2024H2 + block_2025H1. confirm_2025H2 protected
(never fit, scored, or reported). The 43 dev abstentions and 16
confirmation-block abstentions are itemized in the abstention record and
PROMINENTLY reported; the full-run total (59) is never treated as a
development count.

## Primary and supporting metrics

- PRIMARY: count-RPS (registered vocabulary) — challenger vs baseline,
  paired by start on the identical eligible keys.
- SUPPORTING (descriptive, never gated): milestone Briers (the registered
  milestones, e.g., K>=5 / K>=7); per-block deltas descriptive.
- Inference: paired slate-date bootstrap n=2000, seed 20261001,
  block-stratified, null-centered with the (B+1) finite-resample
  correction, Holm m=1 (family of one) — via the registered harness
  primitives through the established import path.

## Provenance and failure conditions

- Mandatory validated provenance receipt (same sections as the
  batter-history diagnostic: consumed inputs = pa_table + preserved
  ledger + BF workload + realized-count source; context identities =
  checkpoint/lineups/freeze; code/config hashes; per-arm output
  inventories; abstention record reference).
- Write-once output directory; collision refuses.
- Any frozen-key, abstention, BF-shape, or eligibility mismatch stops all
  downstream use. No population-policy change.

## Data boundary

Existing 2022-forward inputs. No historical extension, no real-outcome
access before execution authorization, no model-family change (the
aggregation rule is the ONLY change).
