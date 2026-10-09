# History contract - canonized one-prior-season rule (2026-10-08)

> Status: CANONICAL (owner-ordered reconciliation; read-only evidence
> from run manifests; no rerun of the passed 2024 transfer).

## 1. Reconciliation result (read-only, manifest evidence)

| Forecast season | Hazard pool as executed | Evidence |
| --- | --- | --- |
| 2023 frozen I3b | **2023-to-date ONLY** (Apr 414 / Jul 2,460 / Aug 3,194 / Sep 4,016); 2022 entered via appearance-history features + constant fallback, never as hazard-fit rows | `workload-training-policy-20261007_090000` manifest train_B counts |
| 2024 transfer (as executed) | **2023-full + 2024-to-date** (after the documented fail-loud amendment; intended 2022+2023+2024 was NOT executed) | `transfer-2024-i3b-20261008_224538` manifest |

The two canonical runs therefore did NOT use equivalent evidence
windows: 2023 fit its April hazard on 414 same-season rows; the 2024
run fit its April hazard on ~2,900 prior-season + season-date rows.
The 2024 result is the STRONGER warm-up of the two.

## 2. Canonized rule (all future runs, both components)

> **For forecast season Y: use full season Y-1 plus strictly prior
> observations of season Y.**

- Hazard-fit rows: full Y-1 + strictly-prior-Y first-pitcher rows.
- Rate pool (pitcher/batter/league, w=150 shrinkage): same Y-1 +
  prior-Y PAs.
- Appearance-history pool (BF features): same.
- Card pool: season Y only (unchanged).
- All cutoffs remain strictly pre-origin; no future rows ever enter.

This removes accidental dependence on missing Y-2 feature history and
gives every forecast season the same warm-up structure.

## 3. Status of existing results under the canonized rule

- **2023 frozen I3b artifacts (train_B 414-pool):** remain the
  recorded developmental benchmark under the OLDER season-to-date
  rule. NOT rerun.
- **2024 transfer (PASSED):** stands as recorded - "all scoring
  criteria passed with one documented history-pool deviation." Its
  hazard pool matches the canonized rule; its rate and
  appearance-history pools included 2022 (richer than canonical) -
  a favorable deviation, disclosed in the freeze document, not rerun
  (no rerun merely to improve a label).
- **September challenger (next lane):** developed and confirmed
  under the canonized rule on both seasons; its within-run reference
  arm shares the challenger's canonical pool so the comparison is
  internally paired.
