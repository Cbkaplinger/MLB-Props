# Batter-history challenger specification v3 - FINAL for review (2026-10-20)

Pre-registration specification. Ready for INDEPENDENT SPECIFICATION REVIEW by
Chat 2. NO fitting, NO new predictions, NO historical backfill, NO comparative
performance inspection, NO confirmation-period evaluation, NO frozen-artifact
changes, NO new worktree has occurred. The preserved scoring run remains
UNACCEPTED and is never relabeled. Approving this card approves specification
only; fitting requires explicit approval afterward.

Revision register: v1 (draft, five issues) -> v2 (dev-only population, observed-
PA labels, rebuilt training, staleness confidence, one challenger/log-loss) ->
v3 (this document): outcome-join reconciliation, unique evaluation grain + the
duplicate (game_pk, batter) explanation, frozen coverage table with key hashes,
explicit staleness formula with 'decayed PA mass' terminology.

## 1. Outcome joins - reconciling 82,817 (v2) and 208,767 (Chat 2)

Both numbers are correct over DIFFERENT scopes, verified exactly:

| join | projected slots included | join keys | pitcher restriction | PAs |
| --- | --- | --- | --- | --- |
| Chat 2's 208,767 | ALL projected slots (7,194 starts x 9 = 64,746, incl. the 531 cold-start slots) | (game_pk, batter, game_date) | NONE - the batter's PAs in that game against ANY pitcher | 208,767 |
| v2's 82,817 (dev) | DEV-ELIGIBLE slots only (starts with zero cold-slot exclusions, dev blocks) | (game_pk, pitcher, batter, game_date) | REQUIRED - the PA's actual pitcher must equal the FORECAST pitcher | 82,817 |

Exact decomposition (computed):
- Pitcher-unrestricted join over eligible slots, all blocks: 207,075; over ALL
  slots (adding the cold-start starts' slots): 208,767 (exact match with Chat 2).
- Pitcher-matched join over eligible slots, all blocks: 121,973; dev: 82,817;
  confirm: 39,156 (protected, counted only).
- Difference 207,075 - 121,973 = 85,102 PAs are the projected batters' plate
  appearances AGAINST OTHER PITCHERS (relievers, mid-game changes) in eligible
  games - EXCLUDED from this matchup diagnostic by the rule below.
- SPEC RULE: an observed PA enters the evaluation only if the PA's actual
  recorded pitcher EQUALS the forecast (projected) pitcher for that start.
  That batter's PAs against relievers are excluded from this matchup
  diagnostic (they test a different matchup, not the projected one).

## 2. Unique evaluation grain

- Grain: (game_pk, at_bat_number) - verified UNIQUE in the frozen pa_table
  (0 duplicate keys). Pitcher/batter/start identities are retained on every
  evaluation row.
- Join multiplicity check: after the identity join, 0 (game_pk, at_bat_number)
  keys match more than one projected slot - each eligible observed PA
  contributes EXACTLY ONCE per arm (verified max multiplicity = 1).
- The two duplicate (game_pk, batter) rows, explained (not deduplicated away):
  game_pk=777417, batter=646240 appears in BOTH starts of the same game -
  Bot slot 3 (forecast pitcher 678394) and Top slot 2 (forecast pitcher
  694738), both eligible. Cause: the prior-games reconstruction pools batters
  from each team's observed prior lineups; batter 646240 batted for both teams
  within their respective prior-7-game windows (trade across the two teams),
  so both sides' pools contain him. Both projections are kept: each is a
  distinct conditional forecast for its own matchup. His ACTUAL PAs in that
  game: 3 vs 678394 (at_bat_number 6, 21, 38) and 1 vs reliever 692285
  (at_bat_number 58). Therefore 3 evaluation rows attach to the Bot slot's
  probability, 0 to the Top slot (the Top matchup never occurred vs its
  forecast pitcher), and no PA is double-assigned (the PA's recorded pitcher
  selects at most one slot). Counting note: Chat 2's 'two duplicate pairs'
  = the two rows of this one (game_pk, batter) key; this report counts keys,
  so it appears as one duplicated key carrying two rows.

## 3. Frozen development coverage (keys and counts frozen here)

Development = block_2024H2 + block_2025H1 eligible slots only. FROZEN:

| quantity | value |
| --- | --- |
| dev eligible projected-slot keys (game_pk, side, slot) | 43,407; sha256 82592f18f824359e9a48848acf7662c040edc5e3284ed6f4a1741137606318ef |
| dev evaluation keys (game_pk, at_bat_number) | 82,817; sha256 c65681512d5de924e842e80d7c7f27369889590f1c46111eec11e25acb50f902 |
| dev starts total / eligible / abstaining | 4,866 / 4,823 / 43 |
| dev cold-start PA exclusions (rows) | 387 (180 in 2024H2 + 207 in 2025H1) |
| confirm_2025H2 (PROTECTED, out of development) | 2,312 eligible starts; 39,156 observed PAs; counts recorded, never used |

Separate coverage categories (development):

| category | dev slots | dev PAs |
| --- | --- | --- |
| cold exclusions (59 starts list; 43 in dev) | 387 rows | - |
| projected batter NEVER appeared in that game | 7,669 | - |
| batter appeared but NEVER vs the forecast pitcher (relievers only) | 2,645 | (subset of 57,295 all-block eligible reliever PAs) |
| unmatched actual PAs in dev-eligible games (not the projected matchup or non-projected batters) | - | 100,348 of 183,165 |
| matched evaluation PAs | - | 82,817 (183,165 - 100,348 = 82,817, exact) |

SCOPE STATEMENT: this PA diagnostic is CONDITIONAL ON OBSERVABLE PROJECTED
MATCHUPS - it evaluates the projected (batter vs forecast pitcher) matchup
where it actually occurred. It is NOT an evaluation of every lineup slot, not
a full-offense evaluation, and makes no claim about unobserved matchups.

## 4. Staleness formula (explicit)

For a forecast date t and a historical PA row with game_date d_i < t:

    w_i(t) = 2^(-(t - d_i) / 90)      [half-life 90 days, frozen constant]

- Weighted K mass:  WK(t) = sum_i w_i(t) * k_i   (k_i = 1 if the PA ended in a
  strikeout)
- Decayed PA mass:  M(t)  = sum_i w_i(t) * n_i   (n_i = 1 per PA; M is the
  summed weight and is the DECLARED confidence measure - called 'decayed PA
  mass', NOT statistical effective sample size, which is separately defined
  and not claimed here)
- Anchor rate (shrinkage to the as-of league rate, same w150 weight and target
  as the frozen recipe):

    p_anchor(t) = (WK(t) + 150 * lg_rate(t)) / (M(t) + 150)

- The normalized EW rate ew_k/ew_den alone does NOT lose confidence with age
  (the date weights cancel in the ratio); confidence lives in M(t), which
  decays explicitly. A 2022-07-10 observation contributes weight ~2^(-730/90)
  ~ 0.0037 to M at a 2025-07-10 start.
- Recent component (strictly inside the window, disjoint from the anchor pool):
  k_win / n_win over rows with d_i in (t-60, t).
- Update rule (PRIMARY configuration, R=60 days, m=30):

    p_batt_new(t) = (k_win + 30 * p_anchor(t)) / (n_win + 30)

- All component values (n_win, k_win, M(t), WK(t), lg_rate) are recorded per
  row. Empty recent window: p_batt_new = p_anchor. Empty anchor pool:
  p_anchor = lg_rate (INTERNAL FEATURE DEFAULT - see section 6 of the v2
  register, restated: a feature value, never permission to score; the
  registered cold_start_no_prior exclusion remains the policy gate).
- Strictly-prior cutoff: identical asof machinery; two new source-date columns
  (src_date_batt_recent, src_date_batt_anchor) join the existing hard cutoff
  gate in the diagnostic only.
- Feature set: p_batter_prior_w150 + ew_batter REPLACED by p_batt_recent +
  p_batt_anchor (8 features; pitcher side, lg_rate, counts, cold_start,
  ew_pitcher unchanged).

## 5. Experiment (fixed, no selection)

- ONE primary challenger: R=60 days, m=30. No extra configurations, no search,
  no selection among candidates.
- Features rebuilt for EVERY historical training row as of that row's own date;
  per dev block: StandardScaler + LogisticRegression(C=1.0, max_iter=1000) on
  the SAME training rows as the frozen block model (2023-01-01..block
  cal_first; scaler on train only). Historical training-row selection is
  UNCHANGED from the frozen recipe; training rows begin 2023 (2022 feeds
  priors only). This is NOT an annual-reset repair - the frozen model already
  carries history across seasons.
- PRIMARY score: LOG LOSS, challenger vs the unchanged frozen baseline, paired
  by evaluation row on the 82,817 frozen dev keys, paired slate-date bootstrap
  n=2000, seed 20261001, block-stratified, null-centered two-sided p.
  Holm m=1 = the family is exactly the one pre-declared primary contrast.
- SUPPORTING (never selectable post hoc): Brier; calibration summary
  (reliability curve / gap). Per-block deltas descriptive only.
- Reporting: the 59 abstentions (57 debut-date newcomers + 2 pre-2022
  veterans, Enns 608650 and Hart 606996) PROMINENTLY reported in every output;
  dev coverage 4,823/4,866 = 99.12%. The original run stays FAILED against its
  zero-exclusion acceptance and is never relabeled; the diagnostic reuses its
  valid predictions only.

## 6. Data boundary

- This experiment uses EXISTING 2022-04-07..2025-09-28 data only.
- Older data (raw statcast 2015-2021) already exists locally; extending
  history is a SEPARATE proposal using compatible PA outcome fields (minimal
  layer per the v2 register) - NOT a prerequisite and NOT part of this
  challenger. Its relevance is now narrowed: it can help only the 2
  window-limited veterans (Enns, Hart); the 57 debutants have no earlier MLB
  history in any source.

## 7. Prohibitions (unchanged) and handoff

No fitting, no new predictions, no backfill, no comparative performance
inspection, no confirmation-period evaluation, no frozen-artifact changes, no
new worktree. Preserved run: UNACCEPTED, untouched.

HANDOFF: this specification is READY FOR INDEPENDENT SPECIFICATION REVIEW by
Chat 2 - especially the frozen dev key hashes (section 3), the pitcher-matched
outcome join and its 208,767-vs-82,817 reconciliation (section 1), the
777417 duplicate-pair treatment (section 2), and the staleness formula's
'decayed PA mass' semantics (section 4). Published at the SHA noted in the
backlog receipt for this turn.
