# COUNT REGISTRATION — bf-2026-eval-v1 / count_b1 (2026-10-16)

**Status: FROZEN — NOT EXECUTED.** This is a separate, clearly-marked frozen
registration (distinct from the B1 closeout commit). It publishes the
count-layer comparison contract between the closed-out B1 run and the B0
empirical baseline. **The comparison is NOT executed in this commit.**
Machine-readable twin: `freeze_count_eval_v1.json` (same directory).

## What is being compared

Paired count-layer comparison of two supplied BF PMFs — everything else held
identical:

| Arm | Supplied BF PMF (the ONLY varying input) |
| --- | --- |
| B0 | Empirical: `kcount_combiner.bf_pmf_from_37(stored BASE pmf37)`, cap-60 extension, unchanged |
| B1 | Ridge-recentered: persisted `b1_ext_*` extended PMF from `b1_per_row_forecasts.parquet` |

Both arms integrate their BF PMF with the **same** per-start projected PA
probability `p_bar` (frozen scalar shrunk pitcher K rate, w=150 log5 form,
kcount-integration I3b prior construction, pa-k pool strictly before
game_date; sha256 `b91486525988da836303d55dab2718164e214bb6679a41225fcc4d79147bf4c4`,
identical both arms, so the paired contrast is invariant to it). The
realized-sequence diagnostic's realized-PA p_bar is explicitly NOT reused.

## Frozen identities (exact hashes)

| Item | sha256 |
| --- | --- |
| B1 run manifest `...\bf-lane-v1\b1_run_v1\run_manifest.json` | `37910a98b69177704a8147c2c5e04880a893927c368d598329a674298943b16a` |
| B1 `metrics.json` | `0453da67f0c37fdddc37cc66492769014b419c0a0d11bbb46ee1d79da74002f8` |
| `b1_registration.json` | `e10ee2c4a9a56ece249ba3f2203762a34a6a524c9dff3b432d4afca43756425d` |
| `b1_per_row_forecasts.parquet` (supplies the B1 PMFs) | `a5f0ad81318c25e34d8837ee56d8728db63df4cd56049d8497d126d6880fcb69` |
| `b0_audit.json` (verdict PASS, pregame-valid 7,194/7,194) | `a420dda40317b517dcf7d4cfcafee5d9e8877f52299d1e716db5d70071218a69` |
| `bf_forecasts.parquet` (bf-workload-v1 lineage) | `c9c2762fb2c1c239e5645c49fa92eda50bd652d26e54755ac8bf0c28fa968679` |
| `build_bf_forecasts.py` | `8893918b3d001f2e3d481eae40e000b32a3968545e37b84f4ba82ba9f7708ef6` |
| `kcount_combiner.py` | `94f57a49c0996df5147fb961a085fd229d0ba0e3903c6da0ced9f2d3b670f18f` |
| `start_metrics_v2.parquet` (outcomes) | `af6814ec7ea73b4ac941dd52f185139062b987762d639203b867e15bb4817fde` |
| `pa_table.parquet` (PA folds lineage) | `e30d8561d8d0fbb9ab0eae562076312a29eeb1476172d533c3d93570959a85f0` |

Baseline identity: **bf-workload-v1 lineage** — the audited BASE empirical
BF build (`bf_forecasts.parquet` → `kcount_combiner` → count/RPS stack),
pregame-valid on every cohort start. B1 provenance: closeout commit `6ee8544`
(ACCEPT WITH LIMITATION; D1/L2/L3 closed, no registered number affected).

## Held identical (both arms)

- **Cohort:** 7,194 first-pitcher-of-record starts, 2024-07-01..2025-12-31,
  272 slate dates.
- **Folds:** verbatim from `b1_registration.json` — block_2024H2 +
  block_2025H1 dev-scored; block_2024H1 declared empty; confirm_2025H2
  EXCLUDED-NOT-SCORED; 2026 CLOSED.
- **Row eligibility / availability states:** own_distribution (prior_n>=10),
  insufficient_history_league_pool (1<=prior_n<=9, short outings preserved,
  scored), career_debut_league_pool (prior_n==0).
- **p_bar** (above), **count integration** (`combine_count`, k_max 24,
  milestones 6/8/10/12, summed count-RPS convention), **calibration** and
  **aggregation** (block-stratified row-weighted pooled dev; resampling unit
  = slate date), **observed outcomes** (realized BF / realized strikeouts
  from start_metrics_v2).

## Primary endpoint and test

- **Paired count-RPS, B1 − B0** (`C_b1_ridge_vs_b0_empirical`).
- Slate-date bootstrap **n=2000, seed 20261001**, block-stratified by fold,
  one shared draw stream.
- **Null-centered** approximate bootstrap test, two-sided; percentile CIs
  UNADJUSTED.
- **Holm family = 1 primary contrast** (per `b1_registration.json`). The
  recency-batch-v1 4-contrast RAW-Brier family is a different lane and is
  **not** reused.

## Expected row accounting

| Scope | Rows | Notes |
| --- | --- | --- |
| Full registered window | 7,194 starts / 272 slate dates | own_distribution 6,059 · insufficient_history 966 · career_debut 169 · failed joins 0 |
| Dev-scored (this run) | 4,866 rows / 186 slate dates | block_2024H2 2,334 + block_2025H1 2,532 |
| — career-debut pass-through | 120 | B1 forecast = B0 PMF **unchanged** (shift 0); excluded from Ridge fit/scored rows, inside aggregates |
| — insufficient history | 698 | scored, short outings preserved |
| — own distribution | 4,048 | |
| confirm_2025H2 | 2,328 | EXCLUDED-NOT-SCORED |
| block_2024H1 / 2026 | 0 / CLOSED | |

**217 flagged recenter records (217/4,866 = 4.5%):** consumed AS-IS from the
persisted B1 run — `recenter_mass_loss_flag` rows (dropped mass > 0.01 guard;
max 0.42, median 0.0347) are renormalized valid PMFs, carried into every
aggregate, reported, never silently accepted, never excluded. Row counts are
asserted at run time against this table; any mismatch fails loud.

## Output location (write-once) — confirmed absent

`C:\Users\ckaplinger\MLB-Props-Research\bf-2026-eval-v1-outputs\count_b1\`

Verified ABSENT on 2026-10-16 (the parent `bf-2026-eval-v1-outputs` directory
does not exist either). The run dir is write-once: if it exists at start, the
runner refuses without writing.

## Immutable manifest requirement

The run dir must contain a `run_manifest.json` **derived only from that
run's final artifacts** (config/registration/input/artifact hashes,
execution/recovery timestamps taken from persisted records, and the verdict),
with the full sha256 inventory. The manifest's own sha256 is recorded
outside the manifest (in the closeout/registration documentation); it is
never edited in place.

## Persistence inventory (all required at run time)

1. Per-row forecast frame, both arms: row IDs (game_pk, side, pitcher), fold,
   availability state, supplied-BF-PMF identity, per-row count-RPS /
   logscore / milestone Briers, mean forecasts.
2. Per-row 24-bucket count PMFs both arms + per-row p_bar values
   (hash-recorded at run time).
3. Per-date paired sums CSV (n, b0_rps, b1_rps per slate date).
4. Bootstrap replicate matrix (npy; shared stream, fixed metric order).
5. Aggregates: per-fold + pooled dev — n, count_rps, count_logscore,
   bias/MAE/RMSE, 4 milestone Briers, coverage/width (P10-P90, P25-P75) —
   both arms + paired deltas.
6. Calibration deciles, both arms.
7. Contrast record: delta, null-centered p, Holm p, method text, n_boot,
   seed.
8. Row-count assertion table vs this registration.
9. `metrics.json` with full `artifact_inventory_sha256` written inside the
   single compare pass.
10. MLflow logging via the shared `track_and_verify.py` chain
    (compare once → save → log → verify fresh-process) + `tracking_status.json`.
11. `run_manifest.json` per the immutable-manifest requirement.

## Fail-closed / no-rerun conditions

- **Identity gate before any fitting/scoring:** registration sha, B1 manifest
  + metrics.json hashes, input hashes (bf_forecasts, start_metrics_v2,
  pa_table, builder, combiner), B0 audit PASS verdict — all re-derived from
  disk; any mismatch = exit nonzero, nothing written.
- **Destination-exists check:** refuse if the output dir exists.
- **Compare executed EXACTLY ONCE.** Tracking failure preserves partials,
  never triggers a refit or rescore, never retries silently (a log-phase-only
  recovery is permitted and recorded).
- **No rerun on any failure:** a failed or nonconforming run is never
  re-executed into the same destination. Any deviation from this freeze
  requires a NEW registration, never an amendment.
- **Execution requires explicit owner authorization** after exact-head CI +
  review. This commit does not execute the comparison.
- **No promotion, no production change:** dev-only evidence; confirm_2025H2
  and 2026 stay closed.

## Execution amendment v1 (ADDITIVE — execution plumbing only, 2026-10-16)

**No scientific fields changed; this amendment only pins execution plumbing.**
Everything above this section (what is compared, frozen identities, held
identical, primary endpoint and test, row accounting, output location,
immutable manifest requirement, persistence inventory, fail-closed /
no-rerun conditions) is byte-unchanged. The machine-readable twin
`freeze_count_eval_v1.json` likewise changes ONLY by the additive
`"execution_amendment_v1"` key. This amendment closes preflight item 5d
(COUNT_RUN_PREFLIGHT.md): the runner and its literal command are now
committed and reviewed BEFORE any execution.

- **Runner:** `research/offseason_2026/bf_lane/run_count_b1_v1.py`,
  sha256 `209eef4b2652f9d5a32d189444e0db48895fc19daf536b9906f54cabebb026d3`
  (originally committed as
  `7a3956d294d69443023fe513bf66481b198b8b1a7e5117f20b0de2a1cd8db07a`; the
  sha256 was updated in the 2026-10-16 execution-repair commit after the
  missing-parquet-destination repair, and again in the 2026-10-17
  recovery-name normalization fix after the POSIX CI failure — see the
  recovery addendum below;
  the runner re-derives its own bytes against the pinned hash and refuses
  on mismatch). It reuses the
  frozen count scoring machinery verbatim: `kcount_combiner` (registered
  sha `94f57a49...`) for `bf_pmf_from_37` / `combine_count` / summed
  count-RPS, and the harness `comparison.py` `slate_date_draws` +
  `null_centered_contrast_test` (n=2000, seed 20261001, block-stratified,
  one shared draw stream, null-centered two-sided p, Holm family of 1).
- **Immutable config:** `research/offseason_2026/bf_lane/freeze_count_eval_v1.json`
  (scientific contract unchanged; runner hash-gates its endpoint,
  row-accounting, and output blocks against the registered values).
- **Literal command** (run from the working directory below; execution
  remains owner-gated via `--i-accept-real-data-execution`):

  ```
  python research/offseason_2026/bf_lane/run_count_b1_v1.py --freeze research/offseason_2026/bf_lane/freeze_count_eval_v1.json --i-accept-real-data-execution
  ```

- **Working directory:**
  `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\market-eval-v2`
- **Output root (write-once):**
  `C:\Users\ckaplinger\MLB-Props-Research\bf-2026-eval-v1-outputs\count_b1\`
- **Environment identity capture command** (run before execution; writes
  next to, not inside, the 22-file run dir):

  ```
  python -c "import sys, platform; print(sys.version); print(platform.platform())"; python -m pip freeze | Out-File -Encoding ascii C:\Users\ckaplinger\MLB-Props-Research\bf-2026-eval-v1-outputs\pip_freeze_count_b1_v1.txt
  ```

- **Preflight assertion:** the runner asserts the write-once destination is
  absent BEFORE any read or write and exits nonzero if it exists
  (`preflight_destination_absent`; no-rerun rule enforced).
- **Declared 22-file output inventory schema** (exact set enforced by the
  runner at end of run; `run_manifest.json` derived only from final
  artifacts, its own sha256 recorded outside the run dir, never edited in
  place):
  `count_b1_aggregates_block_2024H2.json`,
  `count_b1_aggregates_block_2025H1.json`, `count_b1_aggregates_pooled.json`,
  `count_b1_bootstrap_replicates.npy`,
  `count_b1_calibration_deciles_block_2024H2.json`,
  `count_b1_calibration_deciles_block_2025H1.json`,
  `count_b1_calibration_deciles_pooled.json`, `count_b1_contrast.json`,
  `count_b1_coverage_width.json`,
  `count_b1_flagged_recenter_records.json`,
  `count_b1_identity_gate.json`, `count_b1_per_date_paired_sums.csv`,
  `count_b1_per_row_pmf_b0.parquet`, `count_b1_per_row_pmf_b1.parquet`,
  `count_b1_per_row_scores.parquet`, `count_b1_p_bar_inventory.json`,
  `count_b1_row_count_assertions.json`, `lgbm_equal_info_config.json`,
  `metrics.json`, `retrieved/lgbm_equal_info_config.json`,
  `run_manifest.json`, `tracking_status.json`.

This amendment commit does NOT execute the comparison; execution still
requires explicit owner authorization after exact-head CI + review.

## Execution-recovery addendum v1 (ADDITIVE — recovery destination only, 2026-10-16)

**No scientific field changed.** The first execution attempt on 2026-10-16
FAILED at the first aux parquet write with `TypeError:
DataFrame.write_parquet() missing 1 required positional argument: 'file'`
(polars requires the destination argument; the three aux parquet call sites
called `write_parquet()` bare). **No analytical results were produced** —
no contrast, aggregate, bootstrap, calibration, or manifest artifact existed
before the failure. This addendum records the recovery convention; it is
purely execution plumbing, additive to everything above.

- **Preserved failure evidence (IMMUTABLE):**
  `C:\Users\ckaplinger\MLB-Props-Research\bf-2026-eval-v1-outputs\count_b1\`
  containing `count_b1_error_log.json` (status FAILED, full traceback).
  Never deleted, overwritten, relabeled, or written into again.
- **Recovery destination (registered, write-once):**
  `C:\Users\ckaplinger\MLB-Props-Research\bf-2026-eval-v1-outputs\count_b1_recovery_v1\`
  — sibling of the registered destination under the same output root, named
  by the convention `<registered output dir name>_recovery_v1`; recovery
  run id `bf-2026-eval-v1-count_b1_recovery_v1`. The successful recovery run
  is distinguishable from the preserved failure by its directory name and by
  the `recovery_run_v1` block inside its `run_manifest.json`.
- **Machine-readable twin:** additive `"recovery_run_v1"` key in
  `freeze_count_eval_v1.json` (original destination, FAILED status, error,
  preserved-evidence flag, recovery destination + convention, unchanged
  no-rerun rule). The `execution_amendment_v1.runner.sha256` pin was updated
  to the repaired runner bytes
  (`fc097b5697f75934e286002a18653a00046ca540d7b6050d5e8744b782e47be3`, and
  again to
  `209eef4b2652f9d5a32d189444e0db48895fc19daf536b9906f54cabebb026d3` in the
  2026-10-17 recovery-name normalization fix) —
  execution plumbing only; every scientific field is unchanged.
- **Runner repair:** the three aux parquet call sites
  (`count_b1_per_row_scores.parquet`, `count_b1_per_row_pmf_b0.parquet`,
  `count_b1_per_row_pmf_b1.parquet`) now route through
  `write_once_parquet(path, df)`, which performs the write-once check and
  then passes the explicit destination path to
  `DataFrame.write_parquet`. The runner additionally resolves the effective
  write-once run dir from the additive freeze key (`resolve_recovery_
  destination`), prefights the recovery destination for absence, and asserts
  the preserved original destination + error log still exist before any
  execution.
- **Recovery-name normalization fix (2026-10-17, CI only):** the exact-head
  CI run on ubuntu rejected the registered pair because `Path(...).name`
  keeps a trailing `\` on POSIX (backslash is not a separator there), so the
  name guard compared raw platform-flavored strings.
  `resolve_recovery_destination` now compares separator-normalized path
  components (`path_components`, split on `/` and `\`, trailing separators
  dropped) for both the name check and the sibling check. The registered
  pair — failed evidence destination `count_b1`, recovery destination
  `count_b1_recovery_v1` — is accepted on any platform; no scientific
  field, destination, or rule changed, and no execution was performed.
- **No-rerun rule UNCHANGED:** write-once applies to the recovery
  destination too; a failed recovery is never re-executed into the same
  destination; any further deviation requires a NEW registration, never an
  amendment.
- **Synthetic coverage:** `tests/test_count_b1_end_to_end.py` exercises the
  repaired write/finalize path on synthetic fixtures (all 22 declared files,
  parquet read-back, manifest generation, inventory enforcement, and a
  regression assertion that `write_parquet` is always called with an
  explicit destination), plus tests for the recovery-convention resolution.
