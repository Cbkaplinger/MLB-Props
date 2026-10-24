# STATUS 9 (lineup diagnostic CONTROL INVARIANT FAILED — interpretation
# stopped per owner order, 2026-10-22, latest) —
# The committed runner (lineup_diagnostic.py, 4 synthetic tests) ran on
# real data (lineup_diagnostic_v1_attempt6, write-once). RESULT: the
# CONTROL INVARIANT FAILED — max |PMF_projected - PMF_oracle| = 0.1143
# for the batter-independent PITCHER arm (tolerance 1e-12). ROOT CAUSE:
# the two conditions necessarily draw probabilities from DIFFERENT
# feature-construction paths (projected = the preserved ledger's as-of
# slot states; oracle = the pa_table-attached states), so the PITCHER
# arm's probability VALUES differ between conditions regardless of
# batter order. Raw outputs (n=4,681 common; FULL -0.0142 projected /
# -0.0224 oracle; interaction -0.0081 CI [-0.0117, -0.0045]) are
# recorded but NOT interpretable as lineup effects. The earlier
# 2x2-script numbers (n=4,477) inherit the same violation and are
# equally uninterpretable as lineup effects.
# RESOLUTION OPTIONS (owner decision required):
#   (a) same-frame cohort: both conditions from the pa_table-attached
#       features only -> invariant holds, cohort shrinks to the ~277
#       starts where all nine projected batters actually batted;
#   (c) ledger-features-for-both is impossible (actual batters outside
#       the projection have no ledger rows).
# PER THE OWNER'S ORDER: the lineup-effect interpretation is STOPPED.
#
# Morning/close overlap cohort published (prerequisite for the frozen
# early-market scoring): morning_close_cohort_v1/ - 2,109 starts, key
# hash aadc2d2a3caa104fd6629c7b7057d8de422d4b0aa6afe51c3de75d404495d5aa.
#
# STATUS 8 (paired 2x2 lineup diagnostic, 2026-10-22) — SUPERSEDED by
# STATUS 9: its numbers inherit the control-invariant violation.
# PITCHER/FULL x projected/oracle lineups, identical eligible keys
# (n=4,477 common), fits + BF forecasts + registered aggregation +
# scoring held fixed; only the lineup input changed. ORACLE = the
# actual first-appearance batting order (realized lineup identity;
# labeled ORACLE, never deployable pregame).
#   PITCHER: projected RPS 1.29880 | oracle 1.26879 (control delta
#     -0.0300 — NOTE: the control is NOT clean; it measures the
#     feature-construction difference between the ledger slot path and
#     the pa_table PA path, not batter identity, since PITCHER-only
#     probabilities are batter-independent)
#   FULL:    projected RPS 1.28419 | oracle 1.24548 (delta -0.0387)
#   FULL - PITCHER | projected: -0.01462 CI [-0.02245, -0.00668]
#   FULL - PITCHER | oracle:    -0.02331 CI [-0.03088, -0.01587]
#   CHANGE in (FULL-PITCHER), projected -> oracle: -0.00869
#     CI [-0.01219, -0.00514]
# FINDINGS:
# 1. The "batter features hurt count-RPS" reversal DOES NOT EXIST on
#    the valid population: the earlier ablation count-RPS was computed
#    on ~277 starts/block where all nine projected batters happened to
#    bat (a long-game skew artifact). RETRACTED; the ablation record
#    carries the correction.
# 2. On the correct population (ledger-projected nine slots, all
#    4,823 starts), FULL beats PITCHER-only on count-RPS — consistent
#    with the per-PA ordering. Lineup-projection error is NOT
#    demonstrated as a count-layer problem; the oracle slightly
#    WIDENS FULL's advantage (supporting batter features as a
#    contributor, not a liability).
# 3. Contributor framing per owner: the oracle result SUPPORTS lineup
#    identity as a benign-to-helpful input; it does not exclude
#    calibration, workload, or aggregation contributions.
# The per-PA loss ordering and the market baselines (STATUS 7) are
# unaffected.
#
# STATUS 7 (cohort-split baseline + early-market coverage, 2026-10-22,
# latest) — per owner order the cohorts are now REPORTED SEPARATELY
# (they are different benchmarks, never pooled into one effect):
#   2025H1 TRUE T-5 CLOSE (n=2,154): close 0.6890 | dumb +0.0254 |
#     model +0.0234 CI [+0.0142, +0.0330]; Brier close ~0.2464 vs
#     model 0.2583.
#   2024 PRIOR-EVENING LINE (n=2,182, key hash b517101d6d6967b7):
#     close 0.6829 | dumb +0.0502 | model +0.0371 CI [+0.0262, +0.0482];
#     Brier 0.2449 / 0.2608. NOT a close comparison (no 2024 commence
#     times; the snapshot is the vendor's prior-evening clock).
#   The +0.0303 combined-cohort figure and its CI are RETIRED from
#   headline use (mixed timing tiers).
# CORRECTION: the 22 consensus exclusions are documented COLD-START
# ABSTENTIONS (Chat 2's resolution); the earlier "probable starters who
# never started" wording is withdrawn.
# EARLY-MARKET COVERAGE (tier A, vendor snapshot clocks, verified
# quotes, 2024-07-01..2025-06-30; snapshot labels are the vendor's
# clocks, NOT verified first-posted opens):
#   morning (vendor T-5h clock): 80,974 pre-cutoff rows; 2,368 starts
#     two-sided (100%); median lead 5.0h; 9 books; overlap with the
#     verified 2025H1 close cohort: 2,109/2,154 (97.9%).
#   open18 (vendor T-18h clock): 15,232 pre-cutoff rows; 1,420 starts
#     two-sided; median lead 18.0h; 8 books.
#   board (median lead 10.0h): 52,706 rows; 2,313 starts; 9 books.
# INPUT AVAILABILITY AT EARLY TIMESTAMPS: model inputs are strictly
# prior-game-date; previous-day data is fully available before the
# morning snapshot's ~T-5h timestamp -> CLEAN early benchmark. For
# open18 (~T-18h, ~1am ET) the previous evening's late west-coast
# games may finish AFTER the quote -> the model's as-of state
# partially post-dates the open18 quote; any open18 scoring must
# disclose this. PROTOCOL FROZEN before any early-market score is
# inspected: the same frozen per-PA probabilities scored at EACH
# market quote's own line (per-line binary events; no cross-line
# probability deltas invented); no tuning against any market number.
# NEXT (main modeling task, design stated): the PA-loss/count-RPS
# reversal investigation on identical eligible keys - projected-lineup
# count-RPS (PITCHER 1.32294 vs FULL 1.34526) vs an ORACLE-LINEUP
# diagnostic (actual first-appearance batting order, labeled oracle);
# if FULL's deficit narrows under the oracle, the cause is lineup
# projection error interacting with batter features.
#
# STATUS 6 (accounting reconciliation + quote audit, 2026-10-22)
# — FUNNEL (reconciled exactly): 825,326 quotes -> 406,285 own-player
# (419,041 dropped by the identity filter) -> 82,722 near-close ->
# 4,358 consensuses -> [bridge1 vendor-key->id: 0 unmatched] ->
# 4,336 model-cohort eligible (22 excluded: ALL absent from the model
# frame entirely - probable starters who never started the game; 0
# block-filtered) -> 4,336 final scored (0 lost at the final join).
# The old metric name "consensus_unmatched_to_model" was MISLEADING
# (it measured the vendor-key->id bridge); renamed
# "consensus_unmatched_to_start_bridge".
# QUOTE-SELECTION AUDIT TABLE (write-once,
# quote_selection_audit.parquet, 82,373 rows = 4,336 starts x their
# selected near-close quote rows): per row - game_pk, canonical
# pitcher_id, vendor_player_key, team_side, bet_side, book, line,
# price, quote_timestamp, bet_clock_snapshot; plus the matched event
# linkage for all 2,154 2025H1 starts (2,182 2024 prior-evening starts
# carry full quote provenance; their candidate-audit event linkage was
# 2025H1-scoped and is disclosed as absent). team_side vs bet_side are
# now DISTINCT fields (the first audit build mislabeled team side as
# bet_side - fixed).
# LADDER HELPER: ladder_implied_pmf output records now carry the
# pitcher key on EVERY row including no_ladder cases (regression
# tested); the ladder benchmark itself stays blocked and was not run.
# PAIRED RESULTS (unchanged from STATUS 5; scored parquet
# 1d9a00343d17956f; receipt d652e42a... / 6f69286c41765bb0...):
#   2025H1 (n=2,154): close 0.6890 | dumb +0.0254 | model +0.0234
#   full repaired (n=4,336): close 0.6859 | dumb +0.0379 |
#     model +0.0303; Brier close 0.2464 vs model 0.2596
#   decision: model_not_better_than_close (CI [+0.0236, +0.0373] on the
#   full cohort). Code SHA for the recorded run: 23db50d (the runner's
#   metric RENAME and the ladder-helper identity fix postdate the run
#   and change no scored number).
#
# STATUS 5 (full-key identity repair + rescore, 2026-10-22, FINAL) —
# The identity repair is COMPLETE: pitcher identity now flows through
# every stage (near-close dedup keys, consensus pivot/group/selection,
# and the final model join all use the start key game_pk + quoted
# pitcher; one consensus per start enforced with fail-loud fan-out
# checks; boundary counts in the receipt). Regression tests cover the
# demonstrated cases: two starters in one game keep distinct
# consensuses; changing one starter's quotes leaves the other
# unchanged; dropping one starter cannot borrow the opponent; no
# start-level fan-out from snapshots/books; the unfiltered dedup
# provably scored Webb on Nelson's prices.
# REPAIRED RESCORE (write-once market_eval_k_v3_fullkey_attempt2;
# scored-cohort parquet 1d9a00343d17956f):
#   2025H1 true T-5 close (n=2,154): close 0.6890 | dumb +0.0254 |
#     model +0.0234  (log loss, positive = worse than close)
#   full repaired cohort (n=4,336): close 0.6859 | dumb +0.0379 |
#     model +0.0303; Brier close 0.2464 vs model 0.2596;
#   decision: model_not_better_than_close (CI excludes zero the other
#   way). Coverage: 4,358 verified consensuses, 4,336 joined,
#   0 unmatched, joined_start_key_unique = true; 419,041
#   opposing-starter quotes dropped by the identity filter.
# FINAL INTERPRETATION: with every quote belonging to its own
# pitcher-game, the closing line beats BOTH the one-parameter baseline
# and the frozen model - the market behaves as an efficient market
# should. The earlier apparent edge was an artifact of the two
# identity defects (opposing-starter quote mixing + per-game market
# collapse); it is fully resolved. No betting edge is claimed; the
# close is the benchmark and it wins. 2024 remains prior-evening
# lines; no 2026 run.
#
# STATUS 4 (join repaired + rescored, 2026-10-22, latest) —
# DEMONSTRATED DEFECT: the odds task frame attached a matched event's
# game_pk to ALL its quotes; 419,041 of 825,326 rows (50.8%) quoted the
# OPPOSING starter, and the per-(game_pk, book, line, side) dedup mixed
# the two players' prices arbitrarily. REPAIRED by an identity filter
# (verified_odds_for_start: quoted player == matched start's own key;
# no outcomes/correlations involved) with regression tests.
# Candidate-level audit (match_audit_v1, write-once): only 2
# demonstrated wrong-EVENT picks from the +/-1-day tolerance (of 2,161),
# 3 ambiguous doubleheader candidates, 86 starts without a
# normalized-exact-date candidate. Correlation thresholds REMOVED as
# acceptance criteria per owner correction; the standard is identity.
# RESCORE (2025H1 true T-5 closes, common cohort n=2,233; full repaired
# cohort n=4,515; 419,041 contaminated quotes + minor event drops
# disclosed):
#   close 0.6940 | dumb baseline 0.6603 (gap -0.0337) |
#   frozen model 0.6572 (gap -0.0368)   [2025H1]
#   close 0.6908 | dumb baseline 0.6616 (gap -0.0292) |
#   frozen model 0.6533 (gap -0.0375)   [full repaired]
# INTERPRETATION (bounded): the repair did NOT collapse the gap, so
# "the entire apparent edge came from mismatched games" is NOT
# demonstrated. Neither is an edge: the one-parameter baseline still
# matches the model to ~0.003, the encompassing test remains
# non-significant, and the principal-line de-vig price is ~50/50 by
# market design (the standing hypothesis for why ANY K-rate model beats
# it; testable only against a two-sided ladder, i.e. the 2026 Kalshi
# benchmark). The market comparison remains SUSPENDED as a decision
# input; 2024 stays prior-evening lines; no 2026 run.
#
# STATUS 3 (owner-ordered join-validity audit, 2026-10-22, latest) —
# **THE MARKET COMPARISON IS UNDER AUDIT; THE JOIN FAILED VALIDITY.**
# RETRACTED: any framing that the -0.034 gap is model skill.
# OWNER CORRECTION ADOPTED: low correlation is a WARNING, not proof of
# wrong matches, and NO correlation threshold is used as a
# join-acceptance criterion (the earlier "~0.5-0.7 expected" gate is
# REMOVED). The acceptance standard is IDENTITY: does this quote belong
# to this pitcher, in this particular game, at the claimed time?
# Evidence still standing (as warnings, not proof):
# (a) line<->realized-K correlation 0.206, line<->model-mean 0.381
# over the 2,245 true-close starts;
# (b) the line's MAE (1.985) EQUALS a constant league-mean predictor's
# MAE (1.985) — the matched lines added nothing over a constant;
# (c) 505 of 2,161 matched events used a +/-1 DAY date tolerance (an
# ambiguity RISK, not a demonstrated defect count);
# (d) a one-parameter baseline "beat" the close by -0.0305 — consistent
# with uninformative matches but not proof of them.
# CONSEQUENCE: the close, dumb-baseline and model gaps in this record
# are NOT interpretable until the event join is repaired by identity
# and time evidence and all three are rescored.
#
# STATUS 1 (earlier): the ladder benchmark CANNOT be run validly from
# the held archive - the alternate market is OVER-SIDE ONLY (under
# quotes were never captured), per-rung book coverage is sparse (1-4
# books), and per-book de-vig margins are noisy (p10 = -0.021). The
# implied count distribution is therefore unreliable and the ladder
# falsification test is BLOCKED on data. The line-shuffle placebo is
# DEGENERATE (the close is so flat that shuffling line-to-start is a
# no-op). Receipts for all ladder attempts preserved write-once
# (ladder_benchmark_v1 .. _attempt5).

## Follow-up checks (owner-ordered, 2026-10-22, later still)

- 2024 relabeled **"prior-evening line"**; it is excluded from every
  close comparison. THE close comparison is 2025H1 true T-5 closes
  only: n=2,245, model 0.6610 vs close 0.6947, gap -0.0337.
- LABEL AUDIT: PASS - realized_k matches the OFFICIAL starter K from
  the frozen pa_table on 100% of joined starts (0 differing; mean K
  4.80; mean official BF 21.96). The 17.2 eval-PAs-per-start figure is
  the projected-lineup slot frame (the per-PA feature population), not
  the outcome label.
- ENCOMPASSING (over_hit ~ const + p_model + p_close, OLS White SE,
  n=2,245): p_model coef +0.846 (t=+1.75, NOT significant at 5%);
  p_close coef +0.087 (t=+0.19). The model keeps its weight with the
  close included, but not at conventional significance - the edge
  stays UNPROVEN by this test.
- MAE/RMSE (2025H1): model mean K 1.857/2.348 beats the market line
  1.985/2.492 vs actual K.
- CORRECTED PLACEBO (shuffle the MODEL's predictions across starts,
  20 seeds): shuffled model LOSES to the close (close - shuffled =
  -0.062, i.e. ll 0.757 vs 0.695); the real model beats the close by
  +0.034 - far outside the placebo range. The matched pairing carries
  real information.
- KALSHI: the exchange ladder (11,929 rows, 676 closes, two-sided) is
  2026-season ONLY (2026-07-30..2026-09-05) - no dev overlap. It
  becomes the two-sided distribution benchmark for the 2026 holdout
  run, where the sportsbook ladder cannot serve.
- Net position: promising dev evidence that passes the label and
  corrected-placebo checks; the encompassing test does not reach
  significance; the extraordinary-claim bar is unmet. The 2026 holdout
  (with Kalshi as the ladder benchmark) is the decisive test.

## Bias check (owner-ordered, 2026-10-22, latest)

2025H1 (n=2,245): mean line 4.9009, mean model K 4.5262, mean realized
K 4.8134. Line bias +0.0875 K; model bias -0.2871 K (the model
under-predicts on average).

| predictor | MAE | RMSE |
| --- | --- | --- |
| market line (raw) | 1.985 | 2.492 |
| market line (bias-adjusted) | 1.980 | 2.490 |
| model mean K (raw) | 1.857 | 2.348 |
| model mean K (bias-adjusted) | 1.849 | 2.330 |

The constant line bias explains almost NOTHING of the model's RMSE
advantage (2.492 -> 2.490; the gap stays ~6%). Log loss at the
bias-adjusted line (ladder-sampled at line - bias, n=856 with usable
curves): close 0.6835 vs model 0.6321 on the same starts - the gap
WIDENS to -0.0514 under the location correction. The model's advantage
is distributional shape, not line location; it survives the bias
check.

## Answer first

On the 4,527 scored dev starts (93.9% of the 4,823 registered), the
REGISTERED frozen count layer beats the de-vigged near-close consensus
at its own line:

| metric | model | close | delta (model - close) |
| --- | --- | --- | --- |
| log loss (over/under) | 0.65723 | 0.69118 | **-0.03395** |
| Brier | 0.23379 | 0.24902 | -0.01523 |
| count-RPS (full distribution) | 1.31586 | n/a (line only) | - |

- 95% CI on the log-loss delta (paired slate-date bootstrap, n=2000,
  seed 20261001): **[-0.04216, -0.02590]** - entirely negative.
- p (null-centered) = 0.0005; Holm m=1 adjusted = 0.0005.
- decision: `model_better_than_close` (dev evidence; the confirmation
  block remains the final judge).

## Coverage (drops disclosed at every stage)

| stage | starts |
| --- | --- |
| registered model starts (dev) | 4,823 |
| window starts in the odds join | 4,866 (model frame covers 4,823) |
| starts without event/commence (tier B clock proxy) | 2,442 |
| scored vs a near-close consensus | **4,527 (93.9%)** |
| median two-sided books per start | 7 |

Drops: 296 model starts had no two-sided near-close consensus (late
scratches / no board); they are excluded symmetrically for both sides
and disclosed. Join chain reused UNCHANGED from the tested
odds-coverage machinery (16 tests). Cutoff policy: strict pre-cutoff
within 60 min (tier A, 2025-26) / vendor `close` snapshot (tier B,
2024). The close snapshot is a NEAR-close (p50 ~T-9.35min) - treat
all close comparisons as near-close.

## Reliability (model over-probability deciles)

The model is close to calibrated at the extremes and optimistic in
the middle-low buckets (e.g. p=0.27 -> observed 0.34; p=0.37 -> 0.44),
pessimistic around 0.51 -> 0.47. Direction of the miscalibration is
mixed; the owner's calibration plan (held per step 4) now has evidence
to act on for this market.

## Outputs (write-once, preserved)

`...\pregame-pa-ext-v2\diagnostics\market_eval_k_v1_attempt2\`:
receipt_initial `37411c8d...`, receipt_final / metrics / parquet
recorded in the receipt chain; the first attempt (`market_eval_k_v1`)
failed on a string-timestamp dtype defect, failure record preserved,
fixed at `e3c2e50`.

## Workload-leakage experiment (owner-ordered, 2026-10-22)

BF input answer: the per-start PMF used the REGISTERED PREGAME BF
forecast (bf-workload-v1 artifact, per-start pmf37 with prior_n /
prior_mean state columns; count_agg_eval.py:269-273) - never the
realized batters faced.

Workload A/B (same 4,527 joined starts, same consensus lines):

| workload input | model log loss | gap vs close (0.6912) |
| --- | --- | --- |
| A: registered per-start BF forecast (as scored) | 0.6572 | -0.0339 |
| B: POOLED workload (one shared BF distribution, zero per-start workload info) | 0.6564 | **-0.0348** |

The edge SURVIVES with all per-start workload information removed ->
workload leakage excluded as the cause.

## What the edge actually is (decomposition)

The close's de-vigged principal-line price carries almost no
discrimination: std(p_close) = 0.052 vs the model's std(p_model) =
0.152; the close sits between coin-flip (0.6931) and the oracle
constant (0.6904) - it beats coin-flip by only 0.0019, exactly the
owner's bias arithmetic. The model's 0.034 advantage is RESOLUTION
(knowing which starts lean over), not the bias term. CRITICAL CAVEAT:
the de-vigged price AT the settled principal line is ~50/50 partly BY
CONSTRUCTION (books balance the main line; the market's information
lives in the line choice and the ladder). The honest market benchmark
is therefore the ALTERNATE-LADDER-implied count distribution, not the
binary principal-line price. The ladder comparison is the corrected
test and supersedes the -0.0339 headline as a market benchmark.

- Dev evidence only: the frozen model's fit lineage (2023) predates
  the dev blocks, but the confirmation block is the pre-registered
  final judge; no claim of live edge until it confirms.
- The close comparison is at the line (binary over/under), not the
  full count distribution; the close cannot produce a count PMF from
  one line.
- 2024 events use the vendor close snapshot (no local commence times
  exist for 2024, documented in the odds-archive acceptance audit).
