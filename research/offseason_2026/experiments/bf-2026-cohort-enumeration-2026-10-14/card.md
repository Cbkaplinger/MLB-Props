# Card: bf-2026-cohort-enumeration-2026-10-14

**Bounded preparation - eligibility metadata only. NO outcome reads, NO
scoring, NO fitting.**

## Question

Enumerate the 2026 registered cohorts (PREREGISTRATION_2026.md section
1.2) over the full regular season using the frozen builders, and report
row counts, exclusions, pilot overlap, prior-exposure groups, and
per-row pregame input/cutoff availability.

## Method

`research/offseason_2026/run_bf_2026_cohort_enumeration.py`:

- first-pitcher-of-record starts (game_pk, side) from the completed-PA
  frame (2026 Savant regular parquet);
- projected-batter-state coverage via the ACCEPTED unique-batter v2
  recipe (lake `build_projected_lineups_variant_v2.assign_unique`
  imported unchanged; N=7 prior team-games; nine-distinct requirement);
- BF PMF construction inputs via the chronological strictly-prior pool
  (bf-workload-v1 BASE: own counts when prior_n >= 10 else league),
  2023-01-01 onward, seeded with all 2023-2025 exposures before the
  first 2026 date, updated only after each slate date is enumerated;
- 2022 warm-up: PA feature state pools 2022+ rows as strictly-prior
  state (never fitted, never scored);
- captured cohort + pregame cutoffs from the 6 capture files
  (`data/processed/daily_lineups_*.parquet`).

**Outcome boundary:** the `events` column is used ONLY for
completed-PA determination and `truncated_pa` exclusion (the frozen
builders' eligibility machinery). No label column is created, no K
events are read, no metrics are computed, nothing is scored. Realized
BF is an exposure count (completed PAs per pitcher-game), not an
outcome label.

## Results (report.json)

- Season window: 2026-03-25 .. 2026-09-27 (184 slate dates).
- Full-season cohort: 4,858 first-pitcher-of-record starts; 0 excluded
  (0 nine-distinct failures, 0 unknown teams, 0 missing BF inputs) ->
  4,858 eligible rows (100%).
- BF inputs: 4,858/4,858 available; 4,465 own-dist (prior_n >= 10);
  59 cold starts; league history available on all rows.
- PA state (2022 warm-up): 4,858/4,858 available.
- Pregame cutoffs: 134/4,858 eligible rows have a captured pregame
  cutoff (2.8%); 4,724 have NONE (the intermittent capture covers only
  6 fetch dates).
- Captured cohort: 142 captured team-games, 8 null-probable excluded,
  134 eligible - EXACTLY reproduces the seal prep counts.
- Pilot overlap: seal 134 keys == pilot 134 keys (0 symmetric
  difference); all 134 present in the full-season enumeration; the 11
  usable-B members come from the PILOT package (not the seal
  re-stamped flags).
- Prior-exposure groups: 134 pilot rows (outcomes already observed);
  142 captured team-games (pilot replay inputs); 148 rows on the 6
  capture slate dates (2026-07-28/30, 08-07, 08-10, 08-20, 08-21);
  p1-harness 2026 contact = definition-level reservation only (0 rows
  dated 2026 in eval_predictions, verified); 4,708 rows outside all
  recorded contact groups.

## Files

- `report.json` - full machine-readable report
- `cohort_rows_metadata.parquet` - one metadata row per enumerated
  2026 start (game_pk, side, pitcher, game_date, opp_team, coverage +
  BF-input + cutoff-availability + pilot-membership flags)

## Deviations

None from the bounded-prep scope. Two internal fixes during the build
(before any committed output was read): pools initially not seeded with
2023-2025 BF history (fixed), and capture dates initially derived from
UTC `fetched_at` instead of the 6 capture file names (fixed).
