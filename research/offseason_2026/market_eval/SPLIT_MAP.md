# SPLIT_MAP — actual implemented splits, per lane, per artifact

**Date:** 2026-10-14. Maps the splits the implemented code actually used
(as evidenced by executed receipts and frozen outputs), not aspirational
design. Three lanes are kept separate end to end. Market-matched subsets
are SUBSETS of the forecast-evaluation cohort (the same 7,194-start
population after identity/coverage exclusions) — they are NOT new splits.

## Lane 1 — PA / projected-state (overnight-p2 walk-forward -> payload)

Fit discipline (executed_keys_summary.json, run identity
`6a62d8ed...6def2`): base model + scaler fit on base_train rows ONLY;
calibrator (sigmoid) fit on the final 60-day calibration sub-block;
assessment strictly after calibration. 2022 PAs (182,051 rows) exist ONLY
in pa_table as strictly-prior feature state — zero rows before 2023-01-01
in any base_train (`rows_in_base_train_before_2023 = 0` in every block).

| Block | base_train (dates / PAs) | calibration (dates / PAs) | assessment (dates / PAs) | Role |
| --- | --- | --- | --- | --- |
| block_2024H1 | 2023-03-30..2023-08-02 / 123,081 | 2023-08-03..2023-10-01 / 61,023 | 2024-03-28..2024-06-30 / 94,458 | DEV (walk-forward development) |
| block_2024H2 | 2023-03-30..2024-05-01 / 219,078 | 2024-05-02..2024-06-30 / 59,484 | 2024-07-01..2024-09-30 / 87,808 | DEV |
| block_2025H1 | 2023-03-30..2024-08-01 / 306,791 | 2024-08-02..2024-09-30 / 59,579 | 2025-03-18..2025-06-30 / 95,357 | DEV 2025H1 |
| confirm_2025H2 | 2023-03-30..2025-05-01 / 401,590 | 2025-05-02..2025-06-30 / 60,137 | 2025-07-01..2025-09-28 / 87,569 | EVAL / confirm — **INSPECTED CONFIRMATION** |

- 2022 = warm-up only (never fitted; feeds league/rolling histories).
- 2023+ = fitted (every base_train starts 2023-01-01; first eligible
  PA date 2023-03-30).
- Executed membership receipts: `overnight-p2\data\keys_executed_block_*.parquet`
  + `reports\executed_keys_summary.json` (sha256
  `6c831a5e...0993996009d`); preds parquets sha256-pinned in
  BUNDLE_EXTRACTION section 3; reconstructed block models verified <= 1e-8
  vs stored preds (G2).
- **2025H2 is labeled INSPECTED CONFIRMATION**: its outcomes/preds have been
  looked at during development reporting; it is the confirm block for the PA
  payload but must not be re-treated as untouched holdout.

## Lane 2 — count layer (realized-sequence diagnostic population)

- Population: **7,194 starts** (bf-workload-v1 `start_metrics_v2.parquet`,
  key (game_pk, side, pitcher) unique; cohort 2024-07-01..2025-09-28;
  realized_k range 0..15).
- Persisted count errors `base_h3_*` / `base_l5_*` (rps, logscore,
  rmse_mean_k, brier_ge6/8/10/12) were computed upstream against realized
  sequences and are **REUSED verbatim** by the market-eval scorer — never
  recomputed (market_eval.py `PERSISTED_COUNT_COLS`).
- Status: computed + inspected diagnostic population (the errors exist and
  are read); it is NOT a training population for the market lane and NOT a
  fresh split.

## Lane 3 — market layer (prep_v2; outcome-free; scoring still gated)

From `outputs\prep_v2\` (C2, write-once, bit-reproducible) and
`outputs\verification\`:

| Quantity | Value |
| --- | ---: |
| Cohort starts (payload, 2024-07-01..2025-09-28) | 7,194 |
| Eligible after identity exclusions (62 unresolved + 294 unmatched + 25 doubleheader-ambiguous) | 6,813 |
| Starts with >=1 actionable quote | 6,647 |
| **Usable paired-contract starts** | **6,643** |
| Paired (start, line, book) actionable pairs | 59,636 |
| **Eval observations (start, line)** | **20,004** |
| Contract side rows (start, line, side) | 40,008 (Tier A 28,044 / Tier B 11,964) |
| **Slate dates** | **270** (Tier A 184: 2025-03-18..2025-09-28; Tier B 88: 2024-07-01..2024-09-30) |
| Closing paired refs (benchmark-only) | 70,373 |
| Paper bets (registered rule; settlement GATED) | 11,435 (10,962 with close, 473 without) |

- Status: prep EXECUTED and outcome-free. **No authorized canonical
  scoring run has executed.** One accidental run occurred (2026-10-14
  ~17:15; outputs deleted without being cited; see INCIDENT.md); whether
  anyone inspected the computed metrics before deletion is UNRESOLVED.
- Tier B (2024-07-01..2024-09-30, clock proxy) is development-era by date,
  carried in the same prep but reported separately and labeled sensitivity —
  never pooled into a Tier A headline.
- Closing refs / benchmark_refs are benchmark-only by construction and are
  never part of the actionable set (separation verified: 0 overlaps; Tier A
  CLV non-trivial because actionable strictly precedes close).

## Classification summary

| Data | Class |
| --- | --- |
| 2022 PAs (182,051) | warm-up feature state only (never fitted) |
| 2023 PAs (base_train/calibration of 2024H1..2025H1 blocks) | training |
| 2024H1/2024H2/2025H1 assessments (walk-forward) | development-era inspected evaluation |
| confirm_2025H2 assessment (2025-07-01..2025-09-28) | EVAL — **inspected confirmation** |
| 7,194-start realized-sequence population | inspected diagnostic (count errors reused) |
| Market prep_v2 populations (6,813 / 6,647 / 6,643 / 20,004 / 40,008 / 270) | outcome-free prep of forecast-evaluation subsets; scoring gated |
| 2026 anything | **genuinely unused — CLOSED; nothing touched** (no-2026-tuning rule) |
| 2023 archive K quotes (`board_2023_24` label) | genuinely unused by market-eval (payload cohort starts 2024-07-01) |
| Integer-line push machinery | registered + tested, unexercised (0 integer contracts in cohort) |

## Reconciliation pins

- Starts: 7,194 = 62 + 294 + 25 + 166 + 4 + 1,244 + 5,399 (exact;
  EXCLUSION_LEDGER.md / exclusion_ledger.json).
- Contracts: 2,440,774 K-market rows -> 2,440,764 price-valid -> 59,636
  paired actionable -> 20,004 eval observations -> 40,008 side rows.
- Effective counts for the PIN: 40,008 side rows = 20,004 (start, line) x2;
  6,643 distinct starts; 270 slate dates; complementary sides NOT
  independent (slate-date bootstrap is the declared correlation handling).
