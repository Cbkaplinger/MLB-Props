# Batter-history challenger card v2 - pregame-pa-ext-v2 (2026-10-20)

REVISED pre-registration draft (v2). Supersedes v1 in full; v1 was NOT ready
for fitting (five review issues, resolved below). NO fitting, NO prediction
regeneration, NO historical backfill, NO confirmation-period performance
inspection has occurred. The preserved scoring run remains UNACCEPTED and is
never relabeled. Approval of this card approves SPECIFICATION work only.

## 0. Issue-resolution register (v1 -> v2)

| # | v1 issue | v2 resolution |
| --- | --- | --- |
| 1 | Dev population covered all three blocks incl. confirmation | Development = block_2024H2 + block_2025H1 eligible keys ONLY (exact counts below); confirm_2025H2 fully out of development (no fit/score/tune/report) |
| 2 | Preserved rows are projected slots, not observed PAs | Evaluation unit = OBSERVED PAs via identity join on (game_pk, pitcher, batter, game_date) to the frozen pa_table; unobserved projected matchups are DROPPED with explicit counts - never assigned an invented outcome |
| 3 | Changed features fed to unchanged coefficients would test the wrong question | The challenger REBUILDS its features for every historical training row (forecast-date-anchored as-of construction) and REFITS the same model family per dev block; frozen coefficients are never fed challenger features |
| 4 | Normalized EW rate loses no confidence when its last observation ages | The anchor's effective sample size is its FORECAST-DATE-ANCHORED weighted denominator (half-life 90d): old mass decays toward league explicitly; the decay rule is declared, not implicit |
| 5 | Brier primary + 3 selectable configs made Holm m=1 unjustified | ONE primary challenger (R=60d, m=30); LOG LOSS primary; Brier + calibration = pre-declared supporting/sensitivity only (not selectable candidates); single primary contrast -> Holm m=1 is the family of one, no correction needed |

## 1. Two isolated experiments (never both at once)

| Question | Experiment |
| --- | --- |
| Does better WEIGHTING of existing history help? | Same 2022-04-07..2025-09-28 source; new batter-history construction (this card) |
| Does EXTENDING history help? | Same construction as whichever arm is registered; earlier compatible PA history (separate registered improvement; NOT part of this card) |

## 2. Development population (exact, computed from the preserved output ledger + frozen pa_table)

Eligible = starts with zero cold-slot exclusions in the preserved run (their
64,215 scored slots). Per block:

| block | starts total | eligible starts | abstaining (59 list) | eligible PA rows |
| --- | --- | --- | --- | --- |
| block_2024H2 | 2,334 | 2,314 | 20 | 20,826 |
| block_2025H1 | 2,532 | 2,509 | 23 | 22,581 |
| DEVELOPMENT TOTAL | 4,866 | 4,823 | 43 | 43,407 |
| confirm_2025H2 (PROTECTED) | 2,328 | 2,312 | 16 | 20,808 |

Development keys = eligible (game_pk, side) in block_2024H2 + block_2025H1 only.
The confirm block's counts are recorded for completeness only; it is not used
for fitting, tuning, selection, or reported performance.

## 3. Observed-PA evaluation table and joins (no invented outcomes)

- Evaluation rows = realized PAs from the FROZEN pa_table (game_pk, pitcher,
  batter, game_date, y=realized K) joined to eligible projected matchup slots
  on the IDENTITY keys (game_pk, pitcher, batter, game_date): the observed
  instances of the projected matchup.
- A projected slot maps to ZERO OR MORE observed PAs (a batter can face the
  pitcher several times); every observed PA is one evaluation row carrying the
  slot's projected probability.
- Projected slots with NO observed instance (batter did not face that pitcher
  in that game) are DROPPED from evaluation with explicit counts - never given
  an invented outcome:

| block | projected slots with >=1 observed PA | observed evaluation rows | projected slots with NO observed PA (dropped) |
| --- | --- | --- | --- |
| block_2024H2 | (dev, see join) | 39,252 | 5,039 |
| block_2025H1 | (dev, see join) | 43,565 | 5,275 |
| DEVELOPMENT | - | 82,817 | 10,314 |
| confirm_2025H2 (protected, not evaluated) | - | 39,156 | 4,940 |

- Baseline per evaluation row: the frozen checkpoint's p_h3_raw for that slot
  (from the preserved run's valid predictions). Challenger per evaluation row:
  its own probability. Both arms evaluated on the IDENTICAL evaluation rows.

## 4. Challenger design (one primary configuration)

- Feature change (batter side ONLY): replace p_batter_prior_w150 + ew_batter
  with two new features: p_batt_recent + p_batt_anchor. Pitcher features,
  lg_rate, counts, cold_start, ew_pitcher unchanged (7+1 = 8 features total).
- History split at forecast date t: rows in (t-R, t) = RECENT (R = 60 days);
  rows before t-R = ANCHOR pool. Strictly prior; disjoint by construction -
  no appearance enters both components (no double counting).
- Anchor (age-aware confidence): weights w_i = 2^(-(t - d_i)/90) anchored at
  the FORECAST date; weighted counts ew_k_old/ew_den_old; the weighted
  denominator IS the declared effective sample size (half-life 90d = the decay
  rule): 2022-07 mass at a 2025-07 start carries weight ~2^(-8*365/90) = ~0 -
  an old season cannot impersonate current confidence. Anchor rate shrunk to
  the as-of league rate: p_anchor = (ew_k_old + 150*lg)/(ew_den_old + 150)
  (same w150 weight and target as the frozen recipe). Empty anchor ->
  p_anchor = lg (INTERNAL FEATURE DEFAULT, see section 6).
- Recent component: raw k_win / n_win over window rows.
- Update rule: p_batt_new = (k_win + m * p_anchor) / (n_win + m), m = 30
  pseudo-PA. Newcomer-adjacent batters (small n_win, small anchor mass)
  automatically approach the league rate as their evidence shrinks - the
  estimator degrades gracefully toward lg, BY CONSTRUCTION of the weighted
  denominators, with all components recorded per row.
- Reused machinery: entity_daily_state (extended with forecast-date-anchored
  weighting in the diagnostic script); no new rolling framework.
- PRIMARY challenger config: R=60d, m=30. The v1 alternates (m=15; R=120d) are
  DROPPED - no window/decay/pseudo-count search. Any second configuration
  requires a NEW pre-registered reason.

## 5. Training/inference consistency

- The challenger's features are REBUILT for every historical training row as of
  that row's own date (same asof state machinery; strictly prior).
- Per dev block: fit StandardScaler + LogisticRegression(C=1.0, max_iter=1000)
  on the rebuilt features over the SAME training rows as the frozen block
  model (2023-01-01..block cal_first; scaler on train only; no early stopping,
  no calibration stage). Training rows use the same observed-PA label table.
- The frozen checkpoint coefficients are NEVER applied to challenger features,
  and challenger coefficients are never applied outside their block.

## 6. Newcomer contradiction resolved: feature default vs scoring permission

- INTERNAL FEATURE DEFAULT: when an entity has no (or negligible) pre-window
  history, p_anchor takes the league rate (and in the FROZEN recipe, ew_*
  falls back to lg_rate). This is a FEATURE VALUE - a number the estimator
  needs so arithmetic works. It grants nothing.
- PERMISSION TO ISSUE A PREDICTION: the registered cold_start_no_prior
  EXCLUSION - a POLICY gate that refuses to score entities with zero frozen-
  table history. It is owned by the owner decision (provisional rule, pending),
  not by feature arithmetic.
- The challenger changes feature construction ONLY. It does NOT touch the
  exclusion: zero-history entities remain unscored/unpublished under the
  registered rule; 'league fallback, flagged' describes a feature value inside
  an already-permitted row, never permission for a forbidden one.

## 7. Statistical plan

- ONE primary challenger (section 4). ONE primary contrast: challenger vs
  baseline on pooled DEVELOPMENT evaluation rows (82,817 observed PAs),
  paired by evaluation row, primary score = LOG LOSS delta.
- Primary score justification: log loss is a proper scoring rule that
  penalizes confident errors continuously - the right instrument for testing
  whether an age-aware anchor sharpens well-calibrated probabilities; Brier is
  retained as a pre-declared SUPPORTING score (sensitivity analysis) and
  calibration is summarized (reliability/reliability-gap), neither selectable
  as primary post hoc.
- Inference: paired bootstrap n=2000, seed 20261001, slate-date block-
  stratified, null-centered two-sided p. Holm m=1: the family contains exactly
  the one pre-declared primary contrast (no selectable alternatives), so no
  multiplicity correction applies; the notation records that the family was
  fixed in advance.
- Per-fold (block-level) deltas: DESCRIPTIVE only, never gated.
- Reporting: the 59 abstentions (57 genuine debutants + 2 window-limited
  veterans, Enns 608650 and Hart 606996) are PROMINENTLY reported in every
  output of this diagnostic; 4,823/4,866 dev starts = 99.12% dev coverage; the
  original run stays FAILED against its zero-exclusion acceptance and is never
  relabeled.

## 8. Older data: separate question, minimal layer, existing files

- The two window-limited veterans show the frozen table's 2022-04-07 boundary
  is a CONSTRUCTION choice, not a data availability limit: raw statcast
  regular-season parquets 2015-2021 ALREADY EXIST on disk.
- Minimal historical PA layer (fields needed ONLY for K/PA history; no modern
  bat-tracking required): stable player IDs (MLBAM batter + pitcher),
  game_pk/game_date, terminal PA outcome (K events incl. strikeout_double_play,
  excluded truncated_pa - the exact conventions already in code), and the
  PA-denominator fields (PA counting rule + excluded-event list). Optional:
  team/side for opponent context. Statcast covered all parks from 2015; the
  2020 season is short - both noted as validation inputs, not disqualifiers,
  for a K/PA-denominator layer.
- Per-season validation BEFORE any use: schema/field stability, MLBAM ID
  stability across sources and seasons, PA-counting compatibility (does each
  season's event taxonomy map to the same K/PA definition), league-rate
  continuity at each seam, deduplication keys, and cutoff integrity.
- SEASONAL COMPATIBILITY CHECKS for the extension: (a) 2020 60-game season
  (structure, not measurement - K/PA is outcome-based); (b) pre-2015 absence
  (Statcast not park-complete); (c) PitchFX-vs-Statcast measurement eras affect
  tracking metrics, NOT the outcome fields this layer needs - document, and
  exclude any field whose meaning changes across eras.
- Any extension is a SEPARATE registered improvement, informed by the 57/2
  split: for the 57, extension cannot help (no earlier MLB data exists); for
  the 2 veterans, extension restores information whose age must still be
  discounted by the declared decay rule.

## 9. Prohibitions (unchanged)

No fitting, no prediction regeneration, no historical backfill, no
confirmation-period performance inspection, no modification of the preserved
run or any frozen artifact. Approval of this card authorizes specification
work only; fitting requires its own explicit approval.
