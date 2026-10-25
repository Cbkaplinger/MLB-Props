# C-B1 IMPLEMENTATION SCOPE (one page) — exposure-profile heterogeneity
# (pregame-pa-ext-v2 lane, 2026-10-22; implements
#  card_workload_dependence_B_2026-10-20.md candidate C-B1)

## What is built

Module `research/offseason_2026/pregame_pa_ext/exposure_profile.py`:

1. **Band assignment.** Every realized PA in the frozen training lineage
   carries its BF index within its start (order of PAs per
   (game_pk, side, pitcher) by at_bat_number). BF index j -> band:
   1-9, 10-18, 19-27, 28-36, 37+ (five registered bands).
2. **Per-band rate estimation with shrinkage.** Per dev block
   (block_2024H2, block_2025H1), the band's K rate is the shrunk mean:
   q_band = (w * pbar_band_prior + n_band * k_band) / (w + n_band),
   with the pre-registered shrinkage weight w = 150 PAs (w150
   convention) and pbar_band_prior = the FROZEN cycled prefix-mean
   band rate computed on the same lineage rows (the frozen profile).
   K rate = P(class 0) using the M0 v2 four-class taxonomy labels
   (strikeout class) - the M0 receipt's taxonomy, NOT a relabel.
3. **Per-start profile construction.** For each eligible start, the
   60-slot exposure profile q(j) is the piecewise-constant band rate
   (same band rates for every start of the block - a block-level
   profile, not pitcher-specific; pitcher-specific heterogeneity is
   NOT claimed by C-B1).
4. **Exact PB aggregation.** P(K=k) = sum_n P(N=n) * PB(k; q_1..q_n)
   via the MERGED Question A aggregator (count_aggregation_exact),
   mixed over the REGISTERED BF PMF (bf_pmf_from_37, cap 60, tail at
   k=23) - the frozen mixture machinery, imported and called, never
   modified.
5. **Paired evaluation.** Count-RPS (registered vocabulary) vs the
   frozen baseline arm on the identical 4,823 eligible dev starts
   (preserved ledger), 43 dev abstentions excluded, slate-date
   bootstrap n=2000 seed 20261001 null-centered, Holm m=1.

## What changes vs the frozen baseline

ONLY the per-PA probability sequence generator: frozen cycled prefix
means -> estimated exposure profile. N unchanged; lineup construction
unchanged; eligibility unchanged; confirmation untouched.

## Stop conditions (pre-registered, from the card)

(a) ESTIMATION STOP: every band within 0.005 of the frozen profile
    -> declare no exposure signal WITHOUT evaluation.
(b) EVALUATION STOP: count-RPS delta CI includes zero or favors the
    baseline -> close C-B1.
(c) Any integrity/receipt failure -> stop.

## Synthetic tests required (before any real use)

- Band-profile recoverability (ground-truth profile recovered within
  tolerance).
- Shrinkage-to-frozen behavior at sparse bands.
- PMF normalization + tail-bucket correctness.
- Strictly-prior construction (no same-day/future rows).
- Block isolation (confirm untouched).
- Receipt completeness (write-once, initial-first, chained).

## Execution contract

Real-data execution gated on --i-accept-outcome-evaluation + explicit
owner authorization (same pattern as M0 v2). The run consumes the
frozen training lineage, the preserved ledger, the registered BF PMF,
and the registered realized counts; receipts write-once; failure
records preserved.

## Sequencing

M0 v2 executed 2026-10-22 (both endpoints PASS). C-B1 build starts
now: module + synthetic tests first; no real-data run until
authorized.
