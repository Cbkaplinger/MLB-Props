# Current-control-versus-books evaluation packet (2026-11-12)

Bounded preparation only. No fitting, model search, calibration,
blending, or staking changes. No framework built - every stage reuses
the registered bridge, seam and scorer. The thin orchestration wiring
is NOW IMPLEMENTED (run_control_vs_books.py, synthetic-tested); real
execution still requires the registered market-eval gate plus a
delegated owner order.

## 0. Recovery evidence reconciliation (both receipts unchanged)

- **Receipt 1 (stopped run, execution of record):** PR #86 comment
  6816558623. Refused INSIDE morning pair construction: the
  morning-scan ambiguity guard reported 3 reduced keys (chris paddack
  4.5, gavin williams 5.5, bryan woo 4.5; 2 event_ids each). Close
  screening never ran.
- **Receipt 2 (amended run, PR #87 comment 6829936974):** refused at
  the binding gate: morning+close UNION detected the same 3 keys
  (expected-only empty - all three CONFIRMED) plus a fourth,
  close-side key (2025-04-09, castillo luis, 4.5).
- **Reconciliation:** the two receipts are consistent - receipt 1
  sampled the morning scan only (the guard stopped there); receipt 2's
  union legitimately adds close-side ambiguities. No contradiction.
- **Available evidence:** the detected reduced keys + n_ev counts;
  both guards' committed code paths; the binding file; unchanged input
  hashes. **Missing evidence:** the conflicting event_ids per key
  (not persisted by either refusal), and any game-level fields
  (commence_time, home/away teams, scheduled times/game numbers) for
  those events.
- **Not claimed as duplicates:** a (gd, key) mapping to two event_ids
  is NOT called a vendor duplicate without supporting evidence - it
  could be a legitimate doubleheader listing or a vendor re-listing.
  Classification requires the minimum read below; no outcome-, price-,
  or performance-based resolution is proposed.

## 0b. Identity implementation map (canonical, cited)

- **Bridge:** odds-coverage-v1 `join_coverage.build_task_frames`
  (private card `C:\Users\ckaplinger\MLB-Props-Research\odds-coverage-v1\join_coverage.py`;
  card manifest pins book_lines `325abdf0...`, envelope `2b73bc40...`,
  bf_forecasts `c9c2762f...`, player_id_map `8a463f5c...`).
- **Name normalization:** `norm_name`/`sorted_name` in the card are a
  documented mirror of the canonical `norm_player_name`
  (src/Python/odds_ledger.py) + token-sorted key; tests:
  private `test_join_coverage.py` (TestNameNormalization,
  TestRealArchiveSmoke, 7 test classes) + repo fixtures
  `tests/test_event_player_bridge.py`.
- **Vendor event -> MLB game:** archive event_map
  (event_id, game_date, player_norm) matched to starts on the sorted
  name key with a +-1 day date tolerance (Savant LOCAL game date vs
  vendor UTC commence date); winner = closest `|date_dist|`, then
  event_id order; `unique(subset=[game_pk, pitcher])`. Duplicate
  (game_date, pitcher_key) event pairs are COUNTED
  (`archive_event_map_duplicate_keys`), never silently mixed; the
  deterministic tiebreak is disclosed.
- **Vendor player -> MLBAM:** `data/dimensions/player_id_map.parquet`
  (mlb_id -> player_name -> sorted key); unresolved names counted
  (`starts_name_unresolved_from_id_map`), never guessed.
- **Date/time evidence:** vendor game_date (UTC of commence) vs Savant
  local game_date (+-1 day tolerance, documented ET-vs-UTC artifact);
  first_pitch_ts = envelope earliest commence_time
  (`load_envelope_commence`); `has_commence` = envelope presence.
- **Ambiguity/duplicate/unmatched behavior:** duplicate (game_date,
  pitcher_key) event sets -> meta-counted, resolved by the declared
  closest-date + event_id-order rule (one deterministic winner; the
  losing event's quotes never enter the task odds); vendor players
  with no start -> excluded from odds; starts with no event ->
  has_commence False + meta count. All behavior pinned by the new
  repo fixtures (two-vendor-IDs, closest-date-wins, doubleheader,
  unmatched).
- **No second matcher was created** - the wiring and tests reuse this
  canonical bridge.

## 0c. Minimum exact read (proposal; NOT executed)

To classify the four ambiguous reduced keys (three receipt-bound +
castillo luis 2025-04-09) WITHOUT outcomes/prices:
- event_id lists per key: already-authorized book-lines rg scope
  (event_id, game_date, player_norm columns only);
- envelope columns `commence_time`, `home_team`, `away_team` for
  those specific event_ids (already-declared envelope fields);
- if still unresolved: the vendor event-index game number for those
  event_ids only (doubleheader indicator).
This is a bounded 8-event-id lookup, not a lake-wide query.

## 0d. Treatment rule (proposal, one coherent rule)

For each reduced key whose identity maps to multiple event_ids,
classify via the canonical bridge (starts match + envelope evidence):
`validated_same_game` (all conflicting event_ids map to one validated
MLB game - same (game_pk, pitcher) start, supported by identical
commence/team evidence), `conflicting_games`, or `unresolved`.
Treatment (one rule, applied to morning AND close BEFORE pair
construction): **declared exclusion with recorded classification
provenance** in every case - the panel join is reduced-key and cannot
tolerate event-level fan-out, so ambiguity at the reduced key excludes
the candidate regardless of classification; the classification
(validated_same_game vs conflicting_games vs unresolved) is recorded
as the auditable reason. No arbitrary first(), no fuzzy-score
acceptance, no silent key widening; complete denominators preserved.
(If the owner prefers, a future order could admit validated_same_game
keys through the existing duplicate-side guard - that is NOT
implemented and needs its own declared rule.)

## 0e. Prepared four-key binding amendment (baseline recovery)

`production/ops/market_research/expected_exclusions_2025H1.json` now
binds the FOUR detected reduced keys: the three receipt-1 keys (chris
paddack 4.5, gavin williams 5.5, bryan woo 4.5) plus castillo luis /
2025-04-09 / 4.5 from receipt 2's detected-only diff. Lineage and the
not-a-duplicate caveat are recorded in the file. The union-exclusion
policy is UNCHANGED; no identity guessing; no rerun under consumed
permissions - execution requires a new recorded single-run order.

## 1. Registered control PMF artifact and provenance

- **Artifact:** `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\platoon_information_v1_reproduction_20261110\k_pmf_per_start_v1.parquet`
  - 60,216 rows = 2,509 starts x 24 buckets; single row group.
  - Columns: game_pk, side, pitcher, bucket, `pmf_multinomial_control`,
    `pmf_platoon`. Schema verified footer-only this session.
- **Control arm:** `pmf_multinomial_control` - the registered 8-feature
  multinomial + pooled W0 recipe through the registered
  `start_count_pmfs` (owner ablation decision 2026-11-09: control is
  the retained baseline; challenger = 12-feature platoon).
- **Provenance:** byte-identical reproduction output of the registered
  paired comparison (platoon_information_v1; every artifact
  byte-identical, receipt_final `b1b91357...224ba`); file pin
  `8c5c849c289ecd65a561719d9ca7e9ce0975e6e0c377107fb6587c475b3a4916`;
  control-arm parity vs the accepted W0 RPS reproduced with max abs
  diff 0.0 (n=2,509; PR #79/#80 records).
- **Distinct from legacy-model predictions:** the live panel's
  `p_ours_cal`, the LightGBM bounded-selected arm, and the platoon
  challenger are NOT this control and are not used here. Only the
  declared `pmf_multinomial_control` arm enters the comparison.

## 2. Eligible matched cohort

- **Declared cohort:** `...\pregame_multiclass_baseline_v1_inputs_v2\eligible_cohort_keys_2025H1.parquet`
  - 2,509 starts (game_pk, side, pitcher); content hash
    `f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7`
    (64,746 -> 22,581 PA requests).
- **Observed K source:** `assessment_2025H1_v1.parquet` (pin
  `464fe1922c4aa3090f46b43cdce4949a888ad0c20ccd269d5c2cce671a1b80aa`;
  56,046 per-PA rows; realized K = count of registered `class_label`
  strikeout labels, via the registered `derive_observed_k`).
- The K-PMF diagnostic (count_pmf_diagnostic_v1) executed once on
  exactly these files: PASSED with 23 recorded key exclusions; the
  seam re-enforces exact cohort cover (both directions refuse).
- **Market matching narrows further:** the benchmark cohort is the
  cohort subset with two-sided near-close quotes; coverage, LTBO-
  unavailable counts and exclusions are recorded by the seam.

## 3. Model-input cutoff (timing the comparison can actually support)

- The control PMF's inputs are **strictly-prior pregame states**
  (completed-start history + pregame PA states built from CONFIRMED
  lineups in the pinned assessment construction).
- **Morning (T-5h) input availability is UNESTABLISHED for 2025H1:**
  `pregame_lineup_capture.py` has no committed 2025H1
  morning-coverage record; later confirmed lineups are not morning
  inputs.
- Therefore the proposed comparison is labeled a **NEAR-CLOSE
  BENCHMARK COMPARISON** at the registered near-close contract
  (below). It is explicitly **NOT a morning T-5h trading replay**, and
  nothing in it supports morning decision-time claims.

## 4. Book/consensus contract and timestamps (registered, reused)

- **Quotes:** paid lake `book_lines_pitcher.parquet` + `snapshot_envelope.parquet`
  through the existing join context (`build_task_frames`), dev window
  2024-07-01..2025-06-30 (confirm_2025H2 excluded), own-player filter
  (`verified_odds_for_start`), then `select_near_close`:
  - **tier A** (vendor commence present): latest quote at or before
    `first_pitch_ts` within `CLOSE_WINDOW_MIN` = 60 min;
  - **tier B** (no local commence, 2024 events): vendor `close`
    snapshot, latest `snapshot_ts`;
  - conflicting tied quotes (same identity+timestamp, different
    price) are dropped AND counted, never selected.
- **Book arm:** two-sided multiplicative de-vig per
  (start, book, line) via the registered `devig_over`.
- **LTBO consensus:** median of the OTHER books' de-vigged over
  probabilities at the SAME line; >= 2 other books required, else
  recorded unavailable (never filled).
- **All-book consensus:** registered `consensus_over_probs` (line
  with most two-sided books; ties -> closest to median quoted line).
- One-sided ladders are never converted into PMFs; no model PMF is
  inferred from a single line.

## 5. Orchestration wiring (now implemented; was the ONE missing step)

- **Exists (implemented, synthetic-tested, merged):**
  `market_benchmark_seam.benchmark_contract_rows` (Seam A
  `harness_model_frame` + quote funnel + book/LTBO/consensus probs +
  paired contract rows; the registered `score_starts` and
  `paired_line_scores` scorers with the slate-date bootstrap) and the
  gated `market_eval_k.run_market_eval_k` runner.
- **IMPLEMENTED THIS PR (the one missing step):**
  `research/offseason_2026/pregame_pa_ext/run_control_vs_books.py` -
  a thin, gated, write-once runner that (1) validates EVERY required
  argument (ack, fresh out-dir, existing book-lines/envelope) BEFORE
  output creation or frame decoding, (2) hash-pins and loads the
  registered files (k-PMF `8c5c849c...`, assessment `464fe192...`,
  count_agg_eval dates `afc94ad7...`; cohort content-checked
  downstream), (3) derives observed K via the registered
  `derive_observed_k`, (4) declares start_dates from
  count_agg_eval_v1 restricted to the cohort (seam asserts exact
  cover - no date invention), (5) builds quotes + starts_bridge via
  the registered `build_task_frames` (dev window
  2024-07-01..2025-06-30), (6) calls `benchmark_contract_rows` with
  `arm="pmf_multinomial_control"` ONLY. Execution-ack
  `EXECUTE-CONTROL-VS-BOOKS-V1`.
- **Output discipline (tested):** tables persist as parquet via the
  registered atomic write (`benchmark_model_rows/consensus/
  book_probs/ltbo.parquet`); scores/coverage persist as
  `benchmark_summary.json` through an explicit fail-loud converter -
  `default=str` NEVER serializes scientific results (numpy scalars
  convert to Python scalars; unknown types REFUSE).
  `receipt_final.json` is written LAST, only after every declared
  output succeeded; the synthetic output-failure test proves a failed
  write leaves `failure_record.json` and never a completed receipt.
- **Consumed identities (receipt-final, actual):** cohort content
  hash (registered recipe), pinned artifact hashes, book_lines/
  envelope/workload sha256, private bridge source sha + card
  manifest sha (existing provenance machinery reused; no new
  registry). Timing + identity contract recorded in every output
  (`TIMING_CONTRACT`): commence semantics, near-close interpretation
  and its confirmed-lineup limitation, and the declared per-mapping
  tie-break gap.
- **Remaining unknown:** whether the canonical id-map bridge resolves
  every cohort start to a game_date (cohort âŠ† count_agg_eval_v1) -
  the seam's exact-cover assertion answers it on first real run and
  the runner records the failure receipt if not.
- No new evaluation code path beyond that ordered call list.

## 6. Required access and expected outputs

- **Access (all local, read-only):** the three pinned registered
  files (full-file, hash-pinned); `count_agg_eval_v1.parquet`
  (dates columns); paid book_lines + envelope under the REGISTERED
  market-eval join (dev window, near-close rules); the workload
  `bf_forecasts.parquet` starts table. No Friend, no network, no
  model artifacts, no live-path file.
- **Expected outputs (write-once directory):** receipt_initial /
  receipt_final / failure_record; quote funnel (total -> attached ->
  own-player -> near-close selected); book/LTBO/consensus coverage
  incl. ltbo-unavailable counts; model-vs-consensus scores
  (registered log loss/Brier/RPS definitions + paired slate-date
  bootstrap); book-vs-LTBO paired line scores; probability-
  disagreement (book vs LTBO) reported separately from outcomes.
- **Interpretation boundaries:** model-only and market-only results
  stay separate; no complementary-side pooling as independent bets;
  no model-edge or profitability claim; closing quotes are
  benchmark-only, never decision inputs.
- **Timing label (mandatory):** NEAR-CLOSE BENCHMARK COMPARISON -
  market quotes at the registered near-close cutoff; model inputs
  are strictly-prior pregame states whose morning-decision-time
  availability is unestablished for 2025H1. This packet does NOT
  constitute a morning T-5h trading replay and must not be cited as
  one.

---

# PACKET B OWNER-DECISION BRIEF (2026-11-12; appended after Packet A completion)

Packet B remains UNAUTHORIZED. This brief consolidates the decision material
only; the runner is already built and accepted (no new features were added
to prepare this request).

## B.1 The question

Does the REGISTERED current control (8-feature multinomial + pooled W0,
arm `pmf_multinomial_control`) improve on near-close book quotes and the
LTBO consensus at forecasting the realized full-start over outcome? Paired
log loss / Brier (registered 1e-12 clip definitions) with the slate-date
bootstrap; probability disagreement (book vs LTBO) reported separately from
outcome scoring. Model-only and market-only artifacts stay separate; no
complementary-side pooling; no model-edge or profitability claim.

## B.2 Exact runner/code identity

- Runner: `research/offseason_2026/pregame_pa_ext/run_control_vs_books.py`
  at accepted head `735bb5485560d1773ffc193d10733e5d61440f86` (integrated
  main `aa61986d3d8d818c758a56ae75e64176299cb8ee`; verified identical).
- Gate: `--execution-ack EXECUTE-CONTROL-VS-BOOKS-V1` + write-once receipts
  + delegated owner order (the registered market-eval lane's gate discipline).
- Receipt discipline: tables as parquet (atomic write); scores/coverage as
  fail-loud JSON (never default=str); `receipt_final.json` written LAST
  (output-write failure test proves no completed receipt on failure).
- Consumed identities recorded in the receipt: cohort content hash
  (registered recipe), pinned artifact hashes, book_lines/envelope sha256,
  private bridge source sha + card manifest sha.

## B.2a Command (exact; AMENDED policy - supersedes the consumed invocation, which is preserved, not erased)

**Permission status:** attempt 1 (exact-cohort policy, `control_vs_books_v1`) was EXECUTED once and REFUSED at the exact-cohort coverage gate (2,509 -> 2,154; 355 cohort starts lack an all-book near-close consensus; receipt PR #91 comment 6862633285). That permission is CONSUMED. Any rerun under the amended shared-population policy below requires a NEW recorded owner order.

```
python research/offseason_2026/pregame_pa_ext/run_control_vs_books.py --execution-ack EXECUTE-CONTROL-VS-BOOKS-V1 --out-dir "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\control_vs_books_v2" --book-lines "C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Odds-Historical\theoddsapi\book_lines_pitcher.parquet" --envelope "C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Odds-Historical\theoddsapi\snapshot_envelope.parquet" --consensus-policy shared_population
```

Policy semantics (`--consensus-policy shared_population`, opt-in; default refusal unchanged): model-vs-consensus scored ONLY on the declared shared population; the ORIGINAL 2,509-start cohort remains the coverage denominator (`coverage.consensus_shared_population.cohort_denominator`); matched/unmatched start keys + reason codes (`no_near_close_quotes` / `no_two_sided_quote_at_any_line` / `consensus_unavailable_other`) are durably persisted BEFORE scoring via a membership sink (a scorer failure cannot lose the coverage evidence - tested with a synthetic scorer failure); ZERO matched coverage is a CONTROLLED REFUSAL (explicit no-score result, never silent empty scoring); complete coverage produces explicit accounting (`complete_coverage: true`); book/LTBO populations stay separate with per-book denominators. The policy value is validated at the seam boundary, and the selected policy is recorded in the INITIAL receipt (visible on failed attempts too).

## B.3 Inputs, actual access, and protected exposure (honest decoding facts)

- **Pinned registered artifacts (full-file reads, byte-pinned, hash-enforced
  at run time):** k-PMF control artifact `8c5c849c...`; assessment
  `464fe192...`; count_agg_eval_v1 dates `afc94ad7...`; eligible cohort
  (content hash `f77d7a66...` enforced by the registered validator).
- **Private bridge (build_task_frames, odds-coverage-v1 `join_coverage.py`):
  ALL of the following are FULL-FILE EAGER reads - `pl.read_parquet` then
  in-memory filtering. The declared 2024-07-01..2025-06-30 window is an
  in-memory filter, NOT pre-decode protection, and must not be described as
  such:**
  - `book_lines_pitcher.parquet` (4,025,730 rows): projected quote fields
    decoded for ALL years INCLUDING protected 2025H2/2026 quote rows,
    transiently, filtered in memory;
  - `snapshot_envelope.parquet` (14,531 rows): commence timestamps for all
    years transiently decoded;
  - workload starts `C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\data\bf_forecasts.parquet`
    (task/forecast table; no outcome columns);
  - `data\dimensions\player_id_map.parquet` (identity bridge; actually
    consumed).
- The universe_panel_live panel is NOT consumed by Packet B (model
  probabilities come from the pinned k-PMF artifact; `p_ours_cal` never
  read).
- No Friend CSV, no network, no live-path file.

## B.4 Timing and identity limitations

- The comparison is the NEAR-CLOSE BENCHMARK contract (tier A: latest
  quote at or before the start's commence within 60 minutes; tier B:
  vendor close snapshot). It is NOT a morning trading replay.
- Envelope `commence_time` is the vendor-scheduled commence - NOT an
  observed first pitch.
- A near-close label does NOT establish that confirmed-lineup model inputs
  existed before every selected quote: model inputs are strictly-prior
  pregame states and 2025H1 morning decision-time availability is
  unestablished.
- The event->game mapping tie-break (closest date, then event_id order) is
  NOT independent identity validation; aggregate tie-break counts exist
  (`archive_event_map_duplicate_keys`), per-mapping
  uniquely-supported-vs-tie-broken status is NOT carried by existing
  metadata (declared gap, recorded in the receipt).

## B.5 Fresh output directory and stop conditions

- AMENDED: `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\control_vs_books_v2`
  - must NOT pre-exist (write-once; failure records preserved, receipt
    final written LAST only after all declared outputs succeed). The
    consumed `control_vs_books_v1` directory (receipt_initial +
    failure_record from the refused attempt 1) is PRESERVED untouched.
- Stop conditions: ack mismatch; existing out-dir; missing/nonexistent
  --book-lines/--envelope; pinned-artifact hash mismatch; cohort exact-
  cover refusal; duplicate quote/consensus identity; consensus
  shared population EMPTY (zero matched -> controlled no-score refusal);
  model-rows-lost-in-join refusal (refuse policy); protected/unknown
  block refusal; unknown consensus_policy value (seam-boundary
  validation); any runtime failure -> `failure_record.json` preserved,
  no completed receipt, ONE run, no repair-and-rerun.

## B.6 Packet A reconciliation (verified)

Packet A is EXECUTED (exit 0) and CLOSED; single-run permission consumed.
Preserved artifacts + receipt: PR #90 comment 6861125006 (locations) and
6861289910 (artifact index for Chat 2's verification): baseline parquet
`e4348d3b...`, report `18cd418d...`, policy-tagged integrity sidecar
`53b989e0...`; preserved pre-#90 diagnostic `c590d3b6...` untouched.
No further Packet A runs.

---

# PACKET C PRE-REGISTERED DIAGNOSTIC (prepared 2026-11-13, definitions amended same day; NOT executed; no owner order yet)

Question: does the frozen control exhibit DIRECTIONAL DISAGREEMENT
(model minus consensus) or EXCESS PROBABILITY EXTREMITY (distance from
0.5) relative to the consensus on the existing 2,154 paired starts?
Descriptive diagnostic only - no fitting, no calibration fitting, no
tuning, no subgroup search, no model change, no protected-data access,
no lake query.

## C.1 Exact saved inputs and hashes (read-only; already preserved)

- `...\diagnostics\control_vs_books_v2\benchmark_model_rows.parquet`
  sha256 `1c0e7f4e3a83608fb0315b5ac4ca421ac4b3096e2ea63661e7dcda377d5de075`
  - one row per matched start (n = 2,154); columns: game_pk, side,
    pitcher, game_date, block, realized_k, line, pmf_baseline
    (24-bucket registered PMF), p_over (consensus de-vigged over
    probability), n_books.
- `...\diagnostics\control_vs_books_v2\benchmark_summary.json`
  sha256 `2fee0f1dcc2a3ee076434235fec16973dae2ee1985fbb3ad3f0b5012e6b5bce6`
  - contains the already-computed MODEL reliability decile buckets
    (registered fixed bins).
- Receipts for provenance: receipt_initial/receipt_final in the same
  directory (identity chain verified by Chat 2, PR #92 comment
  6866986855).

## C.2 Required columns and actual access

- Read-only of the two preserved files above (NO lake query, no
  book_lines/envelope/panel/bridge access - the diagnostic is
  self-contained on Packet B's saved outputs).
- Model over probability RECOMPUTED from the preserved pmf_baseline via
  the registered `market_eval_k.model_p_over` (existing helper;
  half-line tail semantics) - no new math.
- Consensus over probability is already a column (`p_over`).

## C.3 Fixed summary definitions (pre-registered before any run)

- Paired row = one matched start; equal weight; n = 2,154; no
  covariates, no subgroups, no filtering beyond the preserved rows.
- Outcome label: y = 1{realized_k > line} (binary over win at the
  quoted line), recomputed from the preserved realized_k + line.
- signed_diff = model_p_over - p_over (consensus). Report mean,
  median, sd, min, max of signed_diff (DIRECTIONAL DISAGREEMENT,
  model minus consensus; percentage points x100 also reported).
  SIGN CONVENTION: positive signed_diff means the model rates the
  over HIGHER than the consensus on that row.
- mean(p - y) per source, on the EXACT same saved rows (y as defined
  above; model p = model_p_over, consensus p = p_over). SIGN
  CONVENTION: positive mean(p - y) means the source's over
  probabilities EXCEED the realized over frequency on this population
  (a descriptive statement about THIS sample; it is NOT by itself a
  calibration claim, which would require the reliability structure
  below plus an inference framework this diagnostic deliberately
  omits).
- extremity_model = mean(|model_p_over - 0.5|); extremity_consensus =
  mean(|p_over - 0.5|); extremity_delta = extremity_model -
  extremity_consensus; plus the share of rows with |p - 0.5| >= 0.25
  for each source (fixed threshold, declared, no search). EXTREMITY
  is DISTANCE FROM 0.5 - a descriptive spread measure; a larger
  extremity is NOT proof of overconfidence (that would require the
  reliability structure plus an inference framework, deliberately
  omitted here).
- Reliability: the EXISTING registered 10-bucket reliability recomputed
  for BOTH sources over the SAME rows, using the SAME model-probability
  decile assignment for both. This is a PAIRED MODEL-BINNED diagnostic
  (bins defined by the model's own probability deciles) - it is NOT a
  consensus-calibration assessment and must not be described as one.

## C.4 Fresh output destination (if outputs are proposed)

- `...\diagnostics\control_vs_books_v2_bias_diagnostic\` - write-once,
  must NOT pre-exist; the v2 directory and all Packet A/B artifacts
  stay untouched. Outputs: one `directional_disagreement_extremity_summary.json`
  (fixed definitions + counts) and one
  `paired_model_binned_reliability.parquet` (paired model-binned
  reliability rows).

## C.5 Executable/script identity (IMPLEMENTED 2026-11-13; not executed)

- Script: `research/offseason_2026/pregame_pa_ext/run_packet_c_diagnostic.py`
  (acked write-once runner; ack `EXECUTE-PACKET-C-DIAGNOSTIC-V1`).
  It implements EXACTLY the C.3 definition set: registered
  `market_eval_k.model_p_over` (half-line tail) for model p_over;
  directional disagreement (mean/median/sd[ddof=0]/min/max + pp);
  mean(p-y) per source; extremity (mean |p-0.5|, delta, fixed 0.25
  shares); paired model-binned table using the registered
  `score_starts` decile-edge derivation ([lo, hi), -inf/+inf, empty
  buckets omitted) applied to BOTH sources.
- Invocation: `python research/offseason_2026/pregame_pa_ext/run_packet_c_diagnostic.py --execution-ack EXECUTE-PACKET-C-DIAGNOSTIC-V1 --out-dir <fresh write-once dir>` (default declared out-dir per C.4).
- Receipt discipline: hash/schema validation BEFORE any output; receipt_initial -> outputs -> receipt_final LAST; failure_record on any error.
- The script's own SHA is published with the delivery; it has NEVER
  been run on the real preserved artifacts (no owner order yet).## C.6 Limitations and stop condition

- Descriptive diagnostic on the consensus-COVERED 2,154-start subset
  (selection caveat inherited from Packet B); NEAR-CLOSE tier A/B
  timing; commence = vendor-scheduled; no morning-validity, holdout,
  profitability or promotion interpretation.
- Stop conditions: destination exists; any preserved-artifact hash
  mismatch vs the recorded receipt; column/schema mismatch; runtime
  failure -> failure record, no completed receipt, one run, no
  repair-and-rerun. Requires a new recorded owner order before
  execution (this handoff authorizes PREPARATION only).

---

# MODEL-ONLY EXPERIMENT PROPOSAL (2026-11-13; PREPARED ONLY - no owner order, no execution, no implementation)

ONE changed component, pre-registered as a proposal for the owner's
decision. No tournament, no feature/window search, no calibration, no
new framework, no data execution. If the owner rejects the component,
this proposal records that the existing evidence was judged
insufficient - nothing is invented.

## P.1 Evidence base (all VERIFIED, already in the repository)

- Packet B (VERIFIED): on the 2,154-start shared population the
  registered control is worse than the near-close consensus: paired
  log-loss delta +0.026786, CI95 [+0.01727, +0.03672], Holm p 0.0005,
  decision model_not_better_than_close; Brier delta +0.011147.
- Packet C (VERIFIED): the control's extremity (mean |p-0.5| 0.0902)
  is ~1.8x the consensus (0.0488); in the MODEL's own outer deciles
  the realized over rates (0.440 bottom / 0.500 top) diverge from the
  model's bin means (0.307 / 0.708; mean(p-y) -0.132 / +0.208) while
  the consensus tracks observed rates closely in the SAME bins
  (~0.447-0.530 mean vs 0.44-0.56 observed).

## P.2 Existing controls that the experiment reuses (identified)

- PA controls: registered assessment-derived labels (realized K =
  count of class_label == 0 per start, registered
  derive_observed_k); per-PA identity (game_pk, side, pitcher,
  at_bat_number, batter); registered norm_player_name/sorted-key
  identity bridge.
- Workload controls: registered bf_forecasts workload
  (BF_WORKLOAD_DIR); pooled-league W0 prior (BF37) through the
  registered `start_count_pmfs`.
- Aggregation controls: registered 24-bucket K-PMF aggregation
  (`adapter.count_pmf_from_mixture`; K_MAX = 24, tail bucket 23);
  m0_multiclass 8-feature multinomial recipe (the control arm
  `pmf_multinomial_control`, bit-exact reproduction receipt
  b1b91357...224ba / 8c5c849c...).
- Paired-score controls: market_eval_k.score_starts,
  paired_line_scores, cmp_bootstrap (seed 20261001, 2,000 reps,
  Holm m=1); the Packet B seam (benchmark_contract_rows) with the
  shared-population policy; Packet C's fixed diagnostic summaries.

## P.3 The ONE changed component and hypothesis

- Component: the pooled-prior STRENGTH in the registered count
  aggregation - the W0/BF37 weight that shrinks pitcher-specific
  count evidence toward the pooled league mean inside
  `start_count_pmfs`. NOTHING else changes: same 8 features, same W0
  mixture composition, same 24-bucket aggregation, same frozen
  pipeline, no calibration of outputs.
- Hypothesis (specific, falsifiable): the control's unsupported
  extremity (Packet C) reflects INSUFFICIENT shrinkage of
  pitcher-specific count evidence toward the pooled mean. A stronger
  declared prior weight produces a less extreme PMF whose over
  probabilities pair better with realized outcomes - i.e., it reduces
  extremity toward (not past) the consensus range and closes a
  material part of the +0.0268 paired log-loss deficit WITHOUT using
  any market information.
- Why this experiment can change the decision: the component is the
  ONLY registered knob that directly targets the measured failure
  mode (unsupported extremity) and it is model-internal - if
  strengthening the prior closes the deficit, the control's market
  gap is a shrinkage artifact and the fix is a one-parameter
  model change; if it does NOT close, the deficit lives in the
  feature/recipe layer and prior-strength tuning is excluded from
  the decision space. Either outcome changes what we do next.
- Explicit honesty: Packet C shows WHERE the miscalibration pattern
  sits (extremity in the model's own outer deciles) but NOT WHICH
  component causes it. The prior weight is the most direct
  registered hypothesis; the experiment tests it rather than
  assuming it. The alternative's magnitude must be pre-registered as
  a SINGLE value (e.g., a doubled BF weight) chosen WITHOUT reference
  to the Packet C rows - it is a design choice, not an
  evidence-derived fit.

## P.4 Experiment contract

- Target: full-start K distribution (24-bucket PMF) -> over
  probability at quoted lines.
- Prediction unit: per-start paired rows, equal weight; model-vs-
  consensus on the declared shared population; book/LTBO untouched;
  ORIGINAL 2,509-start cohort as coverage denominator.
- Decision time: NEAR-CLOSE benchmark timing (registered tier A/B) -
  identical to Packet B; NOT a morning-decision claim.
- Cohort: registered 2,509-start 2025H1 eligible cohort (content
  hash f77d7a66...); shared population disclosed (expected ~2,154/355
  with reason codes, not assumed).
- Input availability: strictly-prior pregame states, identical to the
  registered control's contract; NO market information enters the
  model arm.
- Training/evaluation windows: the registered control recipe's
  windows (unchanged; reconstruction gate must reproduce the
  existing control arm exactly at the unmodified weight - max abs
  diff 0.0 convention - before the alternative arm is scored);
  evaluation window 2025H1 only; 2026 stays closed.
- Frozen components: 8-feature recipe, W0 mixture composition,
  aggregation code, calibration NONE, the entire market seam and
  scorer stack; ONLY the prior-weight parameter differs between the
  control arm and the new arm.
- Paired scores: the registered harness (log loss/Brier with 1e-12
  clip, Count-RPS, slate-date bootstrap seed 20261001 / 2,000 reps /
  Holm) on identical realized outcomes; Packet C's directional-
  disagreement/extremity summaries as pre-registered diagnostics to
  confirm the mechanism (extremity should DROP in the new arm).

## P.5 Implementation gap, permissions, stop condition

- Implementation gap (exact): (1) one new arm in the registered
  count-aggregation lane computing the PMFs at the declared
  alternative prior weight (reuses start_count_pmfs; ~a parameter +
  a runner); (2) wiring that arm into the existing Packet B seam call
  as the scored arm (the seam already accepts keyed PMF frames; the
  runner needs an arm-path argument). No new framework, no scorer
  changes.
- Permissions needed: (a) implementation order (synthetic tests only;
  no real-data run); (b) ONE real-data execution order for the paired
  benchmark (write-once, fresh destination, all Packet B stop
  conditions).
- Stop condition: ONE run; existing destination, hash/binding
  mismatch, coverage-gate refusal, any unresolved multiplicity class,
  runtime failure -> preserve evidence, no repair-and-rerun. If the
  alternative arm fails its reconstruction gate or the paired delta
  is inconclusive, the result is recorded and the component is
  excluded from the decision space - no iteration on the weight under
  the same order.

---

# PRIOR-STRENGTH KNOB TRACE (2026-11-13; code-verified - PROPOSAL WITHDRAWN)

Traced the registered control from its artifact producer through the
aggregation chain, with exact paths/signatures/equations. RESULT: the
proposed "pooled-prior-strength scalar" DOES NOT EXIST; the proposal
is withdrawn as specified. No replacement knob (W_PRIOR, workload
tempering, output calibration) is proposed without a new explicit
scientific contrast.

## T.1 The chain (exact paths, signatures, equations)

1. **Keyed PA probabilities (per-PA p9):**
   `research/offseason_2026/pregame_pa_ext/adapter.py` -
   `apply_h3_raw(pf, model)` per checkpoint block writes `p_h3_raw`
   (and `p_l5_raw`); the control arm consumes the NINE per-PA
   probabilities `p9_h3` from the registered 8-feature multinomial
   (`m0_multiclass.FEATURES`; training/fitting in the m0 lane).
2. **W0/BF37 workload construction:**
   `research/offseason_2026/pregame_pa_ext/workload_comparison.py` -
   `_pooled_bf37_at(pa: pl.DataFrame, cutoff) -> np.ndarray`
   (EXACT equation: pooled histogram of outing batters-faced `v`
   over first-pitcher-of-record game-halves strictly before the
   cutoff, then `(counts + 1.0) / (counts.sum() + 37.0)` - ADD-ONE
   smoothing; cold start returns uniform 1/37). Each cutoff yields
   ONE 37-vector. W0 = this pooled BF37 per cutoff.
3. **BF37 -> N-distribution:**
   `research/offseason_2026/kcount_combiner.py` -
   `bf_pmf_from_37(bf_pmf37: np.ndarray, cap: int = KCOUNT_CAP) ->
   np.ndarray` (also aliased via adapter): maps the 37-category
   workload PMF to the 1..60 N-distribution; index 36 = P(N>=37),
   redistributed over 37..60 by a geometric tail with per-step ratio
   = mean hazard of entries 31..36 (frozen approximation).
4. **start_count_pmfs:**
   `research/offseason_2026/pregame_pa_ext/adapter.py` -
   `start_count_pmfs(p9_h3: np.ndarray, p9_l5: np.ndarray,
   bf37: np.ndarray) -> dict`:
   `bf_ext = bf_pmf_from_37(bf37)`; `pbar = cycled_cond_mean(p9)`
   (cycled prefix mean of the nine per-PA probs, clipped to
   [P_CLIP, 1-P_CLIP]); per arm.
5. **count_pmf_from_mixture:**
   `research/offseason_2026/pregame_pa_ext/adapter.py` -
   `count_pmf_from_mixture(bf_ext: np.ndarray, pbar_n:
   np.ndarray) -> np.ndarray`:
   `P(K=k) = sum_n P(N=n) * Binom(k; n, pbar_n)` (24 buckets, tail
   absorbed into k=23).

## T.2 Answers

1. **What W0 means:** the pooled BATTERS-FACED distribution - the
   probability distribution of outing LENGTH N (number of batters
   faced by the first pitcher of record in a game-half), estimated
   across all qualifying outings before the cutoff. It is the
   WORKLOAD prior over N inside the binomial mixture - NOT a
   shrinkage prior over the strikeout probability.
2. **What each BF37 entry represents:** entry j (j = 0..36) is the
   probability that an outing comprises exactly j+1 batters faced
   (entry 36 = P(N >= 37), redistributed by the registered tail).
3. **Does a separate pooled-prior-strength scalar exist?** NO. The
   only shrinkage constant in the W0 construction is the HARDCODED
   add-one (`counts + 1.0`, denominator `+ 37.0`) inline in
   `_pooled_bf37_at` - a Dirichlet(alpha=1) posterior mean, part of
   the REGISTERED IDENTITY (binary_k_comparison imports
   `wcmod._pooled_bf37_at` rather than re-implementing it "so the W0
   control reconstruction is exact by identity"; reconstruction gates
   pin the accepted-W0 RPS within 1e-12). There is no tunable
   prior-strength parameter, no W_PRIOR, no exposure scalar.
4. **Where genuine shrinkage enters the control:** (a) the per-PA
   probabilities p9 themselves - outputs of the frozen 8-feature
   multinomial (m0_multiclass; a MODEL, not a scalar); (b) the
   cycled prefix-mean in `cycled_cond_mean` with `P_CLIP` bounds
   (registered constants, not a tunable prior); (c) the binomial
   mixture itself, whose "pull toward the middle" comes from
   integrating over N, not from a strength parameter. None of these
   is an adjustable pooled-prior-strength scalar.

## T.3 Proposal withdrawal and causal-claim correction

- The proposed mechanism ("insufficient shrinkage of pitcher-specific
  count evidence toward the pooled mean") was WRONG: the pooled mean
  in the mixture is the workload N-distribution; extremity of p_over
  comes from the per-PA probabilities p9 and their cycling, not from
  the BF37 prior. Changing the (nonexistent) prior strength was
  never possible; changing the add-one constant would alter the
  registered workload identity (breaking the 1e-12 reconstruction
  gates) and was never a sanctioned knob.
- DEVELOPMENT-INFORMED SELECTION DISCLOSED: the component was chosen
  BECAUSE of the Packet C diagnostic measured on the SAME 2025H1
  rows that the experiment would have evaluated - the selection was
  in-sample, and the proposal's causal success/failure claims
  (deficit closes / lives elsewhere) are WITHDRAWN.
- Consequence: no experiment is proposed. The verified Packet B/C
  findings stand as diagnostics. Any future component experiment
  requires a NEW explicit scientific contrast with a mechanism
  traceable through THIS chain (e.g., at the p9/multinomial layer),
  developed without reuse of the 2025H1 diagnostic as its training
  signal.
