# RESULT RECORD ADDENDUM — morning vs near-close (frozen protocol run
# 2026-10-22 at b2a4298; STATUS 11)

## Two-row table (common verified cohort, each market at its own line)

| market | n | model LL | market LL | delta (model − market) | paired 95% CI |
| --- | --- | --- | --- | --- | --- |
| morning (T-5h vendor clock) | 2,109 | 0.7108 | 0.6883 | **+0.0225** | [+0.0141, +0.0307] |
| near-close (T-5m vendor clock) | 2,109 | 0.7120 | 0.6890 | **+0.0229** | [+0.0141, +0.0321] |

Brier: morning model 0.2578 vs market 0.2476; near-close model 0.2583
vs market 0.2479.

## Reading

The close and the morning quote carry nearly identical information
about these starts: the model loses to BOTH by ~0.023 log loss, and
the two deficits are statistically indistinguishable from each other.
No originator-style "value before the market moves" signal exists in
this frozen model on this cohort. The morning benchmark does not
create an opening the close denies.

## Complete-cohort near-close baseline (SEPARATE, n=4,336)

close 0.6859 | model 0.7162 | delta +0.0303. Reported separately per
the standing rule: it mixes 2024 prior-evening lines with 2025H1 true
closes and is not the 2025H1 close-only effect (which is +0.0234 on
n=2,154 / +0.0229 on this 2,109 common cohort).

## Provenance

- Cohort: morning_close_cohort_v1 (2,109 starts, key hash
  aadc2d2a3caa104fd6629c7b7057d8de422d4b0aa6afe51c3de75d404495d5aa),
  published before this run; hash re-verified at run time.
- Quote timestamps: preserved per scored row in
  `morning_vs_close_v1_attempt11.parquet` (per-start line/price
  provenance for both markets); quote-selection audit linkage in
  `quote_selection_audit.parquet`.
- Availability: model inputs are strictly prior-game-date; the morning
  snapshot's ~T-5h lead is downstream of every consumed input —
  availability holds (the open18 caveat does not apply here).
- Artifact hashes: metrics.json `59b5b6fb6d83c041`, parquet
  `1e22c5d6d9106855`. Code SHA: b2a4298.
