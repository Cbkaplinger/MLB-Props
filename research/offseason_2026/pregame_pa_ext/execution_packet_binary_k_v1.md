# Execution packet: binary_k_vs_multinomial_v1 (revision 2)

STATUS: AUTHORIZATION-READY, NOT AUTHORIZED. Every factual claim below was
checked against the code at the frozen checkpoint (2026-11-03). Approval
flow: Chat 2 packet review -> explicit owner authorization -> single
execution of the exact command in this packet. The ack token
`EXECUTE-BINARY-K-VS-MULTINOMIAL-V1` is a technical gate only and is NOT
authorization. Card: `docs/adr/PROPOSED-binary-k-vs-multinomial-k.md`.

## Code checkpoint (frozen during review)

Executable frozen at the commit introducing this packet revision on
`research/binary-k-vs-multinomial-v1` (SHA named in the PR #57 dashboard).
Module SHA-256 identities at that checkpoint:

| Module | SHA-256 |
|---|---|
| binary_k_comparison.py (runner) | `3ad1ccedce6eb6122a017b38b455cdc88d7e0320a0d56dba0d7d0a8b2aefe7ad` |
| adapter.py | `adfa7283d2150abe05ea480f86451a54cb7f550e8e87d798d8940e3fef5a4e47` |
| m0_multiclass.py | `5afe972b4f1c8921f2a87b53af4e1783384ec09fb880ab44328d0b3c18e809fd` |
| workload_comparison.py (pooled-BF37 construction source) | `c0b391bb818f393524d6732946bff41fd4df9d9c0c350e7480e2ff437581f90c` |
| kcount_combiner.py | `94f57a49c0996df5147fb961a085fd229d0ba0e3903c6da0ced9f2d3b670f18f` |
| statcast_event_bridge.py | `5781b3cf83f3d9780fd41cc375b2d29a4a9968bb4a2db996b29ab489a099f4dc` |
| forecast_states_v2.py | `7ec56566c9382ecd8d678338817537f35f2b018f17b756931aa1e0d59a9b356b` |
| baseline_ladder.py | `af81e313be3f11c3a257f64871879d21643e1a18ca4356407e86440a738a55d0` |

The runner's `receipt_initial.json` independently records the first five
identities at runtime; adapter/m0/workload/kcount hashes are byte-identical
to the accepted `workload_personalization_w0v1` run's verified pins
(`adfa7283`/`5afe972b`/`c0b391bb`/`94f57a49`). Any code change during review
is a new checkpoint, not this packet.

## What runs (the actual fixed-recipe two-fit design)

ONE invocation fits TWO models on the SAME declared training rows and scores
BOTH on the SAME cohort:

1. **Control arm fit (fixed recipe, no tuning):** `m0.fit_multinomial` on the
   labeled training frame - StandardScaler + sklearn LogisticRegression
   (C=1.0, lbfgs, max_iter=1000), 4-class taxonomy, K marginal = class-0
   softmax probability (2-class parameterization handled by the runner's
   `_multinomial_pk` with the identical softmax definition).
2. **Challenger arm fit (fixed recipe, no tuning):** `fit_binary` - same
   StandardScaler + LogisticRegression hyperparameters on the SAME rows,
   label `is_k = 1[class_label == K_CLASS]` derived only from the bridged
   `class_label`; per-PA P(K) via a numerically stable sigmoid.
3. Both arms' per-slot K probabilities feed the SAME registered
   `ad.start_count_pmfs(p9, p9, pooled_bf37)` aggregation (24 buckets) with
   the SAME per-cutoff pooled W0 BF37 (construction imported unchanged from
   the reviewed workload runner).
4. Primary endpoint: paired per-start count-RPS contrast
   (RPS(binary-K) - RPS(control)), slate-date bootstrap 2,000 draws,
   seed 20261001 (`bl.paired_contrast`; legacy helper label disclosed).
   Descriptive only (not decisive): per-PA K log loss and Brier on the
   identical matched-PA population.
5. The reconstruction gate requires the control arm to reproduce the pinned
   accepted per-start count-RPS within 1e-12 BEFORE any contrast is
   reported.

There is no third fit, no refit of any accepted artifact, no coefficient
tuning, no feature search, no calibration, and no subgroup exploration.

## What is read (full-file decode disclosure)

The CLI decodes IN FULL, after the four file-byte pins verify: the PA table,
the projected-lineups parquet, the assessment parquet, the reconstruction
reference, and the cohort-keys parquet; the terminal-event bridge reads the
two raw Statcast parquets IN FULL and LEFT-joins validated labels onto the
declared PA population (conflict detection before any dedup; missing labels
stay detectable; failure evidence written by the bridge).

- The registered pa_table contains rows through 2025-09-28, so block_2025H2
  rows ARE inside the decoded frame and inside the states frame. They cannot
  enter any training row (training = window 2024-05-01..2024-12-31 AND
  `class_label >= 0`), any forecast state (v2 construction aggregates ONLY
  rows with `game_date` strictly before each 2025H1 request cutoff), or any
  scored population (assessment = cohort-restricted 2025H1 frame). No 2025H2
  outcome is fitted, forecast, or scored.
- The registered artifacts contain NO 2026 rows; there is nothing to decode
  or score for 2026.
- No input outside the pinned paths is read; no network access; no writes
  outside the destination.

## What is scored and where outputs go

Scored population: the registered 2,509-start block_2025H1 eligible cohort
(sorted-key content hash below), 9-slot keyed aggregation per start,
24-bucket K PMFs per arm, per-start count-RPS, paired contrast, per-PA
descriptive metrics on the identical matched-PA population.

Destination: `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\binary_k_vs_multinomial_v1` - fresh write-once directory. The runner checks destination non-existence at entry, before any label decode or output write; a CLI invocation decodes the five declared inputs (after hash verification) and then refuses without creating anything if the destination exists. Evidence saved: `receipt_initial.json` (immutable, hash-checked at completion; ack route, five module identities, config incl. threshold, expected input identities), `receipt_final.json` (cohort identity, reconstruction evidence, output hashes, counts, acceptance), `binary_k_comparison_report.json`, `binary_k_per_start_v1.parquet`, `keyed_pa_probabilities.parquet` (both arms), `model_artifacts.json` (both fitted models, reloadable), `k_pmf_per_start_v1.parquet`, `bf37_pooled_by_date_v1.parquet`, and `failure_record.json` on any exception (then re-raise).

## Identity pins and enforcement mechanisms

| Input | Path / source | Identity mechanism |
|---|---|---|
| PA source | `C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\pa_table.parquet` | File SHA-256 `1d3be6297d344a93506c9be094795c798d3e32b97dd7ce2f30523804ca846aff` - ENFORCED pre-decode (exit 1 on mismatch, zero side effects) |
| Projected lineups | `C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1\data\projected_lineups_variant_v2.parquet` | File SHA-256 `b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b` - ENFORCED pre-decode (exit 1) |
| Assessment outcomes | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\assessment_2025H1_v1.parquet` | File SHA-256 `464fe1922c4aa3090f46b43cdce4949a888ad0c20ccd269d5c2cce671a1b80aa` - ENFORCED pre-decode (exit 1) |
| **Reconstruction reference** | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\workload_personalization_w0v1\workload_per_start_v1.parquet` (accepted multinomial-plus-W0 per-start artifact, column `rps_w0_pooled`) | File SHA-256 `ae971758b70e1649e28046a8180d375872ad0172f9c8b5cc03ab74e8dfa85f79` - **ENFORCED pre-decode (exit 1)** |
| Cohort keys (n=2,509) | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\eligible_cohort_keys_2025H1.parquet` | Sorted-key CONTENT hash `f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7` - ENFORCED before feature construction (refusal, exit 1). NOTE: the file's own byte hash (`7a0807a8...`) is a different quantity and is NOT the pin. |
| Raw Statcast 2024 | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2024\statcast_2024_regular.parquet` | SHA-256 `de78a1893aa21e305153f5594987f85b40e4bc0cf572484e995a1416b3c49b33` - RECORDED in the receipt (procedural bridge accounting, same convention as the reviewed workload runner; not pre-decode enforced) |
| Raw Statcast 2025 | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2025\statcast_2025_regular.parquet` | SHA-256 `cb072ff830959374ae2f8a8d804a0093e77b2cf0d898fda046b44605d5c31aad` - RECORDED (procedural) |

All six pinned files were re-hashed on disk 2026-11-03 and match; the
cohort content hash was recomputed from the 2,509 keys and matches.

## Command (single line, copy-paste ready; execution only after approval)

```
python research/offseason_2026/pregame_pa_ext/binary_k_comparison.py --pa-source "C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\pa_table.parquet" --lineups "C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1\data\projected_lineups_variant_v2.parquet" --assessment "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\assessment_2025H1_v1.parquet" --raw-events "C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2024\statcast_2024_regular.parquet,C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2025\statcast_2025_regular.parquet" --train-start 2024-05-01 --train-end 2024-12-31 --out-dir "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\binary_k_vs_multinomial_v1" --execution-ack EXECUTE-BINARY-K-VS-MULTINOMIAL-V1 --cohort-keys "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\eligible_cohort_keys_2025H1.parquet" --expected-cohort-hash f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7 --reconstruction-reference "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\workload_personalization_w0v1\workload_per_start_v1.parquet" --expected-reconstruction-sha256 ae971758b70e1649e28046a8180d375872ad0172f9c8b5cc03ab74e8dfa85f79 --expected-pa-sha256 1d3be6297d344a93506c9be094795c798d3e32b97dd7ce2f30523804ca846aff --expected-lineups-sha256 b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b --expected-assessment-sha256 464fe1922c4aa3090f46b43cdce4949a888ad0c20ccd269d5c2cce671a1b80aa
```

15/15 flags verified against the CLI argparse (`--help`, 2026-11-03); none
missing, none extra.

## Refusals and stop conditions (exhaustive)

- Wrong/missing execution ack: exit 2, zero reads, zero writes.
- Any of the four file-byte pins mismatched: `INPUT IDENTITY MISMATCH`,
  exit 1, zero reads beyond the hashed bytes, zero writes.
- Cohort content hash mismatch, duplicate cohort keys, null cohort keys:
  refusal before feature construction.
- Empty training population, single-class training population, null request
  features: refusal.
- Duplicate actual-PA identities, empty matched-PA population: refusal.
- A start without 9 usable slots: refusal (never an invented replacement).
- Reconstruction gate failure (keys differ from scored starts, or max
  per-start |RPS diff| > 1e-12): per-start evidence preserved, report and
  receipt aborted, failure record written, non-zero exit. The gate result is
  NEVER tuned away.
- Any exception: `failure_record.json` (stage, error, initial-receipt sha)
  then re-raise.
- On any refusal or failure: STOP. Evidence preserved; no altered tolerance,
  no silent input substitution, no unapproved retry.

## Reporting rules (pre-declared in the card)

Statistical direction and practical magnitude are reported separately:
CI entirely below zero favors binary-K; entirely above retains the
multinomial control; overlapping zero is inconclusive. A magnitude below
the declared practical threshold (0.005 count-RPS) does not justify added
complexity regardless of CI direction. Promotion is never automatic.

## Explicitly out of scope (deferred)

The `m0.apply_multinomial` two-class softmax repair and any change to the
reviewed `workload_comparison.py` are DEFERRED (nonblocking finding for
review); they must not be expanded, retried, or repaired inside this run.
No taxonomy, calibration, feature, workload, or estimator-family change
beyond the single declared K-probability-source difference. No MLflow
logging, no follow-up runs, no subgroup analyses.

## Limitations carried into any result

Development evidence on the registered 2025H1 cohort; not a fresh final
test; no production, betting-value, or causal claims; the binary arm models
P(K) only and says nothing about non-K class uses; 2026 untouched.
