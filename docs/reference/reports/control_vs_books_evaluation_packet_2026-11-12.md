# Current-control-versus-books evaluation packet (2026-11-12)

Bounded preparation only. No fitting, model search, calibration,
blending, or staking changes. No framework built - every stage reuses
the registered bridge, seam and scorer. NOT EXECUTED; real-data use
requires the registered market-eval gate plus a delegated owner order.

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

## 5. Existing invocation vs the ONE missing orchestration step

- **Exists (implemented, synthetic-tested, merged):**
  `market_benchmark_seam.benchmark_contract_rows` (Seam A
  `harness_model_frame` + quote funnel + book/LTBO/consensus probs +
  paired contract rows; the registered `score_starts` and
  `paired_line_scores` scorers with the slate-date bootstrap) and the
  gated `market_eval_k.run_market_eval_k` runner.
- **ONE missing step (precise):** a thin research-side runner that
  loads the pinned files and calls the existing glue, write-once:
  1. read k-PMF, assessment, cohort (the three pinned files);
  2. `observed = cpd.derive_observed_k(assessment)`;
  3. **declare start_dates from the registered
     `count_agg_eval_v1.parquet`** (it carries game_pk, side,
     pitcher, game_date, block, realized_k for the dev window;
     4,823 rows) restricted to the cohort - the seam asserts exact
     cover, so no date invention is possible (this is the only new
     wiring; the pinned PMF/assessment/cohort carry NO game_date
     column, verified footer-only);
  4. build `quotes` + `starts_bridge` via the existing
     `build_task_frames(book_lines, envelope, bf_forecasts, [MARKET],
     window 2024-07-01..2025-06-30)`;
  5. `benchmark_contract_rows(k_pmf, observed, start_dates, cohort,
     cohort_hash, arm="pmf_multinomial_control", quotes,
     starts_bridge)` -> coverage + model-vs-consensus and
     book-vs-LTBO artifacts into a fresh write-once out-dir.
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
