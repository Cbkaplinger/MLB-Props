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

## CORRECTION (2026-10-20, during review hold) - scope of a later history extension

Section 6 stated the 2015-2021 extension is relevant 'ONLY to the 2
window-limited veterans.' That is too narrow and is corrected: older history
would also change CUMULATIVE estimates for ALREADY-ELIGIBLE players - the
frozen recipe's career-cumulative priors (prior_k/prior_n), n_prior counts,
and the strictly-prior league rate all accumulate from the table origin
(2022-04-07), so pre-2022 rows would enter those statistics for eligible
players as well. The extension is therefore NOT merely an abstention-recovery
lever; it is a population-wide input change whose effect would need its own
registered evaluation.
- This weighting experiment (one batter-history challenger) is deliberately
  run on EXISTING 2022-forward data so the two questions stay isolated:
  better weighting of existing history vs more history. Never both at once.
- Enns/Hart remain the only two currently EXCLUDED starts that an extension
  could potentially recover for scoring; the clarification concerns eligible
  players' cumulative inputs.
- Extension remains a separate registered proposal (minimal PA-outcome layer,
  per-season validation, seasonal compatibility checks per section 8); it is
  not a prerequisite for this card and not part of this challenger.

## v3.1 - IMPLEMENTATION APPENDIX (2026-10-20): deterministic key
## serialization resolved; implementation + synthetic tests complete

Implementation commit (this one) on research/paext-v2-scoring-run,
refreshed onto current main at the coordinated integration point
(merge of origin/main #4/#22-state: merge commit 55e2105; the paext lane
and harness were byte-identical across the merge). Published implementation
SHA: see the backlog receipt for this turn.

### Deterministic serialization (resolves the review finding)

- Both development key sets serialize as: encoding UTF-8; field separator
  | (U+007C); line separator LF (0x0A); NO trailing newline after the
  final line; NO header; no padding; ordering ascending by the NUMERIC
  tuple (game_pk, side-ASCII, slot) for slot keys and (game_pk,
  at_bat_number) for evaluation keys; each set MUST be duplicate-free
  (duplicates fail loud as construction defects); NO dates in the key
  stream ((game_pk, side, slot) uniquely determines game_date inside the
  frozen lineup artifact - asserted at verification, so a date column is
  redundant, not identity-bearing).
- Slot key line: {game_pk}|{side}|{slot}; evaluation key line:
  {game_pk}|{at_bat_number}. Hash = sha256 over the exact byte stream.
- RELATION TO THE EARLIER ABBREVIATED PINS: the provisional pins
  published with v3 (82592f18..., c6568151...) were computed with THIS
  exact byte format; what was missing was the declaration. The
  recomputation under the now-declared format REPRODUCES both hashes
  byte-for-byte (--verify-keys-only PASSED 2026-10-20): slot keys
  43,407 -> 82592f18f824359e9a48848acf7662c040edc5e3284ed6f4a1741137606318ef;
  evaluation keys 82,817 ->
  c65681512d5de924e842e80d7c7f27369889590f1c46111eec11e25acb50f902.
  No serialization was chosen to force a match: the format is the minimal
  identifying tuple with a numeric total order and a canonical encoding;
  the recomputation under an INDEPENDENTLY WRITTEN reimplementation of
  these rules reproduces the pins, and the pins would have been replaced
  with an old->new explanation had they not reproduced. One subtlety
  surfaced and fixed during the declaration: the ordering is NUMERIC by
  (game_pk, at_bat_number), not lexicographic line order (variable-width
  at_bat_number); the serializers sort tuples, never lines, and
  duplicate-key inputs fail loud.
- Implementation: research/offseason_2026/pregame_pa_ext/batt_recency.py
  (canonical serializers + verify_published_keys + --verify-keys-only).

### Implementation (gated, synthetic-tested only)

- batt_recency.py: challenger feature builder (attach_batt_recency)
  reusing the adapter's state machinery conventions; challenger model
  family (StandardScaler + LogisticRegression(C=1.0, max_iter=1000) on
  the 8 CHALLENGER_FEATURES); observed-PA identity join with
  (game_pk, at_bat_number) uniqueness guard; eligible-slot ledger filter
  (never re-admits an excluded row); CLI with --verify-keys-only and a
  HARD GATE (--i-accept-fitting-execution absent -> refusal, exit 2,
  contract text printed). The fitting/evaluation stage has NEVER run.
- One convention note discovered by the synthetic tests: the frozen asof
  convention takes the prior state strictly before the entity's LAST
  game date L <= t (prior_n = rows < L). The challenger splits THAT
  SAME set (recent = (t-60d, L); anchor = <= t-60d and < L), so
  n_win + n_anchor_raw == adapter prior_n exactly. On the diagnostic's
  evaluation population (observed PAs on the game date, L = t) the
  convention is exactly 'all PAs strictly before t'.

### Synthetic test results (CI-safe, no lake, no mlflow)

tests/test_batt_recency_diagnostic.py: 14 collected / 14 passed (1.5s),
covering: cross-season continuity; empty/short history (feature default
vs permission distinction asserted); long inactivity (mass decays, anchor
-> league); recent/anchor boundary (PA at exactly t-60d -> anchor; same-
day PA -> neither); no double counting (n_win + n_anchor_raw == adapter
prior_n across random forecast dates); forecast-relative decay (mass
exactly halves at +90d); strictly-prior source dates; identical
training/inference construction (same builder, bit-equal); unique
pitcher-matched observed-PA joins incl. the 777417-style cross-side
duplicate projection (each PA once; unobserved side contributes 0; a
defective same-PA-two-slots projection fails loud); exclusion policy
unchanged (excluded rows never re-admitted); baseline artifacts
byte-identical around diagnostic calls; canonical hash determinism,
numeric-order sensitivity, duplicate rejection.

### Bounded execution contract (proposed, NOT authorized)

One authorized real-data run of this diagnostic would execute EXACTLY:
(1) --verify-keys-only gate: both published hashes + counts assert; (2)
feature build over the 4,823 dev-eligible starts / 43,407 slots from the
preserved ledger (read-only); (3) fit ONE primary challenger (R=60d,
m=30) per dev block on rebuilt historical training rows (2023-01-01..
block cal_first - the frozen recipe's training-row selection); (4)
evaluate LOG LOSS primary (paired by evaluation row on the 82,817 frozen
keys, slate-date bootstrap n=2000 seed 20261001, null-centered + Holm
m=1) + Brier/calibration supporting; (5) write-once outputs to a NEW
diagnostics directory (pregame-pa-ext-v2/diagnostics/batt_recency_v1/)
- the preserved parquet is never written and never modified; (6) the 59
abstaining starts (57 debut-date newcomers + Enns 608650 / Hart 606996)
prominently reported in every output; (7) confirm_2025H2 untouched; (8)
tracking optional through the shared wrapper; (9) any acceptance failure
stops all downstream use. No population-policy change; no backfill; no
comparative-claims language beyond the registered primary/supporting
scores.

### Future count-aggregation work (queued as a specification note only)

note_count_aggregation_future_2026-10-20.md distinguishes (A) unequal-
batter-probability aggregation (the cycled prefix-mean treats slots as
exchangeable) from (B) workload/performance dependence (the BF-N x per-PA
p independence assumption). Neither is implemented; each needs its own
registered card; they must never be changed at once.

## v3.2 CONTRACT AMENDMENT (2026-10-20, during PR #25 review):
## mandatory provenance receipt + explicit unfinished-work register

### Readiness clarification (what PR #25 @ 48155ec contains)

PR #25 is FEATURE/JOIN/MODEL-PRIMITIVE INFRASTRUCTURE + KEY
VERIFICATION + A GATED CLI - it is NOT a complete runner. The
fitting/evaluation stage currently prints a refusal and exits 3 when
the gate flag is passed, because the execution code does not exist yet.
UNFINISHED WORK (none of it is in PR #25; none of it has been started
on real data):

1. Training-frame assembly: selecting the frozen recipe's historical
   training rows per dev block (2023-01-01..block cal_first) and building
   the challenger feature frame on them (challenger_feature_frame exists;
   the per-block row selection + y join is unwired).
2. Per-block refit orchestration (train frame -> fit_challenger_models
   -> per-block scoring of the evaluation rows).
3. Evaluation-table construction: aligning frozen baseline p_h3_raw and
   challenger probabilities on EXACTLY the 82,817 frozen dev evaluation
   PAs (identity join, forecast-pitcher matching, unchanged eligibility).
4. Metric computation: log loss primary + paired slate-date bootstrap
   (n=2000, seed 20261001, null-centered, Holm m=1) + Brier/calibration
   supporting.
5. Write-once diagnostic outputs under a NEW directory (preserved parquet
   never written).
6. The MANDATORY provenance receipt (see below).

Authorization of fitting is therefore NOT the only remaining step; the
runner must be implemented, reviewed, and published first. No real-data
fitting or evaluation has occurred at any point.

### Mandatory provenance receipt (replaces 'tracking optional')

Every execution of this diagnostic MUST write a persisted provenance
receipt to its write-once output directory BEFORE any result is reported
or used. The receipt is a standalone JSON record containing, at minimum:

- input identities: sha256 of the frozen pa_table, the preserved run
  ledger, the registered checkpoint artifact (canonical payload pin +
  raw-file sha), the BF PMF artifact, and the lineup artifact;
- code/configuration identities: sha256 (LF-normalized) of batt_recency.py
  and every imported lane module, the freeze/registration config content
  hash, and the challenger configuration (R=60d, m=30, feature list);
- the frozen development key-set hashes and counts (82592f18... /
  c6568151..., 43,407 / 82,817);
- per-block fit records (training-row counts, coefficients' sha256),
- all reported metrics (log loss primary, Brier/calibration supporting,
  bootstrap result) and the output file inventory with sha256s;
- the run's acceptance-check outcomes.

MLflow is an OPTIONAL transport for this receipt (shared wrapper,
phase=diagnostic, pipeline_id joined to paext-v2-20261020T141540Z) - but
the RECEIPT ITSELF IS MANDATORY and must be written even if the tracking
transport fails (the reviewed preservation contract applies: a tracking
failure surfaces, never refits, and the receipt stays on disk). A run
without a complete receipt is unaccepted by definition.

Nothing else in the card changes: log loss primary, one challenger,
dev-only population, protected confirm, unchanged gates and eligibility.

## v3.3 (2026-10-20): runner implemented - synthetic-exercised only;
## execution readiness pending Chat 2 review of this delta

The v3.2 unfinished-work register items 1-6 are now IMPLEMENTED in
research/offseason_2026/pregame_pa_ext/batt_recency.py (clearly separated
delta commit in PR #25): per-block training-frame assembly (frozen
recipe's realized-PA lineage via build_checkpoint.build_feature_frame;
original PA identity (game_pk, at_bat_number, batter, y) retained; NOT
assembled from the evaluation subset - asserted by test), per-block
refit/scoring orchestration, paired baseline/challenger evaluation table
(p_baseline from the preserved ledger + p_challenger, identical rows),
registered metric/bootstrap machinery (log loss primary; paired
slate-date bootstrap n=2000 seed 20261001 block-stratified null-centered
plus Holm m=1; Brier + calibration supporting), write-once outputs, and
the MANDATORY provenance receipt (validated before acceptance;
incomplete receipts rejected; MLflow transport optional). Synthetic
exercises: tests/test_batt_recency_diagnostic.py now 22/22 (refusal gate
preserved; end-to-end synthetic runner; deterministic bootstrap
byte-identical across runs; block isolation; output collision fail-loud;
incomplete-receipt rejection; real published-pin gate still enforced).
The runner has NEVER run on real data; execution readiness requires Chat
2 review of this delta plus explicit owner authorization of the bounded
execution contract.
