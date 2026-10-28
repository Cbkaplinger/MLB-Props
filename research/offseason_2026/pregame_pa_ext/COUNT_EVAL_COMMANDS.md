# COUNT EVAL COMMANDS — pregame-pa-ext-v2 (2026-10-19)

**Status 2026-10-20 (status/pointer update; command and pin sections below unchanged): both commands have now executed once.** RECONSTRUCTION ran once (2026-10-20, verified <=1e-8, serialized, tracked; registered pin armed - registration MERGED via PR #21 at `ccd0148`). SCORING ran once (`run_real`, MLflow run `2393940213154b718124b0b323c62ff9`, pipeline_id `paext-v2-20261020T141540Z`, phase=scoring, VERIFIED for artifact integrity) and **FAILED its zero-exclusion acceptance gate**: 531 pitcher-side cold-start PA exclusions and 59 pitcher-cold starts (7,135 of 7,194 starts fully scored) - authoritatively classified as 57 debut-date newcomers plus two window-limited veterans (Dietrich Enns 608650, Kyle Hart 606996). The output parquet is PRESERVED UNACCEPTED (write-once, untouched). NO further real-data execution is authorized; the abstain-vs-handle population decision is the open owner gate. The separation below (reconstruction once vs scoring repeatable, serialized artifact only, never refits) still governs any future authorized run.

**Navigation notice 2026-10-27 (docs-only; command and history sections below unchanged):** the accepted lane state has advanced past the 2026-10-20 status block above. The Question A diagnostic (exact heterogeneous count aggregation) was executed once and its authoritative record is `results_count_agg_eval_v1/RESULT_RECORD.md` (2026-10-21; commits `6000631`, `c9ab8f2`); the Question B pre-registration card followed (PR #25, `a8382e1`); C-B1 is closed per `docs/NEXT.md` (2026-10-27). The commands, pins, and run records in this file remain the governed reference for any future authorized execution of the two commands below; no further real-data execution is authorized.


Lane: `research/offseason_2026/pregame_pa_ext/` (branch
`research/pregame-pa-ext-v2`). Worktree:
`C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\paext-v2`.

## Command (a) — checkpoint reconstruction (runs ONCE)

```
python research/offseason_2026/pregame_pa_ext/build_checkpoint.py
```

Run from the worktree root with the private lake present (never runs in
CI). Deterministic per-block refit of the frozen H3-raw recipe
(StandardScaler + LogisticRegression(C=1.0, max_iter=1000) on the 8
FEAT_H3 features), then serialization of the VERIFIED coefficients.

Input identity (sha256 re-derived from disk 2026-10-19):

| Role | File | sha256 |
| --- | --- | --- |
| PA table (fit-side lineage) | `C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\pa_table.parquet` | `1d3be6297d344a93506c9be094795c798d3e32b97dd7ce2f30523804ca846aff` |
| Verification preds, block_2024H2 | `...\overnight-p2\data\preds_block_2024H2.parquet` | `a311f4429457ced383b8ef834846978b4682b912e53bb46319107efc0cd980d3` |
| Verification preds, block_2025H1 | `...\overnight-p2\data\preds_block_2025H1.parquet` | `6187d232e8917ce40b481feda5521cecefa0ce8418741ef65aff7dfc8702cbd7` |
| Verification preds, confirm_2025H2 | `...\overnight-p2\data\preds_confirm_2025H2.parquet` | `e60b5aa306dcd5e2157d0de61392681c287a190607330461b98cf91701c88d2a` |

Verification gate (fail-closed, raises `AdapterError` = STOP):

- Refit coefficients must reproduce the stored overnight-p2 preds
  checkpoints (`pred_H3_raw` column) at **<= 1e-8 max abs diff** for all
  three registered blocks; any larger deviation aborts before
  serialization.
- Round-trip check: the serialized artifact is reloaded and must
  reproduce the verified coefficients exactly.
- Write-once: the artifact is written only if absent; replacing it
  requires the explicit `--force` flag.

Output artifact path + sha256 pin:

- Path (default `PAEXT_V2_CHECKPOINT_PATH`):
  `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\checkpoints\h3_raw_checkpoint.json`
  (reconstructed 2026-10-20: one authorized deterministic run, all three
  blocks verified <=1e-8, MLflow VERIFIED; write-once, never overwritten).
- The artifact embeds a `sha256` pin computed over its canonical JSON
  payload (`checkpoint_sha256`, sort-keys + compact separators). The
  reconstruction printed and REGISTERED this canonical payload hash as
  `checkpoint_sha256_expected` in
  `freeze_pregame_pa_ext_v2.json` (this directory; the freeze/registration
  config) — see the file's `checkpoint_registration` record for the full
  receipt: canonical payload hash (the scoring pin) vs the distinct
  raw-file sha256 (MLflow artifact byte-verification only), pipeline ID,
  MLflow run ID, input identities, and per-block verification results.
  Registration MERGED (PR #21, `ccd0148`) and does NOT authorize scoring:
  the scoring run above is the only execution on record and it failed
  acceptance; `run_real` must not be executed again without a new
  explicit owner authorization. (The freeze JSON registration_status
  string still reads PENDING REVIEW - authored before the merge; the
  merged state supersedes it. The freeze JSON is deliberately unedited:
  its `config_sha256` covers the top-level config including that string,
  and rewriting it would invalidate the registered config hash.)
  On every scoring load, `load_serialized_checkpoint` verifies the
  artifact's canonical payload hash against the registered pin and fails
  loud with `CHECKPOINT_REGISTERED_PIN_MISMATCH` on mismatch; the pin is
  a fixed literal, never computed dynamically from whatever artifact
  scoring happens to load.

Dual-phase MLflow tracking (optional flags; same SHARED D-1 wrapper as
the frozen LightGBM command):

```
python research/offseason_2026/pregame_pa_ext/build_checkpoint.py \
    --tracking-uri sqlite:///<path>/mlflow.db \
    [--pipeline-id <batch-id>]
```

The reconstruction run is logged tagged `phase=reconstruction` +
`pipeline_id` (batch id + UTC timestamp by default) with the
verification gate result (per-block `verification_max_abs_diff__*`
metrics) and the serialized artifact (byte-hash verified on retrieval).
The adapter scoring run (`run_real(..., tracking_uri=...,
pipeline_id=...)`) is tagged `phase=scoring` with the same
`pipeline_id`, so both phases are retrievable as ONE pipeline
(`tags.pipeline_id = '<id>'`). A tracking failure in either phase
surfaces as `TrackingFailure` AFTER the phase's canonical artifact is
written; the artifact stays untouched on disk and no refit is
triggered.

## Command (b) — scoring (adapter execution, repeatable)

```
python -c "import sys; sys.path.insert(0, r'research/offseason_2026'); from pregame_pa_ext.adapter import run_real; run_real()"
```

Run from the worktree root. The adapter NEVER refits and NEVER
reconstructs at execution time.

Inputs consumed:

1. **Serialized checkpoint artifact** — loaded only via
   `load_serialized_checkpoint` from the path above. Missing artifact
   fails loud with `MISSING_CHECKPOINT_ARTIFACT`; hash-pin mismatch
   fails loud with `CHECKPOINT_HASH_MISMATCH`. No fallback of any kind.
2. **Projected lineups** —
   `C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1\data\projected_lineups_variant_v2.parquet`
   (frozen projected unique-batter-v2; sha256
   `b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b`,
   re-derived 2026-10-19). Uncovered slots are dropped and counted.
3. **PA table** — `overnight-p2\data\pa_table.parquet` (same identity
   as above), used for strictly-prior feature state only; no realized
   outcome can reach a projected feature (strictly-prior shift + hard
   cutoff gate: every source date strictly before the start's
   `game_date`, else STOP).
4. **BF PMFs (WIRED — executable end-to-end)** — both registered RAW
   count-PMF arms (H3-raw cycled-prefix-mean + LOG5 corrected) are mixed
   over the shared BF workload PMF (bf-workload-v1 BASE empirical
   `pmf37_0..36`, extended by `kcount_combiner.bf_pmf_from_37`; 24
   buckets, tail absorbed at k>=23). `run_real()` now wires the artifact
   itself: `load_bf_forecasts` reads
   `C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\data\bf_forecasts.parquet`
   (dir overridable via `BF_WORKLOAD_V1_DIR`; start grain
   `(game_pk, side, pitcher)`, also unique on `(game_pk, pitcher)`; the
   registered artifact carries the `side` column directly) and gates its
   sha256 against the registered pin
   `c9c2762fb2c1c239e5645c49fa92eda50bd652d26e54755ac8bf0c28fa968679`
   (`BF_PMF_SHA_MISMATCH` on any mismatch; verified matching on disk
   2026-10-19, 14,574 rows). `validate_bf37_by_start` then enforces, per
   scored start, fail-loud with NO invented replacement distributions:
   unique start keys on both registered grains
   (`BF_PMF_DUPLICATE_START_KEYS`), complete BF coverage of every scored
   start (`BF_PMF_COVERAGE_MISSING`), artifact-vs-projected `game_date`
   match (`BF_PMF_DATE_MISMATCH`), finite/nonnegative/normalized pmf37
   rows (`BF_PMF_DISTRIBUTION_INVALID`), and the registered cap-60
   geometric-tail conversion (`BF_PMF_CONVERSION_FAILED`). Starts
   containing a cold-start slot remain EXCLUDED from the PMF arms with
   explicit counts (never league-rate filled). Synthetic end-to-end
   coverage: `tests/test_bf37_wiring.py` (run_real on synthetic lake
   fixtures produces the registered count-PMF artifacts; negative tests
   for missing coverage, duplicate keys, sha mismatch, invalid
   distribution, conversion failure, missing checkpoint).

Output destination (write-once):

- `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\outputs\projected_pa_probs_v1.parquet`
  — `write_once` refuses to overwrite an existing parquet. Rows keyed
  `(game_pk, pitcher, batter, slot, game_date)`, identity-gated unique;
  per-slot `source_type` + `exclusion_reason` provenance columns; per
  start, the registered count-PMF / evaluation artifacts
  `pmf_h3_raw` / `pmf_l5_raw` (24-bucket combined count PMFs, 0..23,
  tail absorbed at k>=23) plus `mean_k_h3_raw` / `mean_k_l5_raw`; null
  PMFs only on cold-start rows / rows of cold-slot starts. The run
  summary additionally records `bf37_artifact` (source identity, path,
  input sha256, registered pin, artifact rows) and `bf37` (scored/matched
  start counts, registered extension identity, kcount cap, k_max).

## Spec linkage — cold-start handling (owner decision PENDING)

- **Cold-start handling: EXCLUSION implemented as a provisional approach;
  owner decision pending on fallback vs exclusion.** A slot whose pitcher
  or batter has no PA-table history carries
  `source_type = cold_start_no_prior`, a null PA probability, and an
  explicit `exclusion_reason`; it is EXCLUDED from scoring. This is NOT a
  ruling and does NOT supersede the league-rate fill design in
  `research/offseason_2026/bf_lane/PROJECTED_LINEUP_SPEC.md` section 3:
  that spec section remains the registered candidate fallback, and the
  choice between exclusion and league-rate fallback is BLOCKED awaiting an
  explicit owner decision.
- **The frozen recipe consumes NO league-rate fallback.** A missing
  checkpoint artifact never falls back to league-rate scoring
  (`MISSING_CHECKPOINT_ARTIFACT`); a missing entity history never
  produces a league-rate-substituted probability (the PA is excluded).
  `lg_rate` remains a registered frozen FEATURE input (w150 shrinkage;
  in `attach_prior_features` the EW fill co-occurs only with
  `cold_start = 1`), and the cold-start exclusion guarantees those
  league-derived features on excluded rows never reach a scored
  probability.
- Unseen (pitcher, batter) pairs with full entity history ARE scored:
  the H3-raw checkpoint consumes the 8 features only, never player IDs
  (feature-based scoring, ID-blind).

## Local suite status (2026-10-20 refresh; suite/head evidence)

Affected-suite evidence at the reviewed/merged head `1b3bfd3` (Chat 2
exact-head review): tracking 6/6 + checkpoint pin 10/10 = 16/16 affected
tests (549.13s, mlflow installed); CI `test-and-validate` PASS; the
portable tracking CI lane executes the complete tracking module with a
zero-skip guard (PR #22, merged `3c62655`). Suite counts carry their
suite + head per the reporting rule.

## Local suite status (retained failure — receipt note; dated 2026-10-20, commit `d4d810e`)

The local full suite is NOT fully passing: it carries **1 pre-existing,
CRLF-dependent failure**,
`tests/test_count_b1_end_to_end.py::test_freeze_recovery_addendum_convention`
(reproduced this session: pinned `execution_amendment_v1.runner.sha256`
`5b54c362...20fdcc9` vs working-copy bytes `b8caa3e7...e9829dd` — a
line-ending-dependent byte mismatch in the freeze's runner pin).
Classification: pre-existing, UNRELATED to the pregame-pa-ext-v2 lane.
**Not fixed, not worked around.** The pregame-pa-ext adapter suite
passes: 20/20 (`tests/test_pregame_pa_adapter.py`), the bf37 wiring
suite passes: 17/17 (`tests/test_bf37_wiring.py`, synthetic-only,
CI-safe), the registered-pin gate suite passes: 5/5
(`tests/test_pregame_pa_checkpoint_pin.py`), and the tracking suite
passes: 6/6 (`tests/test_pregame_pa_tracking.py`, synthetic-only,
CI-safe: shared-wrapper verification, no-tracking default, scoring-phase
TrackingFailure, dual-phase pipeline_id retrieval, reconstruction-phase
failure preserves the checkpoint with no refit).
