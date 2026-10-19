# COUNT EVAL COMMANDS — pregame-pa-ext-v2 (2026-10-19)

**Status: SPECIFIED-NOT-EXECUTED.** Two distinct commands, deliberately
separated per the owner instruction recorded in commit `6feb32e`:
checkpoint RECONSTRUCTION runs once against the private lake; adapter
SCORING loads only the serialized artifact and never refits. Neither
command has been executed on real data. Any execution stays behind the
owner's projected-batter scoring gate (`docs/PROJECT_STATE.md`).

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
  (ABSENT as of 2026-10-19).
- The artifact embeds a `sha256` pin computed over its canonical JSON
  payload (`checkpoint_sha256`, sort-keys + compact separators). The
  pin value is printed at build time and MUST be registered before any
  scoring run; the loader refuses a tampered artifact with
  `CHECKPOINT_HASH_MISMATCH`.

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
4. **BF PMFs** — both registered RAW count-PMF arms (H3-raw
   cycled-prefix-mean + LOG5 corrected) are mixed over the shared BF
   workload PMF (bf-workload-v1 BASE empirical `pmf37_0..36`, extended
   by `kcount_combiner.bf_pmf_from_37`; 24 buckets, tail absorbed at
   k>=23), attached per start via the `bf37_by_start` argument of
   `build_projected_pa_probs`. **Wiring note:** the committed
   `run_real()` convenience driver does not yet wire a bf37 source; the
   BF-PMF-attached pass requires supplying `bf37_by_start` (keys
   `game_pk, side, pitcher` + 37 pmf37 columns from the bf-workload-v1
   `bf_forecasts.parquet`) at the call boundary. Per the preflight 5d
   convention, that literal wiring/command must itself be committed and
   reviewed before any real-data execution. Starts containing a
   cold-start slot are EXCLUDED from the PMF arms with explicit counts
   (never league-rate filled).

Output destination (write-once):

- `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\outputs\projected_pa_probs_v1.parquet`
  — `write_once` refuses to overwrite an existing parquet. Rows keyed
  `(game_pk, pitcher, batter, slot, game_date)`, identity-gated unique;
  per-slot `source_type` + `exclusion_reason` provenance columns.

## Spec linkage — accepted ruling (2026-10-19)

- **Cold-start behavior = EXCLUSION, not fallback.** A slot whose
  pitcher or batter has no PA-table history carries
  `source_type = cold_start_no_prior`, a null PA probability, and an
  explicit `exclusion_reason`; it is EXCLUDED from scoring. This
  implements the accepted ruling and SUPERSEDES the league-rate fill
  design in `research/offseason_2026/bf_lane/PROJECTED_LINEUP_SPEC.md`
  section 3 for the paext-v2 adapter path (that spec section describes
  the earlier candidate registration, not the implemented frozen
  behavior).
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

## Local suite status (retained failure — receipt note)

The local full suite is NOT fully passing: it carries **1 pre-existing,
CRLF-dependent failure**,
`tests/test_count_b1_end_to_end.py::test_freeze_recovery_addendum_convention`
(reproduced this session: pinned `execution_amendment_v1.runner.sha256`
`5b54c362...20fdcc9` vs working-copy bytes `b8caa3e7...e9829dd` — a
line-ending-dependent byte mismatch in the freeze's runner pin).
Classification: pre-existing, UNRELATED to the pregame-pa-ext-v2 lane.
**Not fixed, not worked around.** The pregame-pa-ext adapter suite
passes: 20/20 (`tests/test_pregame_pa_adapter.py`).
