# ARTIFACT_MAP — market-eval-v1 artifacts across the evaluation eras

**Date:** 2026-10-14. Maps the existing artifacts onto the three evaluation
eras (2023-2024 walk-forward development, 2025 frozen evaluation, 2026
disclosed evaluation) and lists what is MISSING — without assuming any new
fit is required (PREREGISTRATION_2026 + READY_BRIEF D1-D6 discipline).

## Era 1 — 2023-2024 walk-forward development

| Artifact | Path | Role | Status |
| --- | --- | --- | --- |
| Frozen PA table | `overnight-p2\data\pa_table.parquet` (sha256 `1d3be629...846aff`) | 2022-2025 PA rows; 2022 = warm-up only, never fitted | frozen |
| Feature state | `overnight-p2\data\features_v3.parquet` (sha256 `163ad433...7e8f8`) | day-d state from strictly-prior PAs; leakage_check_v3 clean | frozen |
| Walk-forward checkpoints | `overnight-p2\data\preds_block_2024H1/2024H2.parquet` | block fits: base_train -> calibration (60-day sub-block) -> assessment | frozen |
| Executed fit-key receipts | `overnight-p2\data\keys_executed_block_*.parquet` + `reports\executed_keys_summary.json` | exact base_train/calibration/assessment membership per block (deterministic replay receipts, NOT captured in-run; Chat 2 gap closed additively) | frozen |
| Ladder results | `overnight-p2\reports\ladder_results.json`, `fit_ledger.json`, `block_block_2024H*.json` | H3 8-feature logistic vs LOG5 comparator; reliability CSVs | frozen |
| Reconstructed block models | `pregame-pa-ext-v1\artifacts\h3_models_block_2024H2.joblib`, `...2025H1`, `...confirm_2025H2` | G2-verified deterministic reconstruction of the checkpoint fits (<= 1e-8 vs stored preds) | frozen |

2023 appears ONLY as walk-forward training/base-train data (the archive's
K-market quotes for 2023 exist — `board_2023_24` snapshot label — but the
payload cohort starts 2024-07-01, so 2023 is never scored in market-eval-v1).

## Era 2 — 2025 frozen evaluation

| Artifact | Path | Role | Status |
| --- | --- | --- | --- |
| Frozen confirm checkpoints | `overnight-p2\data\preds_block_2025H1.parquet`, `preds_confirm_2025H2.parquet` | 2025 assessment (H1 + confirm H2; calibration ends 2025-06-30, strictly pre-assessment) | frozen |
| Projected-state payload | `pregame-pa-ext-v1\data\predictor_payload.parquet` (sha256 `19511a49...`, 7,194 starts) | frozen per-start H3-raw/LOG5-raw K PMFs + BF PMFs for 2024-07-01..2025-12-31; **2025 portion = frozen evaluation input** | frozen |
| Market quotes + envelope | `data\Odds-Historical\theoddsapi\book_lines_pitcher.parquet`, `snapshot_envelope.parquet` | opening/pregame/closing price benchmarks; Tier A verified clock = 2025 starts (envelope commence) | frozen |
| market-eval-v1 prep (C2) | `market-eval-v1\outputs\prep_v2\` | matched contracts, actionable pairs, closing refs, paper bets, summary + manifest | write-once |
| Verification bundle | `market-eval-v1\outputs\verification\` | benchmark separation (opening/later-pregame/closing), exclusion ledger, quote-time verification | additive |
| Outcome source (SCORING ONLY) | `bf-workload-v1\data\start_metrics_v2.parquet` | realized K + persisted count-layer errors for the same 7,194 starts | frozen; NOT joined here |

Note: the 2024-07-01..2024-09-30 payload slice (2,189 starts, Tier B clock
proxy) is development-era data by date; it is carried in the same prep but
reported as a separate tier and labeled sensitivity, never pooled into a
Tier A headline.

## Era 3 — 2026 disclosed evaluation

| Artifact | Path | Role | Status |
| --- | --- | --- | --- |
| Registration | `pregame-state-v1\PREREGISTRATION_2026.md` (+ IMMUTABLE copy + acceptance receipt) | registered 2026 evaluation; single fit through 2025-12-31; sections 8-9 exclude the touched pilot population from confirmation/pooling | written, not scored |
| Seal payload (PILOT-REPRODUCTION) | `bf-2026-predictor-seal-v1\` (CLASSIFICATION.md; payload hash-pinned in the external lake) | 134-row rebuilt-recipe payload; NOT confirmatory; excluded from pooling | frozen |
| Cohort enumeration | repo `research/offseason_2026/experiments/bf-2026-cohort-enumeration-2026-10-14/` | 4,858 eligible full-season 2026 rows; only 134 have captured pregame cutoffs | frozen |
| Cohort scorer | repo `research/offseason_2026/run_bf_ab_score_cohort.py` (cohort-aware-2) | manifest-pinned scorer with membership enforcement | committed |
| Pilot diagnostic | `bf-2026-pilot-diagnostic-v1\` + DEVIATIONS.md | REBUILT-RECIPE diagnostic on the inspected pilot cohort; not confirmatory | frozen |
| Market-eval 2026 data | none | 2026 is out of scope for market-eval-v1 (no-2026-tuning rule) | — |

## Missing artifacts (each WITHOUT requiring a new fit)

1. **Registered 2026 single fit** (section 3, train window ends 2025-12-31):
   does not exist; executing it is the registered execution itself, gated on
   owner approval (READY_BRIEF D5). No threshold search is implied.
2. **Registered arm column** (raw vs calibrated) for the 2026 assessment is
   an owner decision (D2); both columns exist in the payload machinery.
3. **Payload consequence** of the single fit — rebuild the seal payload vs
   use the fit for the full-season lane only (D3).
4. **Full-season 2026 cutoff rule** — 4,724 of 4,858 rows lack captured
   pregame cutoffs; a registered cutoff rule (reconstructed scheduled first
   pitch, raw-hash-unverified) or the lane stays blocked (D4).
5. **Reporting preconditions** — chat-2 items 9.1 (paired slate-date
   uncertainty in P1, opening-day prior relabel/leakage rule over the 506
   rows, durable provenance) must be evidenced before any 2026 result is
   treated as confirmatory (D6).
6. **Verified historical pregame BF inputs for 2023-2025** — none exist
   (DOWNSTREAM_BF_INTEGRATION blocker); the market-eval BF PMFs are the
   BASE empirical per-start distribution as registered upstream, disclosed
   as such. Unblocking requires a priced vendor archive, promotion of the
   I3b hazard construction with cutoff caveats resolved, or forward-only
   persistence — none assumed here.
7. **D1 calibration-window wording** — resolved for THIS fit (both readings
   give 2025-07-31..2025-09-28); transcript pin only.
