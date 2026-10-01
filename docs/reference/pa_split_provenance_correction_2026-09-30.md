# C1/C7 Provenance Correction — PA split populations (Phase 8.7, 2026-09-30)

Classification: `REPORTING_AND_SPLIT_PROVENANCE_DEFECT — PRIMARY PAIRED CLAIMS UNAFFECTED`.
No rerun. No card, bundle, prediction, or metric file modified. This note is the correction.

## C1: executed vs registered PA block populations

Primary artifacts: `experiments/logistic_pa/pa_predictions.parquet`,
`experiments/tree_pa/tree_predictions.parquet` (both hash-verified, 2026-09-30 audit).

- Both files contain **106,267 rows with unique keys; key sets identical** and equal to
  the full `pa_table_2023_2024.parquet` 2024 frame (zero null labels; the 122-key
  reconciliation filter is a verified no-op — those keys are absent from the table,
  excluded upstream at build).
- Executed bucketing in both `run_phase7.py` (L403–405) and `run_tree.py` (L178, L265)
  compares **string-cast** datetimes: `E1 = game_date_str <= "2024-06-30"`,
  `E2 = game_date_str >= "2024-07-01"`.
- Executed counts on the artifact frames: **E1 = 55,239; E2 = 50,349;
  2024-06-30 rows = 679 in NEITHER block** (string `"2024-06-30 00:00:00"` exceeds
  `"2024-06-30"`); pooled = 106,267 (06-30 rows included only in pooled_descriptive).
- Cards state E1 = 55,815 / E2 = 50,252 (= 106,067). That pair corresponds to
  datetime-style bucketing (06-30 inside E1) on a 200-row-smaller population that no
  executed frame reproduces. The discrepancy is symmetric across every arm.
- Stored vs independently recomputed arm metrics agree to 6 decimal places on the
  executed masks (audit §7). Paired deltas, bootstrap intervals, and the tree stop
  verdict are therefore valid as executed; only the registered block-n labels are wrong.
- Future rule: split manifests must encode interval boundaries mechanically
  (inclusive timestamp bounds, no string comparison) and assert every eligible row
  belongs to exactly one registered block or a named excluded set.

## C7: aggregation start counts by block

Primary artifacts: `experiments/pa1b_oracle_xk/metrics.json`
(`E1 n`, `E2 n` per arm), `completeness.json`, `start_predictions.parquet`.

- **E1 = 2,467 starts; E2 = 2,244 starts; pooled = 4,711 starts.**
- Phase 6 Gate A resolution: 4,711/4,711 reconcile exactly post-resolution
  (reliever-completed terminal rows credited to the completing pitcher).
- The tree-phase aggregation asserts exact reconciliation
  (`n_rows == official_BF` for every start) over the same registered population, so it
  inherits the identical block counts; all compared arms use identical starts.
- PA1B E1 reference values: M0 MAE 1.8797, P3_l5 MAE 1.7347 (n = 2,467).
