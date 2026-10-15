# HANDOFF_CAPABILITIES — Chat 2 questions answered from actual code

Written 2026-10-15, branch `research/market-eval-v2` @ 5bb0c2c. Evidence is
file:line from the harness (`harness/comparison.py`, this dir), the read-only
incumbent sources under `C:\Users\ckaplinger\MLB-Props-Research\`, and this
repo's `research/offseason_2026/run_paired_uncertainty.py`. Append-only.

Status vocabulary: IMPLEMENTED-VERIFIED (code exists AND an executed run or
executed test evidence pins it), IMPLEMENTED-UNVERIFIED (code exists, only
synthetic tests / no real-data execution), SPECIFIED-ONLY (registered on a map
or spec, no adapter loads/computes it), MISSING.

## 1. Which adapters genuinely FIT vs REPLAY

| candidate | answer | status | evidence |
| --- | --- | --- | --- |
| P0_log5 | REPLAY-style closed form. `fit()` returns None; `predict_proba` computes the full log5 identity on w150 priors + lg_rate. No fitting anywhere. | IMPLEMENTED-VERIFIED (log5 identity pinned by tests at tol 1e-12; no real-data run) | comparison.py:354-355 (fit -> None), 360-361, 334-344 (log5 formula); test_comparison.py:294-308 |
| P1_B_logreg | GENUINELY FITS. Adapter exists; `fit()` runs `StandardScaler().fit(X_train)` then `LogisticRegression(C=1.0, max_iter=1000).fit(...)` on base_train rows only, per fold. | IMPLEMENTED-UNVERIFIED (synthetic suite only; no real-data run — execution gate, spec section 8) | comparison.py:380-388 (fit), 548 (registration), 575 (class) |
| P1_H3_replay | **REFITS, does NOT replay stored predictions.** Despite the name, it is the same `LogisticAdapter.fit()` — a fresh 8-feature LogisticRegression fit on real training rows reproducing the incumbent fit recipe. It never reads `overnight-p2\data\preds_block_*.parquet`. "Replay" = replay of the fit PROCEDURE, not of stored preds. | IMPLEMENTED-UNVERIFIED (synthetic only; equivalence to incumbent `pred_H3_raw` preds is NOT established by any test) | comparison.py:549-550 (registration, incumbent_replay=True), 375-388 (fit calls LogisticRegression.fit); FEAT_H3 at comparison.py:62 |

Defect/nuance: the name `P1_H3_replay` invites the wrong reading (that stored
incumbent predictions are replayed). No coefficient-level or prediction-level
bit-identity check vs the executed overnight-p2 H3 preds exists; only the
assessment-row identity keys were verified bit-identical
(CANDIDATE_MAP.md:59-66). A real-data run must still prove pred equivalence
before the "replay" claim is load-bearing.

## 2. Does any implemented comparison VARY HISTORY WINDOWS?

- **H3 (EW-90d) vs H0 (cumulative w150): YES, implemented in the harness.**
  `P1_B_logreg` = the H0-equivalent (6 cumulative features, comparison.py:58-61)
  and `P1_H3_replay` = H0 + `ew_pitcher` + `ew_batter`
  (comparison.py:62). The runner loads the EW columns through
  `required_features` (comparison.py:604-609, 702-709) and the synthetic suite
  proves the H3 path fails loud when `ew_*` are absent
  (test_comparison.py:476-485). The canonical frame
  `overnight-p2\data\features_v3.parquet` carries the real `ew_pitcher` /
  `ew_batter` columns (verified by direct parquet read, 549,296 x 54).
  Status: IMPLEMENTED-UNVERIFIED on real data (no real-data run authorized).
- **H1 (last-100) / H2 (last-300): SPECIFIED-ONLY in the harness.** No adapter
  is registered for them — `registered_adapters()` contains only P0_log5,
  P1_B_logreg, P1_H3_replay + NOT-STARTED stubs (comparison.py:544-569). No
  harness code path ever loads `rec100_*` / `rec300_*`. H1/H2 exist only in the
  read-only incumbent `overnight-p2\scripts\run_ladder.py:53-57, 172-190`
  (executed there) and in the spec text
  (`COMPARISON_INTERFACE_SPEC.md:48`); CANDIDATE_MAP.md registers no H1/H2 IDs.
- Net: the harness can compare {cumulative, EW-90d} but cannot reproduce the
  H1/H2 rungs of the executed ladder without new adapters.

## 3. BF provenance: VERIFIED vs STILL MISSING

VERIFIED:
- Source artifact: `bf-workload-v1\data\bf_forecasts.parquet` (3,387,501 B),
  built by `bf-workload-v1\scripts\build_bf_forecasts.py`. Construction: per
  (game_pk, side) start, chronological expanding, 37-category add-one
  empirical PMF from the pitcher's own prior BF outcomes when prior_n >= 10,
  else the pooled league prior outcomes (build_bf_forecasts.py:145-152);
  shrunk prior mean W=50 (line 62, 141-144); history pool 2023-01-01 onward,
  2022 warm-up only (lines 14-15, 55).
- Cutoff validity: YES for scored rows, by construction — priors use the
  pitcher's prior starts with game_date STRICTLY BEFORE the start's game_date
  (lines 11-13, 126-128) and both league and per-pitcher pools update only
  AFTER all of that date's starts are forecast (lines 167-181). This answers
  the BASE-empirical-construction question: cutoff-valid, no own-date leakage.
- Scored coverage: start-level metrics were scored ONLY for assessment window
  2024-07-01..2025-12-31 against overnight-p2 preds blocks
  block_2024H2 / block_2025H1 / confirm_2025H2
  (`run_kcount_comparison.py:51-66, 119-132`; blocks list at line 303;
  correction v2 at `run_kcount_correction_v2.py:55, 131-147` ->
  `start_metrics_v2.parquet`).

STILL MISSING:
- No harness BF-lane adapter exists: B1_ridge_bf / B2_lgbm_bf /
  B3_exit_hazard are NotImplemented fail-loud stubs (comparison.py:555-565)
  and B0_bf_frozen is registered NOT-STARTED with no adapter at all
  (CANDIDATE_MAP.md:44). Nothing in comparison.py reads bf_forecasts.parquet.
- Verified BF scoring for the block_2024H1 fold (assess 2024-01-01..2024-06-30):
  PMF rows exist for those dates in bf_forecasts.parquet (covers all 2023-2025
  starts), but the kcount scoring pipeline was never run over that window —
  no start_metrics coverage. The harness fold schedule (assess from 2024-01-01)
  and the BF scored window (from 2024-07-01) do not line up.
- 2023 full-season evaluation: rows on the first league day(s) have no prior
  league history -> `pmf37` is null there (build_bf_forecasts.py:135-138,
  reported as `n_no_pmf`), so a 2023-2025 harness BF run needs an explicit
  policy for those rows; none is registered.

## 4. Projected-batter PA-probability extension (pregame-pa-ext-v1 payload)

Distinction, labeled:
- **SCORED (outside the harness):** the payload is BUILT and SCORED as a
  standalone card. `pregame-pa-ext-v1\data\predictor_payload.parquet`
  (7,194 x 155, sha256 19511a49...8a96 per REVIEW_SUPERSESSION.md:20) carries
  projected per-PA K probabilities for the projected nine-batter sequence
  (`p_h3_raw_1..9`, `p_l5_raw_1..9`) with an explicit per-start forecast
  cutoff (card.md:16-20). The count-PMF arms built from those projected probs
  were scored (rps / logscore / Brier + paired bootstraps; corrected pooled
  RMSE h3_raw 2.3234 / l5_raw 2.3219) in
  `pregame-pa-ext-v1\outputs\full_run_2\` — see
  `rmse_correction_v2\CORRECTION_NOTE.md:29-40`.
- **The realized-sequence diagnostic is a DIFFERENT artifact and consumed
  REALIZED-sequence PA probabilities:** bf-workload-v1's realized-sequence
  diagnostic (reproduced as the G3 gate in
  `pregame-state-v1\scripts\run_pregame_state_v3.py:350-399, 727`; and
  `run_kcount_comparison.py` G3) recomputes per-PA probabilities for the
  REALIZED rows from stored overnight-p2 preds, then counts realized K. That
  is a diagnostic baseline over realized sequences, not the projected-batter
  product. Do not conflate the two lineages (REVIEW_SUPERSESSION.md:3-12
  makes the same scoping point against an earlier review).
- **In the harness: PROPOSED-ONLY / not consumable.** comparison.py cannot
  ingest the payload: `load_pa_rows` requires per-PA grain
  (game_pk, at_bat_number, batter) joined to a features frame
  (comparison.py:121-165), while the payload is start-grain
  (game_pk, side) with precomputed probabilities. No adapter accepts
  probability columns as input — every PA-lane adapter computes probabilities
  from feature columns via `required_features` (comparison.py:604-609), and no
  registered candidate references the payload (absent from
  COMPARISON_INTERFACE_SPEC.md and CANDIDATE_MAP.md entirely). Consuming it
  would need a new start-grain lane (it belongs to the BF/count-PMF lane
  shape, not the PA-lane loader).

## Bootstrap: does the harness match the repaired run_paired_uncertainty method?

COPIED (ported), not imported. comparison.py imports nothing from
run_paired_uncertainty (its imports are stdlib + numpy + polars,
comparison.py:31-42); `slate_date_bootstrap` is a local re-implementation
(comparison.py:490-537) whose docstring cites the market_eval `_slate_bootstrap`
C3 repair (comparison.py:473-477).

Method equivalence to `research/offseason_2026/run_paired_uncertainty.py`
(the repaired method):
- Same estimand: row-weighted num/den over sampled-date rows
  (run_paired_uncertainty.py:18-22; comparison.py:524, 533).
- Same stratification: each replicate draws exactly each block's own slate-date
  count of dates WITH REPLACEMENT, within block, blocks then combined
  (run_paired_uncertainty.py:118-136; comparison.py:507-523).
- Same pairing: ONE draw stream shared across all arms/names
  (run_paired_uncertainty.py:8-10, 120-124; comparison.py:496-497,
  `shared_draws_across_names` at 535), seed 20261001, 2000 resamples,
  percentile 2.5/97.5 in both.

NOT bit-identical: comparison.py draws per-block date counts via
`rng.multinomial(n_dates_b, uniform, size=n_boot)` (comparison.py:519-521)
while run_paired_uncertainty.py uses `rng.integers(0, n_dates,
size=(n_boot, n_dates))` (line 123). Statistically equivalent sampling, but
the rng consumption differs, so harness CIs will not reproduce the executed
run_paired_uncertainty replicate values digit-for-digit. Label: method
MATCH (repaired), stream DIFFERENT.

## Four-status table

| capability | status | one-line basis |
| --- | --- | --- |
| P0_log5 closed-form (no fit) | IMPLEMENTED-VERIFIED | comparison.py:334-344, 354-361; identity pin tests test_comparison.py:294-308 |
| P1_B_logreg genuine fit (6-feat logistic) | IMPLEMENTED-UNVERIFIED | comparison.py:380-388 calls LogisticRegression.fit + StandardScaler.fit; synthetic tests only |
| P1_H3_replay | IMPLEMENTED-UNVERIFIED (REFITS; does NOT replay stored preds) | comparison.py:549-550, 375-388; no pred-level equivalence vs overnight-p2 preds established |
| H0-vs-H3 history-window variation (EW-90d vs cumulative) | IMPLEMENTED-UNVERIFIED | FEAT_H3 consumes ew_pitcher/ew_batter (comparison.py:62); canonical features_v3 has them; no real-data run |
| H1 last-100 / H2 last-300 harness adapters | SPECIFIED-ONLY | not in registered_adapters (comparison.py:544-569); only incumbent run_ladder.py:53-57, 172-190 |
| BF PMF artifact (bf-workload-v1, cutoff-valid, scored 2024-07-01..2025-12-31, 3 blocks) | IMPLEMENTED-VERIFIED (outside harness) | build_bf_forecasts.py:126-181 (strictly-prior pools); run_kcount_comparison.py:51-66,119-132 |
| BF scoring for block_2024H1 window + 2023 rows / B0-B3 harness adapters | MISSING | comparison.py:555-565 stubs; CANDIDATE_MAP.md:44 B0 NOT-STARTED; kcount window starts 2024-07-01 |
| Projected-batter payload built + count-scored (projected probs) | SCORED (standalone card, outside harness) | pregame-pa-ext-v1 card.md:3-8, 16-35; outputs/full_run_2; corrected RMSE note |
| Realized-sequence diagnostic (realized PA probs) | SCORED (separate lineage, do not conflate) | run_pregame_state_v3.py:350-399, 727; run_kcount_comparison.py G3 |
| Projected-batter payload consumable by harness adapters | PROPOSED-ONLY / not implemented | start-grain payload vs per-PA loader (comparison.py:121-165); absent from spec + CANDIDATE_MAP |
| Harness bootstrap = repaired block-stratified method | MATCH (ported copy, not import); draw stream differs (multinomial vs integers) | comparison.py:490-537 vs run_paired_uncertainty.py:104-136 |

## Concrete defects found

1. Misleading name: `P1_H3_replay` refits a fresh logistic; it does not replay
   stored predictions. No prediction-level equivalence gate vs the incumbent
   `pred_H3_raw` exists (CANDIDATE_MAP.md:59-66 pins only row-identity keys).
   Fix: either rename or add a real-data bit-identity gate before any claim
   that the harness "replays the incumbent".
2. Window mismatch: harness folds assess from 2024-01-01 (block_2024H1) but the
   only verified BF scoring window starts 2024-07-01
   (run_kcount_comparison.py:65-66). Any harness BF-lane run over the full fold
   schedule would extend beyond verified BF evidence.
3. Null-PMF origin rows: bf_forecasts rows on the first league day(s) have
   null pmf37 (build_bf_forecasts.py:135-138); no registered policy exists for
   them in a 2023-2025 harness BF evaluation.
4. H1/H2 registered nowhere in the harness despite being part of the executed
   ladder narrative; CANDIDATE_MAP.md has no H1/H2 IDs, so the harness cannot
   reproduce the full H0-H3 ladder without new registrations.
