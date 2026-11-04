# Execution packet: lgbm_multiclass_v1

STATUS: AUTHORIZATION-READY, NOT AUTHORIZED. Every factual claim below was
checked against the code at the frozen checkpoint (2026-11-04). Approval
flow: Chat 2 packet review -> explicit owner approval -> single execution
of the exact command in this packet. The ack token
`EXECUTE-LGBM-MULTICLASS-V1` is a technical gate only and is NOT
authorization. Card: `docs/adr/PROPOSED-lgbm-multiclass-challenger.md`.

## Code checkpoint (frozen during review)

Executable frozen at the commit introducing this packet on
`research/lgbm-multiclass-v1` (SHA named in the PR #59 dashboard). Module
SHA-256 identities at that checkpoint:

| Module | SHA-256 |
|---|---|
| lgbm_multiclass_comparison.py (runner) | `332f7aea1431e8ad95aacd442448bb3ea34b6e778548d22b793d050beda53f02` |
| platoon_comparison.py (control-arm fit + softmax, imported) | `8136e1a81f03ff188666a1eb5e7bd184fc41bfdb92a678d7c36b4dc904c2237f` |
| platoon_features.py (platoon-features-v1) | `ccc56ecac9aed45026c32bb5ce9faa69f07fdfcc2eefd831b8e7607ca46e7122` |
| binary_k_comparison.py (helpers, imported) | `3ad1ccedce6eb6122a017b38b455cdc88d7e0320a0d56dba0d7d0a8b2aefe7ad` |
| adapter.py | `adfa7283d2150abe05ea480f86451a54cb7f550e8e87d798d8940e3fef5a4e47` |
| m0_multiclass.py | `5afe972b4f1c8921f2a87b53af4e1783384ec09fb880ab44328d0b3c18e809fd` |
| workload_comparison.py (pooled-BF37 construction source) | `c0b391bb818f393524d6732946bff41fd4df9d9c0c350e7480e2ff437581f90c` |
| kcount_combiner.py | `94f57a49c0996df5147fb961a085fd229d0ba0e3903c6da0ced9f2d3b670f18f` |
| statcast_event_bridge.py | `5781b3cf83f3d9780fd41cc375b2d29a4a9968bb4a2db996b29ab489a099f4dc` |
| forecast_states_v2.py | `7ec56566c9382ecd8d678338817537f35f2b018f17b756931aa1e0d59a9b356b` |
| baseline_ladder.py | `af81e313be3f11c3a257f64871879d21643e1a18ca4356407e86440a738a55d0` |

adapter/m0/workload/kcount/binary_k hashes are byte-identical to the
verified binary-K run's pins. The runner's `receipt_initial.json`
independently records seven module identities at runtime. Any code change
during review is a new checkpoint, not this packet.

## What runs (one invocation: 13 LightGBM fits + 1 multinomial fit)

1. **Control arm fit (fixed recipe, no tuning):** `pc.fit_challenger` -
   the 12-feature multinomial-plus-platoon pipeline (StandardScaler +
   LogisticRegression C=1.0 lbfgs, identical softmax), exactly the
   accepted platoon run's challenger arm; equal per-PA training weights.
2. **Challenger tuning (pre-declared small budget, chronological):**
   BOUNDED-SELECTED LightGBM multiclass on the IDENTICAL 12 columns
   (fixed multinomial control untouched); grid = `num_leaves`
   {7, 15, 31} x `min_data_in_leaf` {50, 200} (6 configurations, fixed
   `learning_rate = 0.05`, `n_estimators = 200`, `seed/deterministic`
   pinned, single-threaded); TWO chronological folds INSIDE the declared
   training window (fit `2024-05-01..2024-08-31` -> validate
   `2024-09-01..2024-10-31`; fit `..2024-10-31` -> validate
   `2024-11-01..2024-12-31`) = **12 tuning fits**; selection = lowest mean
   validation multiclass log loss, ties -> fewer `num_leaves` -> larger
   `min_data_in_leaf` -> grid order. ALL 12 fold results are recorded.
   The registered assessment cohort NEVER enters tuning or selection.
3. **Challenger final fit:** ONE fit on the full declared training window
   with the selected configuration.
4. Both arms' full class-probability vectors keyed to
   (game_pk, side, pitcher, slot, batter); both K marginals through the
   SAME registered `ad.start_count_pmfs(p9, p9, pooled_bf37)` aggregation
   (24 buckets) with the SAME per-cutoff pooled W0 BF37.
5. **Primary endpoint:** per-PA multiclass log loss on the identical
   matched-PA population; contrast statistic = per-start means (each
   start equally weighted, PAs equally weighted within a start); paired
   slate-date bootstrap 2,000 draws seed 20261001. Practical threshold
   0.0005 nats. **K-count non-degradation guard:** mean per-start
   count-RPS challenger - control within the declared 0.002 margin
   (POINT ESTIMATE; NOT a statistical noninferiority claim; CI reported
   as context). Secondary (declared, non-decisive): classwise log loss /
   Brier, K RPS means, K PMFs, and the full tuning fold table.
6. The reconstruction gate requires the control arm to reproduce the
   pinned accepted per-start count-RPS of the platoon run's challenger
   arm (column `rps_platoon`) within 1e-12 BEFORE any contrast is
   reported.

## What is read (full-file decode disclosure)

Identical to the accepted platoon run: the CLI decodes IN FULL, after the
four file-byte pins verify, the PA table, projected-lineups parquet,
assessment parquet, reconstruction reference, and cohort-keys parquet;
the terminal-event bridge reads the two raw Statcast parquets IN FULL
(LEFT-join onto the declared PA population; conflict detection before any
dedup). The registered pa_table contains rows through 2025-09-28
(block_2025H2 rows present in decoded/states/rates frames but unable to
enter training, tuning, forecasts, or scoring: window + label filter,
strictly-prior constructions at 2025H1 cutoffs, cohort-restricted
assessment). No 2026 rows exist in the registered artifacts. No input
outside the pinned paths is read; no network access; no writes outside
the destination. LightGBM tuning folds use ONLY rows inside the declared
training window; the assessment cohort is decoded once and scored after
the configuration is frozen.

## Destination

`C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\lgbm_multiclass_v1` - fresh write-once directory; the runner checks destination non-existence at entry. Evidence saved: `receipt_initial.json` (immutable), `receipt_final.json`, `lgbm_comparison_report.json` (incl. the full tuning fold table + selection), `lgbm_per_start_v1.parquet`, `keyed_pa_probabilities.parquet` (both arms), `model_artifacts.json` (both models; LightGBM booster serialized to text, reloadable), `k_pmf_per_start_v1.parquet`, `bf37_pooled_by_date_v1.parquet`, `platoon_split_rates_v1.parquet`, `failure_record.json` on any exception (then re-raise).

## Identity pins and enforcement mechanisms

| Input | Path / source | Identity mechanism |
|---|---|---|
| PA source | `C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\pa_table.parquet` | File SHA-256 `1d3be6297d344a93506c9be094795c798d3e32b97dd7ce2f30523804ca846aff` - ENFORCED pre-decode (exit 1) |
| Projected lineups | `C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1\data\projected_lineups_variant_v2.parquet` | File SHA-256 `b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b` - ENFORCED pre-decode (exit 1) |
| Assessment outcomes | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\assessment_2025H1_v1.parquet` | File SHA-256 `464fe1922c4aa3090f46b43cdce4949a888ad0c20ccd269d5c2cce671a1b80aa` - ENFORCED pre-decode (exit 1) |
| **Reconstruction reference** | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\platoon_information_v1\platoon_per_start_v1.parquet` (accepted multinomial-plus-platoon per-start artifact, column `rps_platoon`) | File SHA-256 `c74283753c4fb6f156351c5c310c6ef0ede99b79aacfc7e261cc21f7d7216017` - **ENFORCED pre-decode (exit 1)** |
| Cohort keys (n=2,509) | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\eligible_cohort_keys_2025H1.parquet` | Sorted-key CONTENT hash `f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7` - ENFORCED before feature construction (refusal, exit 1). The file's own byte hash is a different quantity and is NOT the pin. |
| Raw Statcast 2024 | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2024\statcast_2024_regular.parquet` | SHA-256 `de78a1893aa21e305153f5594987f85b40e4bc0cf572484e995a1416b3c49b33` - RECORDED in the receipt (procedural) |
| Raw Statcast 2025 | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2025\statcast_2025_regular.parquet` | SHA-256 `cb072ff830959374ae2f8a8d804a0093e77b2cf0d898fda046b44605d5c31aad` - RECORDED (procedural) |

All six pinned files were re-hashed on disk 2026-11-04 and match; the
cohort content hash was recomputed from the 2,509 keys and matches.

## Command (single line, copy-paste ready; execution only after approval)

```
python research/offseason_2026/pregame_pa_ext/lgbm_multiclass_comparison.py --pa-source "C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\pa_table.parquet" --lineups "C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1\data\projected_lineups_variant_v2.parquet" --assessment "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\assessment_2025H1_v1.parquet" --raw-events "C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2024\statcast_2024_regular.parquet,C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2025\statcast_2025_regular.parquet" --train-start 2024-05-01 --train-end 2024-12-31 --out-dir "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\lgbm_multiclass_v1" --execution-ack EXECUTE-LGBM-MULTICLASS-V1 --cohort-keys "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\eligible_cohort_keys_2025H1.parquet" --expected-cohort-hash f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7 --reconstruction-reference "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\platoon_information_v1\platoon_per_start_v1.parquet" --expected-reconstruction-sha256 c74283753c4fb6f156351c5c310c6ef0ede99b79aacfc7e261cc21f7d7216017 --expected-pa-sha256 1d3be6297d344a93506c9be094795c798d3e32b97dd7ce2f30523804ca846aff --expected-lineups-sha256 b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b --expected-assessment-sha256 464fe1922c4aa3090f46b43cdce4949a888ad0c20ccd269d5c2cce671a1b80aa
```

All 15 flags verified against the CLI argparse (`--help`, 2026-11-04);
none missing, none extra.

## Refusals and stop conditions (exhaustive)

- Wrong/missing execution ack: exit 2, zero reads, zero writes.
- Any of the four file-byte pins mismatched: `INPUT IDENTITY MISMATCH`,
  exit 1, zero writes.
- Cohort content hash mismatch, duplicate/null cohort keys: refusal before
  feature construction.
- Empty/single-class training population, null base features, missing
  platoon rates for a cutoff, an empty or class-incompatible
  chronological fold, duplicate actual-PA identities, empty matched-PA
  population, matched PA with a class outside the fitted class set, a
  start without 9 usable slots, non-finite/non-normalized LightGBM
  probabilities: refusal (never an invented replacement).
- Reconstruction gate failure (keys differ, or max per-start |RPS diff| >
  1e-12): per-start evidence preserved, report and receipt aborted,
  failure record written, non-zero exit. Never tuned away.
- Any exception: `failure_record.json` then re-raise.
- On any refusal or failure: STOP. Evidence preserved; no altered
  tolerance, no silent input substitution, no unapproved retry.

## Reporting rules (pre-declared in the card)

Statistical direction and practical magnitude are reported separately:
CI entirely below zero favors the challenger; entirely above favors the
control; overlapping zero is inconclusive. A mean log-loss improvement
below the declared practical threshold (0.0005 nats) does not justify the
added model complexity regardless of CI direction. The K-count acceptance
guard is the 0.002 point-estimate margin (NOT a statistical
noninferiority claim). Promotion is never automatic. The reconstruction
gate must pass before any contrast is reported.

## Explicitly out of scope (deferred)

No feature expansion, no SHAP deliverable, no calibration, no rescue
variants, no additional tuning budget beyond the declared 12 fits, no
taxonomy/workload/aggregation change, no double-play simulation. The
`m0.apply_multinomial` two-class softmax repair and any change to the
reviewed `workload_comparison.py` remain DEFERRED. No MLflow logging, no
follow-up runs, no subgroup analyses.

## Limitations carried into any result

Development evidence on the registered 2025H1 cohort; not a fresh final
test; no production, betting-value, or causal claims; the small
chronological tuning budget does not establish optimality of the selected
configuration; equal-information design attributes any gain to the model
family; 2026 untouched.
