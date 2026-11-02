# Execution packet: workload_personalization_w0v1

Status: FROZEN for Chat 2 review. No execution until owner approval.
Code checkpoint: `45ed606fb73a78f72cc008f3f52aa39037454ae5` on
`research/baseline-history-scorecard-v1` (working tree clean).

## Code identity

| File | sha256 |
|---|---|
| research/offseason_2026/pregame_pa_ext/workload_comparison.py | `c0b391bb818f393524d6732946bff41fd4df9d9c0c350e7480e2ff437581f90c` |
| research/offseason_2026/pregame_pa_ext/adapter.py | `adfa7283d2150abe05ea480f86451a54cb7f550e8e87d798d8940e3fef5a4e47` |
| research/offseason_2026/pregame_pa_ext/m0_multiclass.py | `5afe972b4f1c8921f2a87b53af4e1783384ec09fb880ab44328d0b3c18e809fd` |
| research/offseason_2026/kcount_combiner.py | `94f57a49c0996df5147fb961a085fd229d0ba0e3903c6da0ced9f2d3b670f18f` |
| research/offseason_2026/pregame_pa_ext/forecast_states_v2.py | `7ec56566c9382ecd8d678338817537f35f2b018f17b756931aa1e0d59a9b356b` |
| research/offseason_2026/pregame_pa_ext/statcast_event_bridge.py | `5781b3cf83f3d9780fd41cc375b2d29a4a9968bb4a2db996b29ab489a099f4dc` |
| research/offseason_2026/pregame_pa_ext/baseline_ladder.py | `af81e313be3f11c3a257f64871879d21643e1a18ca4356407e86440a738a55d0` |

adapter / m0 / bridge SHAs match the stage-1 preparation receipt
(`preparation_receipt.json`) exactly: shared machinery unchanged.

## Input pins (all REQUIRED by the CLI; verified on disk)

| Pin | Path | sha256 |
|---|---|---|
| PA source | `C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\pa_table.parquet` | `1d3be6297d344a93506c9be094795c798d3e32b97dd7ce2f30523804ca846aff` |
| Projected lineups | `C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1\data\projected_lineups_variant_v2.parquet` | `b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b` |
| Assessment outcomes | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\assessment_2025H1_v1.parquet` | `464fe1922c4aa3090f46b43cdce4949a888ad0c20ccd269d5c2cce671a1b80aa` |
| BF workload (W1) | `C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\data\bf_forecasts.parquet` | `c9c2762fb2c1c239e5645c49fa92eda50bd652d26e54755ac8bf0c28fa968679` |
| Raw Statcast 2024 | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2024\statcast_2024_regular.parquet` | `de78a1893aa21e305153f5594987f85b40e4bc0cf572484e995a1416b3c49b33` |
| Raw Statcast 2025 | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2025\statcast_2025_regular.parquet` | `cb072ff830959374ae2f8a8d804a0093e77b2cf0d898fda046b44605d5c31aad` |

Lineups, BF, PA, and both raw Statcast pins equal the registered
identities from the accepted-baseline preparation receipt and the
bf-workload-v1 registered construction.

## Accepted reference pin (reconstruction gate)

- Path: `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1\multiclass_baseline_per_start_v1.parquet`
- sha256: `3414d0d2fba58eba34524ad0a28fb9b63d1f1918595b608f1fc2e2b20bc4cf07`
- 2,509 rows; schema verified (game_pk, side, pitcher, rps_ref1_multinomial).
- Tolerance: max per-start absolute RPS difference <= 1e-12. The
  tolerance is NOT adjustable; a gate failure is diagnosed, never
  tuned away.

## Cohort identity

- Cohort keys: `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\eligible_cohort_keys_2025H1.parquet`
- File sha256: `7a0807a80abb2cfab0506038510ae7db2b441280cdd5c3e5f2bb521df5e3d6e0`
- Computed cohort hash: `f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7`
  (matches the registered 2,509-start pin; 0 duplicates, 0 nulls, verified).

## Fresh output destination

`C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\workload_personalization_w0v1`
Must NOT exist at launch (write-once enforced). Never reuse or delete.

## Decode disclosure

The CLI reads and decodes: the four input parquet frames above, the
cohort-keys parquet, the reconstruction-reference parquet, and the two
raw Statcast parquet files (terminal-event bridge reads them for
labeling). Raw Statcast identity is hashed and recorded in the receipt,
but the terminal-event preflight is PROCEDURAL (bridge accounting), not
CLI-enforced event-level identity. Ack route: `cli`.

## Failure / no-retry behavior

- Any failure writes `failure_record.json` into the fresh out-dir and
  aborts; the out-dir is NOT deleted or reused.
- A retry requires a NEW fresh out-dir (`..._attempt2`, etc.); prior
  failed dirs are preserved unchanged as evidence.
- Invalid ack / mismatched pins refuse before any decode or creation.

## Projected-lineup artifact: exact generator

Artifact: `projected_lineups_variant_v2.parquet`
(sha `b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b`, 7,194 starts).

- Generator script: `C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1\scripts\build_projected_lineups_variant_v2.py`
  sha256 `dba328627cbdd3aa2b94b1b64ecac1e8a7a5b0e808324c5870094ce055bf6c9d`
  (research workspace script, not a repo commit; preregistered under
  `scripts/preregistration_variant_v2.json`, PREREGISTRATION_2026
  frozen 2026-10-13; build evidence `report_v2.json` +
  `reports/coverage_summary_variant_v2.txt`).
- Request population: the 7,194 registered bf-workload-v1 starts
  (`bf_forecasts.parquet`, `2024-07-01 <= game_date <= 2025-12-31`).
- Slot pools: per opposing-team appearance lists from raw Statcast
  (2023/2024/2025 `statcast_{season}_regular.parquet`), built from the
  SAME prior seven team-games as the v1 mode-slot build (mean 7.0 prior
  games; gate G4 reproduces the v1 parquet's b_slot_i/cnt_slot_i
  EXACTLY for all 7,194 starts).
- Selection + ordering rule: unique-batter bijection. 1) enumerate all
  (slot, batter) pairs with support > 0; 2) sort (support DESC,
  batter MLBAM id ASC, slot ASC); 3) walk in order, assign iff both
  slot and batter unassigned.
- Missing-slot handling: cold-start fallback fills still-unassigned
  slots in ASCENDING slot order with the unassigned pool batter of
  highest TOTAL prior usage (tiebreak smaller MLBAM id). A pool with
  <9 distinct batters leaves slots null and the start is EXCLUDED
  downstream (reason `insufficient_distinct_prior_batters`). In the
  pinned artifact: 7,194/7,194 nine-distinct (0 excluded); 52 starts
  used exactly 1 fallback slot; duplicated ids never written.
- Same-date/future exclusion evidence: pools use prior team-games with
  `game_date < start_date` (strictly prior; `build_projected_lineups_variant_v2.py`
  line ~161), so same-date and future appearances cannot enter.

## Training window and fit settings (copied from the accepted baseline receipt)

Source: `pregame_multiclass_baseline_v1\receipt_initial.json` /
`receipt_final.json` `config` (identical in both). NOT owner-settable
for this isolated comparison — the workload run copies them verbatim:

- `train_window`: **2024-05-01 .. 2024-12-31** (accepted run:
  `train_rows` 148,369).
- Feature construction: `adapter.attach_prior_features` over
  `forecast_states_v2` cutoff states; identical constructor for
  training and inference.
- Fit: regularized multinomial logistic (`m0_multiclass.fit_multinomial`,
  sha `5afe972b…` — unchanged since the accepted run):
  `LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs")` over
  `StandardScaler`-scaled features.
- Class order / taxonomy: 4 classes, K = class 0 = "strikeout"
  (`["strikeout", "walk_hbp_interference", "in_play_out", "hit"]`).
- State contract: `forecast_cutoff_states_v1` (v2 implementation).
- Lineup source: projected lineups (actionable; never oracle).

## Execution command (owner-approval-gated)

```text
python research/offseason_2026/pregame_pa_ext/workload_comparison.py \
  --pa-source C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\pa_table.parquet \
  --lineups C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1\data\projected_lineups_variant_v2.parquet \
  --assessment C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\assessment_2025H1_v1.parquet \
  --bf-source C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\data\bf_forecasts.parquet \
  --raw-events C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2024\statcast_2024_regular.parquet,C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2025\statcast_2025_regular.parquet \
  --cohort-keys C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\eligible_cohort_keys_2025H1.parquet \
  --expected-cohort-hash f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7 \
  --reconstruction-reference C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1\multiclass_baseline_per_start_v1.parquet \
  --expected-pa-sha256 1d3be6297d344a93506c9be094795c798d3e32b97dd7ce2f30523804ca846aff \
  --expected-lineups-sha256 b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b \
  --expected-assessment-sha256 464fe1922c4aa3090f46b43cdce4949a888ad0c20ccd269d5c2cce671a1b80aa \
  --expected-bf-sha256 c9c2762fb2c1c239e5645c49fa92eda50bd652d26e54755ac8bf0c28fa968679 \
  --train-start 2024-05-01 --train-end 2024-12-31 \
  --out-dir C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\workload_personalization_w0v1 \
  --execution-ack EXECUTE-WORKLOAD-PERSONALIZATION-V1
```

Training window and fit settings are copied verbatim from the accepted
baseline receipt; no element of the command is owner-settable.
