# Debut-pitcher reconciliation - pregame-pa-ext-v2 scoring acceptance failure (2026-10-20)

Point-in-time reconciliation report. The authorized scoring run of 2026-10-20
executed ONCE and FAILED its acceptance gate (531 cold-start PA exclusions, 59
cold-slot starts vs required zero). The output parquet is PRESERVED UNACCEPTED;
all downstream use is stopped. This report reconciles those 59 starts against
existing artifacts. Read-only; no rerun, no reconstruction, no fill, no
outcome evaluation.

## 1. Failed acceptance receipt and artifact identities

- Merged implementation: PR #21 (merge ccd0148798e75cb93b6eb9ce2f319c37ebc8bf7b;
  reviewed head 1b3bfd311421155a93895765c87b930ccc01c4a1; paext lane byte-identical
  1b3bfd3..main at run time).
- Command: run_real(tracking_uri=sqlite:///<research mlflow.db>,
  experiment=pa-k-probability-v1, pipeline_id=paext-v2-20261020T141540Z).
- Output (UNACCEPTED, write-once, untouched):
  MLB-Props-Research/pregame-pa-ext-v2/outputs/projected_pa_probs_v1.parquet
  - 64,746 rows = 7,194 starts x 9 slots; 64,215 scored (finite, in [0,1]);
    531 rows cold_start_no_prior (null probs + exclusion_reason);
    PMF arms present on 7,135 starts only (24-bucket, normalized).
- Checkpoint artifact (unchanged): checkpoints/h3_raw_checkpoint.json;
  canonical payload sha256 176fb18bc3b06328f4425175907506ea0dbcea45727e8879ff06249a751decfe
  (registered pin, enforced); raw-file sha256 d266a1cd108633012e2bdec8c93dd467759fd966191c71aed9d790b74d1c68c6.
- BF PMF artifact (unchanged): bf-workload-v1/data/bf_forecasts.parquet,
  sha256 c9c2762fb2c1c239e5645c49fa92eda50bd652d26e54755ac8bf0c28fa968679, 14,574 rows.
- Lineup artifact (unchanged): pregame-state-v1/data/projected_lineups_variant_v2.parquet,
  sha256 b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b, 7,194 starts.
- MLflow scoring run: 2393940213154b718124b0b323c62ff9 (experiment pa-k-probability-v1,
  phase=scoring, pipeline_id=paext-v2-20261020T141540Z), status VERIFIED - the run is
  tracked as EVIDENCE of the unaccepted execution.
- Acceptance result: FAILED on zero-exclusion criteria (531/59/7,135-of-7,194).

## 2. The 59 starts (reconciliation table)

Start key = (game_pk, side, game_date). First appearance = earliest frozen
PA-table row where the player is the recorded pitcher. Cold-start reason is the
registered adapter classification (pitcher prior_n == 0, strictly prior). BF
availability state from the bf artifact's own prior_n (career_debut_bf = 0,
insufficient_history_bf = 1..9, own_distribution_bf = >=10). Source-history
coverage = the frozen PA table spans 2022-04-07..2025-09-28 (four seasons).

| # | game_pk | side | game_date | pitcher | first pitcher-row | pitcher rows in table | cold-start reason | BF availability state | source-history coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 746128 | Bot | 2024-07-03 | 691441 | 2024-07-03 | 41 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 2 | 746122 | Top | 2024-07-07 | 680736 | 2024-07-07 | 434 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 3 | 746530 | Top | 2024-07-07 | 685299 | 2024-07-07 | 497 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 4 | 747181 | Top | 2024-07-08 | 700270 | 2024-07-08 | 134 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 5 | 746204 | Top | 2024-07-11 | 686799 | 2024-07-11 | 778 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 6 | 746124 | Top | 2024-07-22 | 689981 | 2024-07-22 | 81 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 7 | 746035 | Bot | 2024-07-24 | 694646 | 2024-07-24 | 69 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 8 | 745550 | Bot | 2024-07-28 | 676282 | 2024-07-28 | 564 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 9 | 745546 | Bot | 2024-07-30 | 701542 | 2024-07-30 | 821 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 10 | 745148 | Top | 2024-07-31 | 700241 | 2024-07-31 | 486 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 11 | 745628 | Bot | 2024-08-05 | 681066 | 2024-08-05 | 87 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 12 | 745867 | Top | 2024-08-13 | 805673 | 2024-08-13 | 531 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 13 | 744898 | Bot | 2024-08-19 | 687924 | 2024-08-19 | 140 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 14 | 746753 | Bot | 2024-08-26 | 680744 | 2024-08-26 | 101 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 15 | 746184 | Top | 2024-08-30 | 691951 | 2024-08-30 | 140 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 16 | 746665 | Top | 2024-08-30 | 695076 | 2024-08-30 | 128 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 17 | 746183 | Top | 2024-09-01 | 702674 | 2024-09-01 | 193 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 18 | 746017 | Bot | 2024-09-08 | 686751 | 2024-09-08 | 72 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 19 | 746910 | Top | 2024-09-08 | 690916 | 2024-09-08 | 280 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 20 | 745208 | Bot | 2024-09-12 | 677958 | 2024-09-12 | 342 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 21 | 778564 | Bot | 2025-03-19 | 808963 | 2025-03-19 | 161 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 22 | 778525 | Bot | 2025-03-30 | 608372 | 2025-03-30 | 675 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 23 | 778499 | Top | 2025-03-31 | 606996 | 2025-03-31 | 179 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 24 | 778490 | Top | 2025-04-01 | 681343 | 2025-04-01 | 616 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 25 | 778493 | Bot | 2025-04-01 | 802419 | 2025-04-01 | 50 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 26 | 778423 | Top | 2025-04-06 | 801403 | 2025-04-06 | 441 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 27 | 778432 | Top | 2025-04-06 | 690928 | 2025-04-06 | 256 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 28 | 778262 | Top | 2025-04-19 | 687064 | 2025-04-19 | 256 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 29 | 778239 | Top | 2025-04-20 | 701656 | 2025-04-20 | 99 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 30 | 778169 | Top | 2025-04-26 | 680951 | 2025-04-26 | 23 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 31 | 778136 | Top | 2025-04-27 | 688138 | 2025-04-27 | 350 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 32 | 778110 | Top | 2025-04-30 | 805123 | 2025-04-30 | 125 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 33 | 778113 | Bot | 2025-04-30 | 702070 | 2025-04-30 | 556 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 34 | 778119 | Top | 2025-04-30 | 695534 | 2025-04-30 | 40 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 35 | 778091 | Bot | 2025-05-02 | 680684 | 2025-05-02 | 139 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 36 | 778053 | Bot | 2025-05-04 | 694918 | 2025-05-04 | 78 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 37 | 777920 | Top | 2025-05-14 | 676467 | 2025-05-14 | 379 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 38 | 777897 | Bot | 2025-05-16 | 687223 | 2025-05-16 | 175 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 39 | 777880 | Top | 2025-05-18 | 690953 | 2025-05-18 | 174 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 40 | 777532 | Top | 2025-06-12 | 694819 | 2025-06-12 | 272 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 41 | 777439 | Bot | 2025-06-20 | 800311 | 2025-06-20 | 69 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 42 | 777385 | Top | 2025-06-24 | 695505 | 2025-06-24 | 188 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 43 | 777351 | Top | 2025-06-26 | 608650 | 2025-06-26 | 200 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 44 | 777213 | Top | 2025-07-06 | 829272 | 2025-07-06 | 173 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start (also has batter rows from 2025-08-27) |
| 45 | 777184 | Top | 2025-07-09 | 693645 | 2025-07-09 | 304 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 46 | 777029 | Bot | 2025-07-23 | 675512 | 2025-07-23 | 180 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 47 | 776964 | Top | 2025-07-28 | 687931 | 2025-07-28 | 102 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 48 | 776954 | Top | 2025-07-29 | 701487 | 2025-07-29 | 133 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 49 | 776726 | Top | 2025-08-16 | 690997 | 2025-08-16 | 188 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 50 | 776658 | Bot | 2025-08-20 | 800048 | 2025-08-20 | 165 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 51 | 776610 | Bot | 2025-08-24 | 685326 | 2025-08-24 | 126 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 52 | 776548 | Top | 2025-08-29 | 804636 | 2025-08-29 | 87 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 53 | 776549 | Top | 2025-08-29 | 801139 | 2025-08-29 | 74 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 54 | 776524 | Top | 2025-08-30 | 686930 | 2025-08-30 | 104 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 55 | 776498 | Top | 2025-09-01 | 674841 | 2025-09-01 | 98 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 56 | 776488 | Bot | 2025-09-02 | 815083 | 2025-09-02 | 107 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 57 | 776429 | Bot | 2025-09-07 | 687075 | 2025-09-07 | 84 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 58 | 776396 | Bot | 2025-09-09 | 813349 | 2025-09-09 | 79 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |
| 59 | 776316 | Bot | 2025-09-15 | 702056 | 2025-09-15 | 62 | cold_start_no_prior (pitcher prior_n==0) | career_debut_bf (bf prior_n=0) | 0 rows before start |

## 3. Actual MLB career debuts vs first-appearance-in-table

- ALL 59: first pitcher-row is ON or AFTER the scored start date, inside the
  registered window, with ZERO earlier pitcher rows in a table that covers four
  full seasons (2022-04-07..2025-09-28, 731,347 rows).
- 0 of 59 have any EARLIER batter rows (no position-player-conversion case).
- Conclusion: these are ACTUAL MLB CAREER DEBUTS (as pitchers) within the frozen
  lineage's coverage - not merely first appearances in a truncated table. The
  only caveat is definitional: 'career debut' here means first MLB pitching
  appearance captured by the frozen 2022-2025 Savant lineage; an appearance
  before 2022-04-07 would be outside the table, which is impossible for an
  in-window debut preceded by zero captured rows across 2022-2023.

## 4. Reconciling the 59 (PA-history) vs the 169 (BF)

Definitions, matched from the executed code:
- PA/adapter cold: prior_n_pitcher == 0 in the frozen pa_table (2022-04-07+
  lineage; adapter.py cold_start = (prior_n_pitcher==0) | (prior_n_batter==0)).
- BF cold: cold_start = int(prior_n == 0) where prior_n counts the pitcher's
  PRIOR OUTINGS accumulated within the BF build's own pool window, which starts
  at the bf artifact's first date 2023-03-30 (build_bf_forecasts.py:162;
  DIAGNOSTIC_DEFINITIONS.md: '169 cold starts in the assessment window').

Key-level reconciliation over the registered 7,194 starts:
- BF cold_start==1 in-window: 169. PA-cold: 59.
- Intersection (both definitions): 59 - the 59 are a STRICT SUBSET of the 169
  (pa-cold-only = 0). On every one of the 59 both definitions agree
  (bf prior_n == 0, cold_start == 1).
- BF-cold only: 110 starts whose pitchers HAVE prior PA-table pitcher rows
  (first pitcher-row range 2022-04-07..2025-09-04) but zero prior outings
  within the BF pool window: their prior appearances predate 2023-03-30 (the
  bf accumulation start) - e.g. a 2022 debutant returning after a long absence.
  The PA table (2022-04-07+) sees that history; the BF pools do not.

So: 169 = 59 true in-window career debuts + 110 BF-window-accumulation colds.
The counts are not expected to be equal because the two prior-history spans
differ (2022-04-07 vs 2023-03-30); the definitions agree exactly where they
overlap.

## 5. Frozen specification text governing pitcher cold starts

REGISTERED RULE (spec level, PROJECTED_LINEUP_SPEC.md section 3 annotation,
2026-10-19, quoted verbatim):

> the paext-v2 adapter path (research/offseason_2026/pregame_pa_ext/) currently
> implements cold-start handling as EXCLUSION (provisional approach): a slot
> with no entity history gets a null PA probability, an explicit
> exclusion_reason, and is excluded from scoring. This does NOT supersede this
> section - the league-rate fill below remains the registered candidate
> fallback for this lane, and the choice between exclusion and league-rate
> fallback is BLOCKED awaiting an explicit owner decision.

REGISTERED RULE (lane doc, COUNT_EVAL_COMMANDS.md, quoted verbatim):

> Cold-start handling: EXCLUSION implemented as a provisional approach; owner
> decision pending on fallback vs exclusion. A slot whose pitcher or batter has
> no PA-table history carries source_type = cold_start_no_prior, a null PA
> probability, and an explicit exclusion_reason; it is EXCLUDED from scoring.

IMPLEMENTATION BEHAVIOR (adapter.py, reviewed code - distinct from the rule):
- cold_start flag = (prior_n_pitcher == 0) | (prior_n_batter == 0) per PA row,
  computed strictly-prior; source_type = cold_start_no_prior on such rows.
- Those PA rows are EXCLUDED (null probability + exclusion_reason) and their
  starts are excluded from the count-PMF arms (n_cold > 0 -> no PMF), with
  counts recorded in the run summary (n_pa_rows_excluded_cold_start,
  n_starts_pmf_excluded_cold_slot). No stop is raised; no league-rate fill is
  applied anywhere; no silent acceptance (all counts surfaced).

DISTINCTION: the registered rule is exclusion-as-PROVISIONAL-approach with the
owner decision explicitly pending; the implementation is the mechanical
realization of that provisional rule (exclude + record), which is what the
2026-10-20 run did. Neither the rule nor the run constitutes population-policy
approval. The 59 debut starts make the dormant policy question CONCRETE: an
owner decision is required before any accepted run can exist.

## 6. State

- Output: UNACCEPTED, preserved untouched. Downstream use: stopped.
- No reconstruction, prediction rerun, fallback implementation, or outcome
  evaluation was performed for this report (existing artifacts only).
- Open owner decisions: (1) debut-pitcher handling for the 59 starts; (2) any
  accepted re-run after that decision (write-once destination decision needed).
