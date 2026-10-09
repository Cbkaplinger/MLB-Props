# September hazard challenger - FROZEN design (2026-10-08)

> Status: FROZEN before any scoring. One mechanism, one development
> season (2023), one confirmation season (2024, **prior endpoint
> awareness** - September 2024 bias was already inspected and
> motivated this challenger; 2024 is confirmation, NOT a pristine
> holdout). History contract: canonized one-prior-season rule
> (`history-contract-2026-10-08.md`).

## 1. Mechanism (frozen; single parameter)

Modify ONLY the BF stopping hazard:

    logit h_t = logit h_{0,t} + beta_Sep * I(September)

- I(September) = 1 if the START's game_date is in September of its
  season (pregame-known: the scheduled month). Same flag for
  training and evaluation rows.
- beta_Sep is ESTIMATED, not tuned: the hazard is refit per origin
  with I(September) appended as an 11th feature column to
  CHALLENGER_FEATURES inside the unchanged `bf_distribution.fit_hazard`
  (L2 C=1.0, identical risk-set construction and preprocessing).
- beta_Sep uses strictly pre-origin training data only. Under the
  canonized history rule the Y-1 season supplies September evidence
  to every origin (including April).
- **p\* is HELD FIXED per row (canonical reference p\*)**: the
  challenger changes only the BF PMF; count PMFs = combine_count(
  ext60_challenger, p*_reference). The scientific claim stays narrow:
  September changes workload, not pitcher-batter K probability.
- Everything else frozen: card pool = season Y only, B1/B2 policy,
  rate pool = Y-1 + prior-Y, rates and shrinkage untouched.

## 2. History pools (canonized rule)

| Pool | Season Y development (2023) | Season Y confirmation (2024) |
| --- | --- | --- |
| Hazard-fit rows | 2022-full + 2023-to-origin | 2023-full + 2024-to-origin |
| Rates | 2022 + 2023-to-origin | 2023 + 2024-to-origin |
| Appearance histories | 2022 + 2023 | 2023 + 2024 |
| Cards | 2023 season | 2024 season |

2022 hazard-fit rows whose opponent team has no strictly-prior 2022
game are excluded (the frozen prior-year team-rate chain has no 2021
source and exhausts fail-loud); the exclusion count is reported.
Within-run reference arm shares the challenger's pools exactly
(same rows, same features minus the September flag), so every gate
is an internally paired comparison.

## 3. Gates (frozen ex ante; evaluated on the CONFIRMATION season)

### Primary gate (September eval rows)

1. BF absolute bias improves by >= 0.15 (reference minus challenger,
   |bias_ref| - |bias_chal| >= 0.15); sign flips to negative do NOT
   count as improvement unless |bias| shrinks accordingly.
2. K absolute bias worsens by <= 0.02.
3. Paired count-RPS (challenger - reference), date-clustered
   bootstrap 2,000 / seed 20261001: FAIL if the CI is entirely above
   +0.0005; otherwise pass (CI entirely below 0 = preferred).
4. September PIT: tail bins (first/last) <= 1.5x expected in BOTH
   arms (no new imbalance).
5. P(N<9) absolute calibration error improves or worsens by
   < 0.002 (neutral-or-better).

### Safety gate (full season, all eval rows)

1. Paired count-RPS (challenger - reference) CI entirely below
   -0.0005 = FAIL (material full-season degradation).
2. BF MAE worsens by > 0.02 or K MAE worsens by > 0.02 = FAIL.
3. Milestone Brier (ge6/ge8/ge10/ge12) increase > 0.0002 = FAIL.
4. Log-score floor rows increase = FAIL.
5. April BF bias worsens by > 0.10 = FAIL (compensation check).

### Decision rule

Promote the September mechanism into the canonical recipe ONLY if
BOTH gates pass on the 2024 confirmation. Otherwise: keep the frozen
I3b recipe unchanged, record the dev + confirmation numbers, and
close the lane (no interval fishing, no second mechanism, no
threshold adjustment after seeing 2024).

## 4. Reporting

All metrics via the existing conventions (bias = predicted - actual;
summed-RPS; floor accounting; seeded discrete PIT). Per-origin and
September/full-season splits reported separately. The dev-season
(2023) numbers are recorded in the run manifest for transparency but
do NOT alter the frozen thresholds.
