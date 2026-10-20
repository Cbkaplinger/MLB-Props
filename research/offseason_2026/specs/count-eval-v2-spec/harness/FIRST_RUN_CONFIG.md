# FIRST_RUN_CONFIG — first-run packet v1 (PA-only baseline reproduction)

Registered 2026-10-15. Companion to `first_run_packet_v1.json` (the frozen,
hash-bound config; this doc is the human-readable statement of the same
registration). Branch `research/market-eval-v2`.

- **Status: NOT-EXECUTED — awaiting owner authorization.** Nothing here
  authorizes a run (spec section 8 execution gate).
- **run_id:** `first-run-v1-e59da946da21`
- **canonical config sha256:** `e59da946da218bd43af05d0dde3ddeace5b30c3280b249767158eec94ab15fc1`
  (sha256 over `json.dumps(config, sort_keys=True, separators=(',',':'))` of the
  packet's `config` object)
- **Output destination:** `C:\Users\ckaplinger\MLB-Props-Research\first-run-v1\`
  — confirmed nonexistent 2026-10-15; write-once (the harness refuses to
  overwrite an existing output dir, `WriteOnceError`).
- **No BF-driven window restriction: registered folds stand.**

## Inputs (frozen, sha256-bound)

| role | path | sha256 |
| --- | --- | --- |
| PA table | `C:\Users\ckaplinger\MLB-Props-Research\p1-harness-v2\data\pa_table.parquet` | `e30d8561d8d0fbb9ab0eae562076312a29eeb1476172d533c3d93570959a85f0` |
| features (canonical) | `C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\features_v3.parquet` | `163ad43356e66649274682a473a4015c71f04be6c2f074f15e417c3d49b7e8f8` |

Supersession note: the canonical 8-feature H3 set (incl. `ew_pitcher` /
`ew_batter`, EW-90d) lives only in `overnight-p2\data\features_v3.parquet`,
which SUPERSEDES the p1-harness-v2 features frame for this run. The
p1-harness-v2 default features frame
(`...\p1-harness-v2\data\features.parquet`, 731,347 x 21, sha256
`b2ec8c90...457e9b98`) lacks the EW columns and is documented as superseded —
not used.

## Candidates (frozen)

| candidate | fitted features | preprocessing | calibration lanes | hyperparameters |
| --- | --- | --- | --- | --- |
| P0_log5 | none — closed-form log5 identity on `p_pitcher_prior_w150`, `p_batter_prior_w150`, `lg_rate` | none (no scaler, no fit) | no calibrator; RAW lane only | none |
| P1_B_logreg | 6 frozen B features: `p_pitcher_prior_w150`, `p_batter_prior_w150`, `lg_rate`, `n_prior_pitcher`, `n_prior_batter`, `cold_start` | StandardScaler fit on base_train ONLY, one scaler per fold | block sigmoid on the 60-PA-bearing-day cal sub-block; RAW and CAL both output, both labeled (`pred_raw` / `pred_cal`), both reported | C=1.0, max_iter=1000 |
| P1_H3_incumbent_refit | 8 H3 features = the 6 B features + `ew_pitcher` + `ew_batter` (EW-90d) | StandardScaler fit on base_train ONLY, one scaler per fold | same block sigmoid; RAW and CAL both output, both labeled, both reported | C=1.0, max_iter=1000 |

- **H3 label (binding):** incumbent-procedure refit — re-executes the frozen H3
  fitting procedure on the registered folds; NOT proven prediction-equivalent
  to historical incumbent outputs (`pred_H3_raw`); equivalence requires a
  separate real-data comparison requiring authorization. Formerly registered as
  `P1_H3_replay` (superseded ID; see CANDIDATE_MAP "Superseded IDs").
- **Frozen feature-construction constants** (inherited from the incumbent
  features_v3 build; not refit or retuned here): prior weight w=150, EW
  half-life 90 days.
- **Calibration sub-block:** block sigmoid (1-D unpenalized logistic of y on
  logit(p)) fit ONLY on the calibration sub-block per fold — the 60 calendar
  days bearing PAs `[cal_first..cal_last]`, derived at runtime
  (`cal_last = max game_date <= train_end`; `cal_first = cal_last - 59 days`).

## Evaluation (frozen)

- **Folds:** the four registered folds (anchors exactly
  `run_ladder.py:60-66`): block_2024H1, block_2024H2, block_2025H1,
  confirm_2025H2. Dev = first three (pooled); confirm_2025H2 executed LAST,
  never pooled into dev.
- **Baseline comparator:** `P0_log5`.
- **Bootstrap:** paired slate-date, block-stratified, row-weighted num/den;
  **seed 20261001, n_boot 2000**; ONE draw stream shared across candidates.
- **Metrics:** per-fold + pooled-dev log loss / Brier; paired-vs-baseline CIs.

## PREFLIGHT (computed 2026-10-15, read-only — no fit, no score, no outputs)

**Population / exclusion counts**

| quantity | value |
| --- | ---: |
| PA-table rows (p1-harness-v2 pa_table.parquet) | 731,347 |
| canonical features frame rows (features_v3.parquet) | 549,296 |
| PA-table rows absent from the canonical features frame | 182,051 |
| absent by season | 2022: 182,051 (ALL exclusions are 2022 warm-up) |
| absent by role | starter_pa: 106,558; reliever_pa: 75,493 |
| absent inside ANY fold assessment window | **0** |

Every excluded row is a 2022 warm-up row outside the 2023-01-01..2025-12-31
eligibility window. History categories of the excluded rows (vs the pitcher's
first-ever PA): first-ever PA on/after row date 8,251; within prior 7 days
8,592; prior history > 7 days 165,208.

**Explicit evaluation population** (from the loaded 549,296-row frame,
2023-03-30..2025-09-28, overall K rate 0.225115; starter_pa 319,714 /
reliever_pa 229,582):

| fold | base_train | calibration (60 PA-bearing days) | assessment rows | assessment dates | K rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| block_2024H1 (cal 2023-08-03..2023-10-01) | 123,081 | 61,023 | 94,458 | 95 | 0.222437 |
| block_2024H2 (cal 2024-05-02..2024-06-30) | 219,078 | 59,484 | 87,808 | 88 | 0.229546 |
| block_2025H1 (cal 2024-08-02..2024-09-30) | 306,791 | 59,579 | 95,357 | 98 | 0.219323 |
| confirm_2025H2 (cal 2025-05-02..2025-06-30) | 401,590 | 60,137 | 87,569 | 86 | 0.225319 |

Pooled dev = 277,623 rows; confirm_2025H2 separate (87,569). The four
assessment counts (94,458 / 87,808 / 95,357 / 87,569) MATCH the executed
overnight-p2 assessment keys. Per-fold eval identity sha256 values are
registered in `first_run_packet_v1.json` (`preflight.fold_partitions`).

**Shared-rows/labels verification across candidates.** Features identity is a
subset of PA-table identity (anti-join = 0), so the loader's inner join drops 0
rows (it fails loud otherwise, comparison.py:166-170). All candidates score the
SAME eval rows: the runner asserts the per-fold eval identity hash is identical
across candidates (comparison.py:743-744) and records it per candidate in the
manifest; pinned by `test_eval_identity_hash_matches_across_candidates`. One
loaded frame supplies `y` to every candidate; each preds parquet re-records `y`
and the fold eval identity sha256.

**Feature integrity.** All 8 required feature columns + the 3 log5 inputs have
ZERO nulls on the loaded frame. Availability guard passed on the full canonical
frame (all `src_date_*` non-null and strictly < game_date; all `src_type_*`
non-null).

**Preserved 2025 exposure history (blocks already inspected).** EW-90d rolling
state (`ew_pitcher`/`ew_batter`) carries its own `src_date_ew_*` strictly prior
to `game_date` (guard passed over all 549,296 rows), so 2025 assessment rows
retain full prior exposure history through each game date. 2025 blocks already
inspected read-only before this packet: (1) the executed assessment key sets
`keys_executed_block_2025H1.parquet` and `keys_executed_confirm_2025H2.parquet`
verified bit-identical to harness fold construction (CANDIDATE_MAP "Executed
bit-identity check", 2026-10-15); (2) canonical `features_v3.parquet` direct
read, 549,296 x 54, ew_* present (HANDOFF_CAPABILITIES.md section 2); (3) this
packet's preflight re-derived all four fold partitions + eval identity hashes
read-only (2026-10-15). No 2026 rows exist in either input frame (2026 CLOSED).

## Literal execution command

Run from the `market-eval-v2` worktree root (repo
`C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\market-eval-v2`):

```
python -c "import json,sys; d='research/offseason_2026/specs/count-eval-v2-spec/harness'; sys.path.insert(0,d); from comparison import RunConfig, run_comparison; p=json.load(open(d+'/first_run_packet_v1.json',encoding='utf-8')); c=p['config']; print(run_comparison(RunConfig(pa_table_path=c['inputs']['pa_table_path'],features_path=c['inputs']['features_path'],candidates=c['candidate_order'],output_root=c['output_destination'],run_label=p['run_id'])))"
```

Command semantics verified read-only (packet parses; `RunConfig` constructs
with the registered candidates; destination absent). The command itself was NOT
run — execution is gated on owner authorization. The harness creates
`<output_destination>\<64-hex harness run_id>\` (its own sha256 identity over
its canonical config + input sha256s) and records this packet's run_id as
`run_label`; the manifest binds both IDs plus the input sha256s above.
