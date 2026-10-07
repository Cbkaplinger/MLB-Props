# BF-distribution readiness clarifications (pre-score, 2026-10-06)

Supplements `bf-distribution-design-prereg.md` without altering it.
Anything here that conflicted with the frozen design would block
scoring instead; nothing below does.

## Support and overflow (exact)

- Categories 0..36 map to BF 1..37? No: index 0 = BF 1, ...,
  index 35 = BF 36, index 36 = overflow bucket N >= 37.
- "37+ BF" is a category, not the numeric value 37. No realized
  observation is ever assigned BF = 37.
- RPS grid: t = 0..36 over categories (37 grid points);
  CDF(t) = P(category <= t); hit indicator uses the realized
  category (>=37 maps to 37). RPS range is [0, 37].
- NLL: -log(max(mass, 1e-12)) with a clipped counter per batch.
- Short-outing event: P(BF < 9) = PMF categories 0..7.
- Intervals: central equal-tail on categories; the hi endpoint may
  be the overflow category (reported as "37+"); width is counted in
  categories, not batters. A width spanning overflow is not a
  finite-BF width claim.
- Distribution mean (reference only): categorical mean with the
  overflow bucket scored at 37, labeled explicitly as a
  lower-bound-capped mean. Never compared to Ridge point MAE as
  though exact. Median is exact (no convention needed).

## Cold start and fallback mapping

- Distribution-level median imputation trains on training risk-set
  rows only; the existing 2022-constant fallback enters through
  spine features exactly as in the point lane (no separate
  fallback path, no new policy).
- All-null-history rows resolve through the same flagged fallback;
  they are counted, never special-cased away.

## Comparators and baselines

- Train-only empirical add-one baseline over the 37 categories,
  fitted per origin on that origin's training partition.
- Preserved Ridge point forecasts appear as point-performance
  references (MAE/RMSE/bias from completed runs, labeled with
  their run identities). No refitting here.
- Beating the empirical baseline does not by itself show the
  conditional hazard beats uncertainty attached to Ridge; that
  comparison is explicitly deferred, not claimed.

## What this diagnostic does not do

- No within-overflow distribution is invented.
- No post-score calibration (Platt/temperature) is applied.
- No 2024+ data, no feature search, no architecture race.
