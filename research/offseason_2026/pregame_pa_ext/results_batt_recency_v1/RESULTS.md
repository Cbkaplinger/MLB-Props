# RESULTS — batter-history challenger diagnostic v1 (R60/m30), 2026-10-20

Bounded real-data diagnostic executed ONCE under owner authorization
(PR #25 contract, approved head 2d2c02f at execution time). All registered
integrity checks passed. **Primary result: the challenger is significantly
WORSE than the unchanged baseline on development log loss** — the
recency-anchored batter feature REJECTS its hypothesis.

## Headline numbers (82,817 paired development evaluation PAs)

| Metric | Baseline (frozen) | Challenger (R60/m30) | Delta (chall − base) |
| --- | --- | --- | --- |
| **Log loss (PRIMARY)** | 0.5085714457 | 0.5091916511 | **+0.0006202053** |
| Brier (supporting) | 0.1647954031 | 0.1649860802 | +0.0001906771 |

- Registered bootstrap (slate-date, block-stratified, n=2000, seed 20261001,
  null-centered with the (B+1) finite-resample correction, Holm m=1):
  **p = 0.0004997501** (2000-resample resolution floor); 95% percentile
  interval on the paired delta **[+0.0002941, +0.0009431]** — entirely
  positive (worse).
- Calibration (supporting, descriptive): baseline mean predicted 0.21367 vs
  observed 0.21461; challenger mean predicted 0.20987 vs observed 0.21461;
  challenger max decile reliability gap 0.01291.

## Interpretation (dev-only, non-promotional)

Recent form anchored to an age-weighted personal history does **not**
improve batter K probabilities here — it degrades them, with the paired
interval excluding zero on the worse side. No promotion, no downstream
use, no claim beyond this development diagnostic. The unchanged frozen
baseline remains the reference.

## Coverage and abstentions

- 4,823 eligible development starts / 43,407 projected slots / **82,817
  observed pitcher-matched evaluation PAs** (frozen keys verified:
  slots `82592f18...`, evaluation `c6568151...`).
- Abstentions (frozen record `abstentions.json`, sha256
  `66c582e070229ee02e72d07af8574af4e335d75603ae47efc000851d987e385f`):
  **59 full-run** (57 debut-date newcomers + 2 window-limited veterans
  Enns 608650 / Hart 606996), of which **43 development** and 16
  confirmation-block. Development metrics never treat the full-run total
  as a development count. Confirmation outcomes were not touched.

## Execution provenance

- Executed: 2026-10-20, single run, no retry, no overwrite. Output bundle
  (write-once, in the private lake):
  `MLB-Props-Research\pregame-pa-ext-v2\diagnostics\batt_recency_v1\`
  (`batt_recency_eval_v1.parquet` sha256 `375f25f9...e0221c`;
  `metrics.json` sha256 `517bac01...1a921`).
- Receipt: `provenance_receipt.json` in the same bundle — sections inputs /
  code_config / dev_keys / fits / metrics / outputs / abstentions /
  acceptance, all validated. MLflow transport not exercised (receipt
  on disk is the mandatory record).
- Fits: block_2024H2 n=219,078 (coef sha256 `db173def...`), block_2025H1
  n=306,791 (coef sha256 `16e4dc4b...`) — training rows identical to the
  frozen recipe's realized-PA lineage (max train dates 2024-05-01 /
  2024-08-01; confirmation rows never entered training).

## DISCLOSED DEFECT + REPAIR (transparency)

The authorized run's CLI wiring did not pass artifact paths, so the
original receipt's `inputs` section was a placeholder note (receipt-
completeness defect in code published at `084d2aa`; the evaluation itself
was unaffected). **Repair (same day, disclosed):** the `inputs` section
was completed READ-ONLY from the same frozen files the run consumed, with
a dated `receipt_repair` note inside the receipt; every other section
byte-unchanged; re-validated. The CLI wiring was fixed in code so any
future run emits complete receipts natively. No re-run, no re-fit.

Input identities (from the repaired receipt): pa_table `1d3be629...`,
preserved ledger `fd1841e1...`, checkpoint raw-file `d266a1cd...`
(registered payload pin `176fb18b...` enforced), BF `c9c2762f...`,
lineups `b6a1947c...`, freeze config `31dd78b7...`.

## State

- The ORIGINAL prediction run remains **UNACCEPTED** and unchanged
  (write-once parquet untouched).
- This diagnostic is development-only: no confirmation evaluation, no
  count-distribution validation, no betting/decision claim.
- Bundle files are mirrored byte-identically in this directory
  (metrics.json / provenance_receipt.json / abstentions.json).
