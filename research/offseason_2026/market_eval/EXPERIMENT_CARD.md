# EXPERIMENT CARD: market-eval-v1

**Registered:** 2026-10-14. **Status (correction C2, 2026-10-14):** PREP v2
EXECUTED (write-once, bit-reproducible); SCORING CODE COMPLETE but the
scoring run REMAINS NOT AUTHORIZED and has not been executed against the
frozen prep. This card is the single registration for the market-layer
evaluation. No fitting, calibration, blending, thresholding, or policy
search is permitted under this card. 2026 data is out of scope
(no-2026-tuning rule).

> **CORRECTION C2 (2026-10-14) — read before the original sections.** The
> original prep (`outputs\prep\`, kept byte-frozen below as the v1 record)
> was built by a load step with two defects, both found by rerun
> verification: (a) the market-pooling key omitted `player_norm`, so
> whenever two pitchers shared an (event, snapshot, book, line, side) key
> (750,797 such keys in the archive) one pitcher's quotes were arbitrarily
> DELETED; (b) `sort + unique(keep=...)` tie handling was unstable, so the
> pipeline was nondeterministic run to run (eval pairs varied 10,640-10,650
> across processes; the frozen v1 numbers were one draw). Per this card's
> write-once protocol, prep was re-executed into a NEW directory
> `outputs\prep_v2\` with the pooling key fixed and every dedup made
> deterministic (file-row-index tie-breaks + maintain_order). v1 outputs
> stand as the superseded record; ALL registered analysis under this card
> uses prep_v2. A second defect (`chosen_for_eval` flag marking every
> (start, line, book) row instead of the chosen book) is also fixed in v2.
> Deviation note: no authorized canonical scoring run; one accidental run
> occurred (2026-10-14 ~17:15, outputs deleted, inspection status
> UNRESOLVED) — a test invoked `--score` with default paths after the
> scoring code landed but before its guard test was rewritten; its outputs
> were deleted without being cited and are NOT evidence of any kind; the
> authorized scoring run remains gated.

## Question

Do the frozen projected-state K PMFs (H3-raw, LOG5-raw) carry probability
skill against de-vigged market prices at matched contracts, and does a fixed
pre-registered paper-betting rule clear its costs? Outcome scoring happens in
a LATER authorized run; this card + prep pin every choice made before it.

## Scope and read-only sources

| Role | Path |
| --- | --- |
| Quotes (The Odds API archive) | `data\Odds-Historical\theoddsapi\book_lines_pitcher.parquet` (4.03M rows; K markets) |
| Snapshot envelope | `data\Odds-Historical\theoddsapi\snapshot_envelope.parquet` (commence_time per event) |
| Frozen model payload | `MLB-Props-Research\pregame-pa-ext-v1\data\predictor_payload.parquet` (accepted projected-batter-state v2; 7,194 starts; per-PA H3-raw/LOG5-raw + count PMFs + BF PMFs) |
| Identity bridge | `data\dimensions\player_id_map.parquet` |
| Realized K (SCORING ONLY, not joined yet) | `MLB-Props-Research\bf-workload-v1\data\start_metrics_v2.parquet` (`realized_k` per game_pk/side/pitcher) |
| Join lineage provenance | `MLB-Props-Research\odds-coverage-v1\join_coverage.py` + `COVERAGE_REPORT.md` |

Input sha256_16 hashes are recorded in `outputs\prep\manifest.json`.

## 1. TIMING (registered)

- `forecast_time` = scheduled first pitch. Tier A (2025-26 events with a
  vendor `commence_time` in the envelope): first_pitch_ts = earliest
  commence_time per event. Verified clock.
- Tier B (2024 events; no local commence source): the archive clocks are
  pregame by construction (odds-coverage-v1 acceptance audit: `close` returned
  p50 T-9.35min, `morning` T-5h, `board` fixed 12:00Z, `open18` T-18h).
  First-pitch time is unknown; the clock labels act as a proxy. Tier B rows
  are kept separate from Tier A in every output and summary.
- Quote time = `snapshot_ts` (UTC). Verified: `snapshot_ts` is constant within
  (event, snapshot) in the archive (0 event-snapshots with >1 ts).
- **Closing reference** (benchmark/CLV only; NEVER in the actionable set):
  per (start, line, book, side): Tier A = the latest quote with
  `quote_ts < first_pitch_ts` (last quote before the vendor commence);
  Tier B = the latest `close`-clock quote.
- **Actionable set** = pre-cutoff quotes MINUS the closing-reference row
  itself: Tier A: `quote_ts < first_pitch_ts AND quote_ts < closing_ref_ts`;
  Tier B: `snapshot != 'close'`. The latest actionable quote per
  (book, line, side) is the actionable price.
- Separation guarantee: closing refs and actionable prices are disjoint by
  construction; tier A CLV is therefore non-trivial (actionable precedes
  close). A book/line/side whose ONLY pre-cutoff quote is its closing ref has
  no actionable price (counted in coverage).

## 2. IDENTITY (registered)

Join chain (mirrors odds-coverage-v1): payload MLBAM id ->
`player_id_map` name -> sorted-token normalized key -> archive `player_norm`
(vendor game_date is UTC vs local Savant date: match within +/-1 day,
closest first, ties by event_id) -> event_id -> envelope commence_time.

Fixed exclusion rules (exclude AND count; no rescues attempted in v1):

1. **Unresolved ids:** pitcher MLBAM id absent from `player_id_map` (the
   62-start class from odds-coverage-v1). Excluded.
2. **Doubleheader ambiguity:** archive (vendor_game_date, pitcher_key) maps
   to 2+ event_ids (the 54-key class). The envelope carries no game_pk and
   the payload carries no team labels, so no event_id maps unambiguously to
   one game_pk. All starts landing on such keys are excluded.
3. **Price validity:** quotes with |price| outside [1, 100000] dropped
   (counted; vendor junk such as -5,000,000).
4. **Duplicate quote rows** (same event/snapshot/book/market/player/line/
   side, 5,386 rows, all with differing prices): keep the max price
   (bettor-best); ties keep first file row.
5. **Market pooling:** `pitcher_strikeouts` and `pitcher_strikeouts_alternate`
   are pooled; one row per (event, snapshot, book, line, side) at the max
   price across the two markets.

Eligible coverage is RECALCULATED after all exclusions (section below).

## 3. CONTRACT PROBABILITIES (registered)

- Contract lines come from the actionable quote set at the matched start.
- Frozen PMFs: `pmf_h3_raw_0..23` (H3-raw) and `pmf_l5_raw_0..23` (LOG5-raw)
  from the accepted payload. No refit, no recalibration, no blending. Support
  is k = 0..23; P(K >= 24) is 0 by payload truncation (payload contract).
- **Half-line L** (fractional, e.g. 5.5): `p_over = P(K >= ceil(L))`,
  `p_under = P(K <= floor(L))`, `p_push = 0`.
- **Integer line L** (e.g. 2.0, 4.0): `p_push = P(K = L)`,
  `p_over = P(K >= L+1)`, `p_under = P(K <= L-1)`; push = explicit refund
  semantics (stake returned, PnL 0). Note: the 2024-25 cohort contains no
  integer-line contracts (see prep run report); the rule is registered and
  tested for completeness.
- Separate named fields per contract side row:
  `p_market` (proportional no-vig probability from the PAIRED contemporaneous
  over/under prices at the SAME book and SAME snapshot ts:
  `p_over_mkt = (1/d_over)/(1/d_over + 1/d_under)`),
  `break_even` (1/decimal of the offered price), `ev_h3` / `ev_l5`
  (model expected PnL per 1-unit stake: `p_win*(d-1) - p_lose`; push = 0).
- American -> decimal: `d = 1 + p/100` (p > 0); `d = 1 + 100/|p|` (p < 0).
- Pairing rule: per (start, line, book) the pair ts is the LATEST clock in
  the relevant set (actionable / closing-eligible) where the book quotes BOTH
  sides; a book without a both-sides clock contributes no pair.

## 4. EVALUATION (registered; NOT executed)

Observation unit (anti-duplication): ONE observation per
(start, line, side). The single (book, ts) pair per (start, line) is chosen
by the registered rule, applied in order:

1. max total decimal (`d_over + d_under`) — best price on both sides;
2. tie -> lowest index in `BOOK_PRIORITY` (below);
3. tie -> latest pair ts.

`BOOK_PRIORITY` (registered before execution):
`draftkings, fanduel, betmgm, williamhill_us, betrivers, bovada, fanatics,
betonlineag, mybookieag, superbook, pointsbetus, barstool, unibet_us`
(unknown books sort last, alphabetically among themselves).

Primary probability-skill metric (at the scoring run): **multi-class Brier at
matched contracts** on identical observations, classes {over_win, push,
under_win}, competitors H3-raw vs LOG5-raw vs de-vig market (`p_market`),
push counted as a class (refund). Secondary: count-RPS on the full frozen
PMF vs realized K (support 0..23; realized K clamped to 23, disclosed).
Per-book breakdowns reported for every metric; per-tier and per-line-bucket
breakdowns reported. Uncertainty: paired slate-date bootstrap, **2000
resamples, seed 20261001, resampling unit = game_date** (slate), identical
resample indices across all competitors.

## 5. PAPER BETTING (registered; ONE fixed research rule, no optimization)

- Rule: bet a side when **H3-raw `p_win > break_even + 0.02`** (margin 0.02,
  strict >), stake 1 unit flat, at the **first qualifying book by
  BOOK_PRIORITY** among paired actionable quotes. Over and under are
  independent bets. H3-raw drives the rule (champion lineage); LOG5 is
  evaluated for probability skill only.
- Reported separately from probability skill: paper ROI, PnL, win rate, and
  **CLV vs closing** (`clv_pct = (d_bet - d_close)/d_close`) using the bet
  book's OWN closing side price; bets without a closing ref keep their bet
  row but are excluded from CLV stats with the count disclosed.
- Execution assumptions (disclosed): fills at the full quoted price at the
  actionable snapshot; no partial fills, no limits, no margin/fees; push = 0
  PnL; one unit per qualifying (start, line, side).

## Prep outputs (write-once; `outputs\prep\`)

| File | Content |
| --- | --- |
| `matched_contracts.parquet` | one row per (start, line, side): model probs (both arms), de-vig `p_market`, `break_even`, `ev_h3`/`ev_l5`, chosen book/ts/prices, tier |
| `actionable_pairs.parquet` | per (start, line, book) paired actionable price + de-vig, `chosen_for_eval` flag |
| `closing_refs.parquet` | per (start, line, book) paired closing benchmark + de-vig |
| `paper_bets.parquet` | registered bet rows (no outcomes; CLV fields where close exists) |
| `prep_summary.json` | exclusions, coverage after exclusions, contract counts, bet counts, constants echo |
| `manifest.json` | input + output sha256_16 hashes + registered constants |

Write-once policy: a prep run into a directory containing any prep output
fails (`WriteOnceError`). Rerunning prep requires a NEW directory and a note
in this card (versioned correction).

## Coverage recalculation (after exclusions)

Eligible starts = 7,194 payload starts minus unresolved-id exclusions minus
doubleheader-ambiguous exclusions. Coverage flags per eligible start:
`has_precutoff_quote` (>=1 actionable quote), `has_any_precutoff` (>=1
pre-cutoff quote even if it is the closing ref), `has_closing_ref`. Results
are written to `prep_summary.json` (`identity`, `coverage`, `contracts`,
`paper_bets` keys) and mirrored in the run report below.

## Commands

Tests (synthetic fixtures only, no archive reads; 28 tests):

```
cd C:\Users\ckaplinger\MLB-Props-Research\market-eval-v1
python -m pytest tests\ -q
```

Prep v2 (executed 2026-10-14 under correction C2; write-once,
bit-reproducible across processes):

```
cd C:\Users\ckaplinger\MLB-Props-Research\market-eval-v1
python market_eval.py            # writes outputs\prep_v2 (write-once)
```

Verification + benchmark separation + exclusion ledger (outcome-free):

```
cd C:\Users\ckaplinger\MLB-Props-Research\market-eval-v1
python verify_ledger.py          # writes outputs\verification\; updates
                                 # prep_v2\prep_summary.json additively
```

SCORING RUN (code COMPLETE under C2; EXECUTION NOT AUTHORIZED — requires
owner approval; the command below has never been run against the frozen
prep. SUPERSEDED 2026-10-14: executed ONCE as recorded in the
EXECUTED-RUN record at the end of this card — the text below stands as
the pre-execution registration). F-4 hard opt-in gate: `--score` REFUSES to run without the explicit
`--i-accept-outcome-scoring` flag (the refusal names the gate, reads no
inputs, writes nothing, exits 2). Passing the flag confirms intent to join
realized outcomes; it does NOT by itself constitute owner authorization:

```
cd C:\Users\ckaplinger\MLB-Props-Research\market-eval-v1
python market_eval.py --score --i-accept-outcome-scoring --prep-dir outputs\prep_v2 --start-metrics "C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\data\start_metrics_v2.parquet" --score-dir outputs\score_v2 --seed 20261001 --n-boot 2000
```

It verifies prep hashes (fail loud on mismatch), joins realized K, settles
the registered paper bets, computes the PIN skill metrics (paired
contract-level multi-class Brier; H3-raw vs LOG5-raw vs de-vig market on
identical matched contracts; slate-date bootstrap 2000/seed 20261001 with
identical resample indices), reuses the persisted count-layer errors, and
writes `outputs\score_v2\` (bets_ledger, clv_table, skill_metrics,
bootstrap, score_summary, score_manifest) under a write-once guard.

## Prep run report — v2 (executed 2026-10-14 under correction C2)

Inputs verified: `book_lines_pitcher.parquet` sha256_16 `325abdf01f5f0b84`
(match); all four input hashes recorded in `outputs\prep_v2\manifest.json`.
Cross-process rerun into a scratch directory reproduced all four output
parquets bit-identically.

Identity + exclusions (starts_total 7,194; full ledger in
EXCLUSION_LEDGER.md):

| Rule | Excluded | Eligible |
| --- | --- | --- |
| Unresolved ids (player_id_map) | 62 | - |
| No matching archive event (+/-1 day) — disclosed in C2 (v1 silent) | 294 | - |
| Doubleheader-ambiguous keys (54 archive keys; 25 starts) | 25 | - |
| **Eligible starts** | | **6,813** (Tier A 4,624 / Tier B 2,189) |

Coverage after exclusions (recalculated by verify_ledger.py; matches
prep_summary exactly):

| Tier | Starts | Actionable quote | Closing ref | Both |
| --- | --- | --- | --- | --- |
| A verified clock | 4,624 | 4,514 (97.6%) | 4,622 | 4,514 |
| B clock proxy | 2,189 | 2,133 (97.4%) | 2,185 | 2,131 |
| **All** | **6,813** | **6,647 (97.6%)** | **6,807 (99.9%)** | **6,645** |

Contracts (from the actionable set only):

- Paired (start, line, book) actionable pairs: 59,636; closing paired refs:
  70,373.
- Eval observations: **20,004 (start, line) pairs = 40,008 (start, line,
  side) contract rows** (Tier A 28,044 / Tier B 11,964), covering 6,643
  starts, 270 slate dates, 11 distinct half-lines (0.5..10.5).
- Integer lines: ZERO contracts in this cohort (registered + tested
  push semantics unexercised; disclose in the scoring report).
- Quote-time rule (C2): actionable quotes must be at/after
  `predictor_available_ts` (= forecast_cutoff 00:00 ET); earlier quotes are
  reference-only, not actionable. The floor removed 8 starts / 19
  (start, line) observations / 11 bets from the v2 pool; verification
  confirms ZERO selected quotes or bets predating predictor availability
  (Tier A primary; Tier B separately labeled sensitivity).

Paper bets (registered rule, no outcomes computed): 11,435 bets
(over 2,414 / under 9,021; Tier A 7,784 / Tier B 3,651); 10,962 with a
closing ref for CLV, 473 without (disclosed at scoring). Multiple bets per
start: 3,731 starts, max 5 bets/start — ladder exposure warning: bets
within a start share the same realized K and are NOT independent.

Prep v2 output hashes (sha256_16, see `outputs\prep_v2\manifest.json`):
matched_contracts `185abda9a238dd97`, actionable_pairs `32d65386b92718e4`,
closing_refs `fbcad4d833cb7dc9`, paper_bets `6e310c49bc238795`.

## Selection rule (ONE rule, registered under C2)

Per (start, line, side): among pre-cutoff quotes take the LATEST snapshot
per book; then the book by `BOOK_PRIORITY`; then the best decimal price;
then the book name. The paper-bet edge gate (H3-raw p_win >
break_even + 0.02, strict >) selects WHICH (start, line, side) cells bet;
among bet-eligible books the same ordering applies. Verified against the
frozen prep bet selection: 0 differences on all 11,435 bets. The separate
registered eval-observation rule (one pair per (start, line) by max total
decimal, then priority, then latest ts) remains the observation rule for
the market de-vig comparison; the book-choice delta between the two rules
(23,978 of 40,008 side rows) is disclosed in
`outputs\verification\verification_report.json`.

## Verification bundle (2026-10-14, outcome-free)

`outputs\verification\` holds: `verification_report.json` (clock
verification vs the envelope — open18 T-18.0h p50, morning T-5.0h p50,
close T-5min p50, board T-10.8h p50, 7,429 post-cutoff tier-A quotes
present in the archive and excluded; cohort dates 2024-07-01..2025-09-28;
identity recheck 54 ambiguous keys / 25 starts), `exclusion_ledger.json`
(reconciles exactly: 7,194 = 62+294+25+166+4+1,244+5,399),
`benchmark_refs.parquet` (opening-time, later-pregame, and closing
references as separate fields per eval observation: 20,004/20,004/19,235
coverage; 12,223 observations have a single actionable clock so opening =
later-pregame), and `prep_summary_original.json` (byte-copy of
prep_summary.json before the additive verification key was appended).

## Prep run report — v1 (SUPERSEDED by C2; kept for the record)

The report below describes `outputs\prep\`, which is byte-frozen and
superseded; do not cite its counts. Inputs verified against the accepted
archive manifest: `book_lines_pitcher.parquet` sha256_16 `325abdf01f5f0b84`
(match).

Identity + exclusions (starts_total 7,194):

| Rule | Excluded | Eligible |
| --- | --- | --- |
| Unresolved ids (player_id_map) | 62 | - |
| Doubleheader-ambiguous keys (52 archive keys; 25 starts land on them) | 25 | - |
| **Eligible starts** | | **6,813** (Tier A 4,624 / Tier B 2,189) |

Coverage after exclusions:

| Tier | Starts | Actionable quote | Closing ref | Both |
| --- | --- | --- | --- | --- |
| A verified clock | 4,624 | 4,519 (97.7%) | 4,622 | 4,519 |
| B clock proxy | 2,189 | 2,135 (97.5%) | 2,185 | 2,131 |
| **All** | **6,813** | **6,654 (97.7%)** | **6,807 (99.9%)** | **6,650** |

Contracts (from the actionable set only):

- Paired (start, line, book) actionable pairs: 28,535; closing paired refs: 35,961.
- Eval observations after the registered dedup rule: **10,647 (start, line)
  pairs = 21,294 (start, line, side) contract rows** (Tier A 14,598 /
  Tier B 6,696), covering 5,697 starts, 11 distinct half-lines
  (0.5..10.5; modal 4.5-6.5).
- **Integer lines: ZERO contracts in this cohort.** The archive's integer
  K lines (2.0, 4.0) exist only in 2023 (8 rows), outside the 2024-07+
  cohort. Push semantics are registered and unit-tested but unexercised by
  real data; disclose this in the scoring report.
- Actionable-quote starts without a contract: 957 = 350 starts with no book
  quoting BOTH sides at any actionable clock (mostly alternate-market-only
  coverage) + 607 starts where both sides exist but never at the same
  (line, book, clock).

Paper bets (registered rule, no outcomes computed): 6,188 bets
(over 1,265 / under 4,923; Tier A 4,064 / Tier B 2,124); 5,800 with a
closing ref for CLV, 388 without (disclosed at scoring).

Prep output hashes (sha256_16, see `outputs\prep\manifest.json`):
matched_contracts `420091e353fbb258`, actionable_pairs `544956c4a4481f9c`,
closing_refs `91b6528ea5363433`, paper_bets `65c52a4bb1a3f874`.

## CORRECTION C3 (2026-10-14) — AMENDED REGISTRATION

This section AMENDS the registration above. It is appended, not substituted:
the original registration text stays in force as the historical record and
is quoted verbatim below wherever this amendment changes it (marked
ORIGINAL). Nothing in this amendment restores untouched evaluation: the
prep was rebuilt under C2 after v1 defects, the scoring code was written
and reviewed before any authorized run, and an unauthorized scoring
execution already occurred (see UNRESOLVED item). This amendment completes
and pins the registration so a FUTURE authorized scoring run, if approved,
is evaluated against a fully specified, deterministic, reviewed protocol.

### C3.1 Estimand (amended; supersedes nothing, completes section 4)

ORIGINAL (section 4): "Primary probability-skill metric (at the scoring
run): **multi-class Brier at matched contracts** on identical observations,
classes {over_win, push, under_win}, competitors H3-raw vs LOG5-raw vs
de-vig market (`p_market`), push counted as a class (refund)."

AMENDED registration: every reported skill metric is the ROW-WEIGHTED
estimand — the sum of per-row metric contributions divided by the count of
rows over all included rows (rows never thinned):

- Brier: `sum_rows [(p_win - y_win)^2 + (p_push - y_push)^2
  + (p_lose - y_lose)^2] / n_rows` over matched contract side rows.
- Log loss (secondary, non-push rows): `sum_rows[-(y log p + (1-y)
  log(1-p))] / n_nonpush_rows`, clipped at `LOG_FLOOR = 1e-12`.
- Paper ROI: `sum(pnl_units) / n_bets` over settled paper bets.

The unit of resampling is the SLATE DATE (`game_date`); a date contributes
ALL of its rows (per-date numerator sum + row count), never a thinned or
averaged version. The point estimate is the same row-weighted estimand on
the full data. This matches the parity target
`research/offseason_2026/run_paired_uncertainty.py` (estimand: "sum of
per-row losses / count of rows over all sampled-date rows").

### C3.2 Bootstrap stratification/weighting (amended)

ORIGINAL (section 4): "Uncertainty: paired slate-date bootstrap, **2000
resamples, seed 20261001, resampling unit = game_date** (slate), identical
resample indices across all competitors."

AMENDED registration (the reviewed repair; verified by F-1 hand-calculated
test `test_slate_bootstrap_hand_calculated_unequal_slate_sizes` and C3
regression `test_slate_bootstrap_block_stratified_row_weighted`):

1. BLOCK-STRATIFIED draws: within each block the replicate draws exactly
   that block's ORIGINAL slate-date count of dates, with replacement
   (multinomial over the block's dates). A replicate can never drop or
   over-draw a block.
2. ROW-WEIGHTED pooled combination: per-block numerators (per-row metric
   sums over sampled-date rows) and denominators (sampled row counts) are
   summed ACROSS blocks; the replicate statistic is numerator/denominator,
   on the same per-row scale as the point estimate. Block weights cannot
   shift across replicates.
3. PAIRED draws: ONE draw of date indices per block per replicate is shared
   across ALL competitors (H3-raw, LOG5-raw, de-vig market, and the
   H3-vs-LOG5 / H3-vs-market / L5-vs-market pairwise diffs), so intervals
   are paired at the draw level.
4. Params unchanged: 2000 resamples, seed 20261001 (ROI bootstrap uses the
   adjacent stream seed+1, disclosed), percentile interval [2.5, 97.5].

### C3.3 Block definitions (registered)

Owner-ruled v3 assessment windows (identical to
`run_paired_uncertainty.BLOCK_WINDOWS`; parity by construction):

| Block | Window | Role |
| --- | --- | --- |
| `block_2024H1` | 2024-01-01 .. 2024-06-30 | development |
| `block_2024H2` | 2024-07-01 .. 2024-12-31 | development |
| `block_2025H1` | 2025-01-01 .. 2025-06-30 | development |
| `confirm_2025H2` | 2025-07-01 .. | CONFIRMATORY (never pooled into dev) |

Bootstrap resampling and pooled point estimates use DEVELOPMENT blocks
only; `confirm_2025H2` rows are reported separately and never enter the
dev pooled estimand. Cohort note: the prep_v2 cohort spans
2024-07-01..2025-09-28, so prep_v2 carries `block_2024H2`, `block_2025H1`,
and `confirm_2025H2` rows only (`block_2024H1` precedes the archive
cohort; the window definition above still applies to any future prep).

### C3.4 Selection and settlement behavior (repaired; registration completed)

ORIGINAL (section "Selection rule"): "Per (start, line, side): among
pre-cutoff quotes take the LATEST snapshot per book; then the book by
`BOOK_PRIORITY`; then the best decimal price; then the book name." and
"one pair per (start, line) by max total decimal, then priority, then
latest ts".

AMENDED registration:

- **F-2 (pair_sides collapse):** distinct snapshot labels (or prices) can
  share ONE `quote_ts`; the pairing/collapse steps reduce to exactly ONE
  row per (start, line, book, side) before pairing and ONE pair per
  (start, line, book) after, deterministically (full-column sort + first).
  Hard `_assert_unique` join-cardinality guards on closing_side_refs
  (start, line, book, side), paper_bets (start, line, side), and all prep
  outputs fail loud BEFORE any write instead of silently multiplying rows.
- **Eval-observation tiebreak (completed):** the one-pair-per-(start, line)
  ordering is max total decimal, then lowest `BOOK_PRIORITY` index, then
  latest pair ts, THEN book name ascending. The final name tiebreak is
  required because two books both outside BOOK_PRIORITY tie on all three
  original keys; without it the choice was nondeterministic across
  processes (fixed in commit 850aa38).
- **F-3 (settlement semantics):** half line NEVER pushes (over wins at
  K >= ceil(L), under wins at K <= floor(L)); integer line L pushes at
  K == L for BOTH sides with exact 0.0 refund; invalid side / negative K
  fail loud. Pinned by the K = 0..20 sweep
  `test_settlement_half_line_never_pushes_and_integer_push_refunds`.
- **F-5 (push-aware bet columns):** paper-bet EV uses the refund
  decomposition `p_h3_win*(d-1) - p_h3_lose` (push mass excluded from the
  lose term; eea37bc), and the paper-bet table carries `p_h3_push` (the
  frozen-PMF push probability) per bet row (244ee13).

### C3.5 prep_v2 persisted constants are HISTORICAL

Where the constants echoed inside the frozen prep_v2 outputs
(`prep_summary.json` -> `registered_constants`, `manifest.json`) differ
from this amended registration, the PERSISTED ECHO is HISTORICAL and this
section governs. Known divergences:

- `observation_dedup` in prep_v2 reads "...max total decimal, then book
  priority, then latest ts" — HISTORICAL; the amended rule adds the final
  book-name tiebreak (C3.4).
- `bootstrap_registered_only` in prep_v2 records only n_resamples / seed /
  unit — HISTORICAL; the amended bootstrap is block-stratified and
  row-weighted per C3.2/C3.3.
- The prep_v2 output bytes themselves are UNCHANGED by this amendment
  (write-once holds; the F-2 outcome-free audit found 0 duplicate keys and
  the expanded OLD-vs-NEW selection audit is reported in
  FINDINGS_F1_F5_2026-10-14.md).

### C3.6 Accidental scoring exposure — UNRESOLVED

Status: **no authorized canonical scoring run; one accidental run occurred
(2026-10-14 ~17:15, outputs deleted, inspection status UNRESOLVED).**

C2 disclosed that a test invoked `--score` with default paths after the
scoring code landed but before its guard test was rewritten; outputs were
deleted without being cited. THIS ITEM REMAINS UNRESOLVED: the exposure
inspection (what was joined, what was computed, what the deleted outputs
contained, and any information leak into subsequent decisions) has not
been completed and no closure evidence exists. Nothing in this amendment
should be read as clearing that exposure or as restoring an untouched
evaluation state. The authorized canonical scoring run remains separately
owner-gated (F-4 flag confirms intent only).

### C3.7 Population definitions for ALL reported metrics (F-6 completion)

AMENDED registration (completes C3.3; supersedes any pooled-population
reading of the scoring outputs): every metric the scoring run reports is
computed per POPULATION from ONE validated block->population assignment,
applied identically to skill points, bootstrap draws, per-tier and
per-book breakdowns, count summaries, ROI, and paper bets:

- **dev** = `block_2024H2` + `block_2025H1` (development headline;
  `block_2024H1` is a registered dev window per C3.3 but precedes the
  prep_v2 archive cohort and cannot occur in prep_v2 rows);
- **confirm** = `confirm_2025H2` (never pooled into dev, never mixed into
  any dev point, interval, ROI, or count summary).

Concretely, the score outputs carry:

1. **Validation (fail loud):** `run_score` validates every row's `block`
   label against the registered cohort set {block_2024H2, block_2025H1,
   confirm_2025H2} immediately after the outcome join; unknown or null
   labels raise `PopulationLabelError` naming the offending labels and row
   counts BEFORE any metric is computed. Empty known blocks are permitted
   (a block with 0 rows is OK).
2. **Dev-only headline:** `skill_metrics.json` top-level `dev` block and
   `bootstrap.json` `brier` (points + block-stratified intervals) are
   computed on DEV rows ONLY; `score_summary.json` `skill_headline` is
   labeled with its population.
3. **Serialized confirmation:** the confirmation metrics (per-arm Brier +
   CI, log loss, skill vs market, per-tier breakdown, effective counts
   n_rows/n_dates, and the paired `h3_minus_l5` bootstrap) are written to
   `confirm_metrics.json` in the score dir AND mirrored under
   `bootstrap.json` `confirm` + `skill_metrics.json` `confirm`.
   `confirm_metrics.json` is part of the write-once SCORE_FILES set.
4. **Per-population ROI and counts:** `bootstrap.json` `paper_roi` is
   `{dev, confirm}` (separate block-stratified ratio bootstraps; no pooled
   interval is reported); `skill_metrics.json`
   `count_layer_persisted_reused` is `{dev, confirm}`;
   `score_summary.json` adds `bets_by_population` and per-population CLV
   means; `bets_ledger.parquet` and `clv_table.parquet` carry a
   `population` column per row. Tier A/B separation is preserved WITHIN
   each population (`per_tier` keys).
5. **Reconciliation:** `effective_counts.dev_rows + confirm_rows =
   contract_side_rows` with per-block row counts, pinned by the
   run_score-invoking regression
   (`tests/test_f6_confirmation_separation.py::test_f6_run_score_population_separation_end_to_end`)
   and the pre-existing helper tests
   (`test_f6_confirmation_exclusion.py`, the `_slate_bootstrap`
   known-answer test).

### C3.8 Null-centered approximate bootstrap test for the 4 predeclared RAW Brier contrasts (amendment, 2026-10-15)

AMENDED registration for the recency-batch-v1 freeze
(`specs/count-eval-v2-spec/harness/freeze_recency_batch_v1.json`, new
`hypothesis_test` section; config sha256 changes from
`4b11e4b7...f810` to `05c7790ac039579ce0e19bae7720c19aa0803ddf0d22746e1b0f6a07dcce9104`
under the file's own hash definition). ADDITIVE only: frozen candidates,
inputs, folds, seed, n_boot, lanes and output destination are UNCHANGED;
nothing here authorizes a run.

**Registered inference.** For each of the 4 predeclared contrasts
(C1_pitcher_ew_vs_B, C2_batter_ew_vs_B, C3_both_vs_pitcher_only,
C4_both_vs_batter_only, each a SIGNED RAW Brier difference exactly as
registered in the freeze's `evaluation.contrasts_predeclared`):

1. **Estimand (exact fold aggregation):** the EXISTING block-stratified
   row-weighted pooled dev estimand - sum of per-row Brier contributions
   divided by the count of rows over all pooled dev rows (dev blocks
   2024H1/2024H2/2025H1 only; confirm_2025H2 excluded-not-scored). The
   observed contrast delta `Delta_j` is the difference of the two
   candidates' pooled RAW Brier point estimates on the identical shared
   rows (per-fold eval-identity hash equality asserted).
2. **Resampling (paired, shared):** the EXISTING paired slate-date
   bootstrap, block-stratified, row-weighted num/den ratio, n_boot=2000,
   seed=20261001. The per-block date draws depend only on
   (blocks, dates, n_boot, seed), so ONE draw stream is shared across
   candidates AND contrasts; contrast replicate deltas
   `Delta*_jb` are differences of candidate replicate statistics under the
   SAME draws.
3. **Resampling-design verification (explicit):** the resampling unit (the
   SLATE DATE, `game_date`) and the fold aggregation (block-stratified
   row-weighted pooled) are explicitly identified and appropriate for the
   dependence structure: within-slate cross-row dependence is absorbed by
   resampling whole dates (multinomial over each block's original
   slate-date count), block-stratified draws fix block composition so
   block weights cannot shift across replicates, the row-weighted num/den
   pooling keeps the replicate statistic on the same per-row scale as the
   point estimate, and paired draws make every contrast replicate
   internally paired. The existing design SUPPORTS this inference; no
   validity blocker exists.
4. **Test statistic:** NULL-CENTERED APPROXIMATE BOOTSTRAP TEST. With
   observed contrast `Delta_j` and bootstrap replicate `Delta*_jb`,
   centered errors `e_jb = Delta*_jb - Delta_j`; two-sided
   `p_j = (1 + sum_b 1{|e_jb| >= |Delta_j|}) / (B + 1)` with B = 2000.
   Ties count toward the numerator via `>=`; the `B + 1` denominator is
   the finite-resample correction.
5. **Label (binding):** this is an APPROXIMATE CENTERED-BOOTSTRAP TEST,
   NOT an exact randomization test, and carries NO finite-sample-validity
   guarantee.
6. **Multiplicity:** Holm step-down across the 4 RAW Brier contrasts at
   family level 0.05 (monotone adjusted p-values); any family-level claim
   across the 4 contrasts comes ONLY from the Holm-adjusted result. The
   ordinary (unadjusted) 95% percentile intervals remain explicitly
   UNADJUSTED and are never used for a family-level claim. Log loss and
   the CAL lane are DESCRIPTIVE ONLY (no test, no claim).

**Implementation:** `comparison.py`
(`HYPOTHESIS_TEST_CONTRASTS`, `null_centered_p_value`, `holm_adjust`,
`null_centered_contrast_test`, wired into `_compute_metrics` as
`pooled_dev.hypothesis_test_brier_raw`). Synthetic verification:
`harness/test_null_centered.py` - (a) hand-computed fixture with exact
p-values including a tie case; (b) p in (0,1], non-increasing as
`|Delta_j|` moves away from the centered null; (c) symmetric null-centered
draws -> conservative (p >= 1/(B+1); large |Delta_j| -> minimal p);
(d) Holm monotonicity + family-level 0.05 respected (hand-computed);
(e) arm swap reverses the signed delta with the two-sided p unchanged;
plus runner-integration tests (all 4 contrasts registered from one shared
draw stream; absent endpoints skipped fail-safe; determinism).

## EXECUTED-RUN record (canonical scoring run) — EXECUTED 2026-10-14

Status: **EXECUTED once; outputs PRESERVED write-once; results
PRELIMINARY at serialization (2026-10-14); Chat 2 integrity review of the
score_v2 artifacts ACCEPTED 2026-10-14 (see Reviewer verdict below).** No
authorized reruns exist. No model promotion. No production
changes. The accidental 2026-10-14 ~17:15 run (C3.6) remains UNRESOLVED
and is unrelated to this executed run's evidence status.

### Provenance

| Item | Value |
| --- | --- |
| Executed code SHA | `108d5ba9ca4075017c7590a6c90e967fe3b18707` (branch `research/market-eval-v2`; descendant of pinned review snapshot `02ce162f119208b762edf1fd690edd5e7ee9b8ea`) |
| Executed scorer | `C:\Users\ckaplinger\MLB-Props-Research\market-eval-v1\market_eval.py`; sha256 `c2745980ada20c0942a811ac6e58245418a45cd8f7d83b265f17f54f834cd6c5`; committed git blob `99db556c676878aab5336989fbc7fccd9f4e31f5` (raw blob bytes hash to `c2745980...4c6c5`, so the executed file is byte-identical to the reviewed committed bytes) |
| Stale lake scorer replaced pre-run | sha256 `457991d81d44f9541dcb6a2889f35979aa0d9d844cd1ab91d57e1aea5e20e929` (pre-amendment pinned-snapshot bytes) replaced with the reviewed committed bytes above BEFORE the run |
| Execution date/time | 2026-10-14; outputs and execution log written 23:44:16-23:44:17 local (file-system timestamps; the execution log carries no in-band timestamp field) |
| Authorization provenance | the owner's "Keep moving forward" instruction plus the coordinator's bounded execution authorization: ONE canonical scoring run at the reviewed SHA. The F-4 `--i-accept-outcome-scoring` flag confirms intent to join realized outcomes only; it does not by itself constitute owner authorization. No separate explicit approval quotation exists and none is invented here. |
| Reviewer verdict | Chat 2 integrity review: ACCEPTED — SCORING-ARTIFACT INTEGRITY REVIEW + CLOSEOUT (2026-10-14, Chat 2 sole reviewer), bit-level reconciliation of all 7 score_v2 output files + execution log; findings recorded in `C:\Users\ckaplinger\MLB-Props-Research\chat2-review-overnight-20261013\market_eval\CANONICAL_FINDINGS_2026-10-14.md` (computed-at-citation sha256 `b5daea6be46d59fd1900a2e8e615e6b9d58dc2d5ef1c105c78865dd8ec462d14`, not a pre-registered digest) |
| Canonical findings hash | no separate findings digest was registered in the score artifacts (CHAT2_HANDOFF.md section 1 lists only output-file hashes); canonical identity of the accepted run = `score_manifest.json` sha256 `bc9ed9e31750f6e6ac6ad5ec7f0ed35a24b30f8098a23106c449a2d1bb0a2bd2` |

Reconstructed effective command (2026-10-15 correction, supplemental to
3fce43d; run from `C:\Users\ckaplinger\MLB-Props-Research\market-eval-v1\`):
the execution log captures no verbatim command line and carries no in-band
timestamp, so this command is RECONSTRUCTED, not captured. Its content is
established by (a) the run's outputs manifest and argument-derived paths, and
(b) the F-4 gate, which refuses `--score` without
`--i-accept-outcome-scoring`, making the flag's presence a structural fact
of the successful run:

```
python market_eval.py --score --i-accept-outcome-scoring --prep-dir outputs\prep_v2 --start-metrics "C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\data\start_metrics_v2.parquet" --score-dir outputs\score_v2 --seed 20261001 --n-boot 2000
```

**Dated correction note (2026-10-15):** `CHAT2_HANDOFF.md` section 3 quotes
the registered command line WITHOUT the F-4 flag (copied from the lake
card's score section at handoff time), so its command section needed flag
disclosure. The original handoff file is retained unchanged
(sha256 `2e050474cfebce6c98d80c8be4255fcdd53382616374942c7b989f67786e5558`,
byte-identical to the lake copy; verified 2026-10-15); this note is the
correction of record, and the reconstructed effective command above is
authoritative over the handoff's command line.

### Outputs and hashes

Output dir (write-once):
`C:\Users\ckaplinger\MLB-Props-Research\market-eval-v1\outputs\score_v2\`;
execution log: `..\score_v2_execution_log_2026-10-14.txt`. Full sha256 as
recorded in `CHAT2_HANDOFF.md`, re-verified 2026-10-15 against the
preserved bytes (all match):

| File | Bytes | sha256 |
| --- | ---: | --- |
| bets_ledger.parquet | 488,965 | `be02861afafc526e7184ac13f4825ec613c06a92209818e44f6f7c465e973b80` |
| bootstrap.json | 2,579 | `d237037bb263dbc3149013408fb7d026eb70622fb51241aa8c4c1819ec220e65` |
| clv_table.parquet | 184,576 | `78e7d8c1f3a50a54179b63f79f9461089d7345fcf5151208ad2dc1fe6a9f6559` |
| confirm_metrics.json | 1,564 | `8f052c192572e9819dabce62c1067dc6257c1aeea4e8d57ea6d1b8851993c982` |
| score_manifest.json | 376 | `bc9ed9e31750f6e6ac6ad5ec7f0ed35a24b30f8098a23106c449a2d1bb0a2bd2` |
| score_summary.json | 2,869 | `deec1c21f61a3f9827c799dccda9ecf3e234f779cd7e96623520f18a5c8c6214` |
| skill_metrics.json | 8,709 | `08c99f3997eacbbde989fbcb5e703b53a1709e9146f0ad5bf92d4b387061cba6` |
| ..\score_v2_execution_log_2026-10-14.txt | 5,826 | `7c61ff31644e203adec9c90e08675187e83d8fc89786a320a24ea3817060ed16` |

### Result-label corrections (binding reading of the outputs)

1. The 25,978-row development population is POOLED Tier A + Tier B:
   Tier A_verified_clock 14,014 side rows + Tier B_clock_proxy 11,964
   side rows (184 slate dates). Any reading of the dev headline as
   "Tier A only" is INCORRECT; the dev headline (n_rows 25,978) includes
   both tiers.
2. Tier A results are the STRICT-CLOCK lane (verified pregame clocks):
   dev Tier A Brier H3-raw 0.46727 / LOG5-raw 0.46504 / market 0.44687
   (n_rows 14,014; `skill_metrics.json` `dev.per_tier.A_verified_clock`).
   Tier B is SENSITIVITY-ONLY (proxy clocks; dev Tier B Brier H3-raw
   0.46971 / LOG5-raw 0.46785 / market 0.44684, n_rows 11,964) and stays
   sensitivity-only in every citation of these outputs.
3. No strict execution-timing claims are made beyond the established
   provenance: 2024 Tier B rows use PROXY clocks (not verified pregame
   timestamps). Only the Tier A strict-clock lane supports strict
   pregame-clock timing statements, within the limits of the
   verification bundle.
