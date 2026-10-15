# BUILDER_HANDOFF.md - market-eval / count-eval-v2 recency batch (single consolidated handoff)

Written 2026-10-15. This is the ONE handoff doc for the builder (Chat 2). It supersedes the
scattered handoff notes only as a pointer sheet; the underlying cards and specs stay canonical
(EXPERIMENT_CARD.md, REVIEW_HANDOFF.md, harness/RECENCY_BATCH_REGISTRATION.md,
harness/freeze_recency_batch_v1.json). Every hash below was recomputed from the actual files
on 2026-10-15 by the pack author; re-verify before executing (commands in section 6).

## 1. Published state (remote)

| Item | Value |
| --- | --- |
| Remote branch | `research/market-eval-v2` (origin) |
| Published remote SHA | `972fc554d956f3993552690c053967fb4c539a85` |
| PR | #3, DRAFT: market-eval v2 implementation (review snapshot + docs) - https://github.com/Cbkaplinger/MLB-Props/pull/3 |
| CI | run `38759070843`, PASS (completed/success), head SHA `972fc554...` - https://github.com/Cbkaplinger/MLB-Props/actions/runs/38759070843 |

Verified via `git ls-remote origin research/market-eval-v2` (matches local HEAD of the
market-eval-v2 worktree) and `gh pr view 3` / `gh run view 38759070843`.

## 2. Frozen batch config

- File: `research/offseason_2026/specs/count-eval-v2-spec/harness/freeze_recency_batch_v1.json`
- Config sha256: `4b11e4b71cec3ab6c68235ea8966cf0f3f02f9a81cfc7d7bd209c6236c1af810`
  (definition, from the file itself: sha256 over
  `json.dumps(config, sort_keys=True, separators=(',',':')).encode('utf-8')` of the `config`
  object - NOT the file bytes)
- Status: `FROZEN - NOT EXECUTED`. Execution requires owner authorization (spec section 8).
- Batch: `recency-batch-v1` (run_label); scope: DEVELOPMENT-ONLY EW-recency ablation on three
  dev folds. No confirm claim, no adoption claim, no production promotion; 2026 rows CLOSED.

### 2.1 Candidates (4, fixed order)

| Order | Candidate | Role | Fitted features |
| --- | --- | --- | --- |
| 1 | `P1_B_logreg` | REFERENCE | 6 frozen B features (no EW column) |
| 2 | `P1_H3_pitcher_ew_only` | TREATMENT 1 | 6 B + `ew_pitcher` |
| 3 | `P1_H3_batter_ew_only` | TREATMENT 2 | 6 B + `ew_batter` |
| 4 | `P1_H3_incumbent_refit` | INCUMBENT-PROCEDURE REFIT | 8 H3 features (both EW columns) |

All four share one logistic spec: `LogisticRegression(C=1.0, max_iter=1000)`, StandardScaler fit
on base_train ONLY (one scaler per fold), block sigmoid calibration (1-D unpenalized logistic of
y on logit(p)) fit on the 60 PA-bearing calendar days per fold, derived at runtime
(cal_last = max game_date <= train_end; cal_first = cal_last - 59 days).
`P1_H3_incumbent_refit` is NOT proven prediction-equivalent to historical incumbent outputs
(pred_H3_raw) - it re-executes the frozen H3 fitting procedure on the registered folds.

### 2.2 Folds

- Dev folds scored: `block_2024H1`, `block_2024H2`, `block_2025H1`
  (train_end 2023-12-31 / 2024-06-30 / 2024-12-31 respectively).
- `confirm_2025H2`: EXCLUDED - NOT SCORED. Exclusion control:
  `RunConfig.include_confirm=False`, implemented in `comparison.py` and synthetic-proven by
  `test_confirm_exclusion_control_proves_no_confirm_rows_in_fits_or_bootstrap` (proves no
  confirm_2025H2 row reaches any fit, calibration sub-block, or bootstrap; the harness also
  fails loud at runtime if confirm rows leak with include_confirm=False).

### 2.3 Evaluation contract

- Seed: `20261001`. Bootstrap: paired slate-date bootstrap, block-stratified, row-weighted
  num/den ratio; `n_boot = 2000`; ONE draw stream shared across candidates; pooled dev = the
  3 dev folds ONLY.
- Primary metric: Brier. Secondary: log_loss.
- Lanes: RAW is the PRINCIPAL lane (all intervals, contrasts, family claims computed on
  pred_raw). CAL reported SEPARATELY as derived point estimates (no CIs, no contrast claims);
  never merged with RAW.
- Shared populations: per-fold eval identity hash (sha256 over sorted
  (game_pk, at_bat_number, batter)) asserted identical for every candidate.

### 2.4 Contrasts and multiplicity

4 predeclared contrasts (the only registered comparisons):

| ID | Contrast |
| --- | --- |
| `C1_pitcher_ew_vs_B` | P1_H3_pitcher_ew_only minus P1_B_logreg |
| `C2_batter_ew_vs_B` | P1_H3_batter_ew_only minus P1_B_logreg |
| `C3_both_vs_pitcher_only` | P1_H3_incumbent_refit minus P1_H3_pitcher_ew_only |
| `C4_both_vs_batter_only` | P1_H3_incumbent_refit minus P1_H3_batter_ew_only |

Holm family note: report each contrast's ORDINARY (unadjusted) 95% percentile interval AND the
Holm-adjusted family result SEPARATELY. Any family-level claim across the 4 contrasts must come
from the Holm-adjusted result, never from the ordinary intervals.

### 2.5 No-search constraints

- `ew_half_life_days = 90`, FIXED. NO half-life search permitted (no sweep, no tuning, no
  sensitivity lane). Inherited from the incumbent feature build (features_v3); not refit here.
- No hyperparameter search, no feature-set search beyond the 4 registered candidates.
- Prior weight w = 150, also inherited and frozen.

## 3. Input hashes (recomputed 2026-10-15 from the actual files)

| Input | Path (absolute) | sha256 |
| --- | --- | --- |
| PA table | `C:\Users\ckaplinger\MLB-Props-Research\p1-harness-v2\data\pa_table.parquet` | `e30d8561d8d0fbb9ab0eae562076312a29eeb1476172d533c3d93570959a85f0` |
| Features | `C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\features_v3.parquet` | `163ad43356e66649274682a473a4015c71f04be6c2f074f15e417c3d49b7e8f8` |
| Predictor payload (lineage) | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v1\data\predictor_payload.parquet` | `19511a492767ca061f216bf0a1679e94a77706b2737aea4cf1ab93c312b58a96` |

Notes:
- These are identical canonical inputs to first-run packet v1 (config sha256 `e59da946...5fc1`).
- `features_v3.parquet` (overnight-p2\data) is the canonical features frame and carries the
  EW-90d columns (`ew_pitcher`, `ew_batter`).
- The predictor payload is lineage-only for this batch (frozen per-start H3-raw/LOG5-raw K PMFs
  + BF PMFs, 7,194 starts x 155 cols, frozen pre-label-join); it is NOT a batch input.
- Predecessor lineage refs (from REVIEW_SNAPSHOT.md / FINDINGS_F1_F5): `player_id_map`
  `8a463f5c34281afd`, bundle refs `2b73bc4096b34641`, `325abdf01f5f0b84`.

## 4. Literal execution command (verbatim from the frozen config)

Working directory: market-eval-v2 worktree root. Command is registered in
`freeze_recency_batch_v1.json` under `config.execution.command` and matches the registered
runner (`comparison.RunConfig` / `run_comparison`):

```
python -c "import json,sys; d='research/offseason_2026/specs/count-eval-v2-spec/harness'; sys.path.insert(0,d); from comparison import RunConfig, run_comparison; p=json.load(open(d+'/freeze_recency_batch_v1.json',encoding='utf-8')); c=p['config']; print(run_comparison(RunConfig(pa_table_path=c['inputs']['pa_table_path'],features_path=c['inputs']['features_path'],candidates=c['candidate_order'],include_confirm=False,output_root=c['output_destination'],run_label=p['batch_id'])))"
```

Key bindings baked into the command: seed 20261001 and n_boot 2000 come from the config's
`evaluation` block (read by the harness at runtime, not passed here); `include_confirm=False`
is explicit in the command itself; `run_label='recency-batch-v1'`; `output_root` =
the output destination in section 5.

DO NOT edit this command. It is part of the frozen config; owner authorization is required
before running it (spec section 8: synthetic tests green + frozen config hash + owner
authorization; nothing in this batch authorizes a run).

## 5. Output destination (write-once)

- `C:\Users\ckaplinger\MLB-Props-Research\recency-batch-v1`
- Confirmed nonexistent at registration (2026-10-15) and re-verified 2026-10-15 by the pack
  author.
- Write-once: `run_comparison` refuses to overwrite an existing output dir
  (`WriteOnceError`, comparison.py). The harness creates
  `<output_destination>\<64-hex harness run_id>\` and records `recency-batch-v1` as run_label.
- If the dir exists at execution time, STOP - do not delete it; escalate to the owner.

## 6. How to re-verify every hash (copy-paste)

From the market-eval-v2 worktree root:

```
python -c "import json,hashlib; p='research/offseason_2026/specs/count-eval-v2-spec/harness/freeze_recency_batch_v1.json'; d=json.load(open(p,encoding='utf-8')); c=json.dumps(d['config'],sort_keys=True,separators=(',',':')).encode('utf-8'); print(hashlib.sha256(c).hexdigest()); print(d['config_sha256'])"
```

```
python -c "import hashlib; [print(hashlib.sha256(open(f,'rb').read()).hexdigest()) for f in [r'C:\Users\ckaplinger\MLB-Props-Research\p1-harness-v2\data\pa_table.parquet', r'C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\features_v3.parquet', r'C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v1\data\predictor_payload.parquet']]"
```

Remote/PR/CI claims: `git ls-remote origin research/market-eval-v2`,
`gh pr view 3 --json isDraft,headRefOid`, `gh run view 38759070843 --json conclusion,headSha`.

## 7. Review priorities for Chat 2

1. **Config/input hash verification** - recompute the config sha256 (section 6, first command;
   remember the hash is over the sorted-JSON `config` object, not the file bytes) and the three
   input parquet hashes (section 6, second command). All must match section 2/3 before any
   further review work is trusted.
2. **Confirm-exclusion guard** - confirm `RunConfig.include_confirm=False` is present in the
   frozen command AND backed by
   `test_confirm_exclusion_control_proves_no_confirm_rows_in_fits_or_bootstrap`
   (harness/test_comparison.py); confirm `run_comparison` fails loud if confirm rows leak
   (comparison.py leak check) and that `confirm_2025H2` is registered EXCLUDED in the config.
3. **Contrast definitions** - verify the 4 predeclared contrasts (C1-C4, section 2.4) match the
   config's `contrasts_predeclared` exactly and that the Holm family rule (ordinary intervals
   and Holm-adjusted result reported SEPARATELY) is stated in the config's
   `multiplicity_rule`.
4. **F-4 opt-in gate** - owner authorization per spec section 8 is required before execution;
   the batch is `FROZEN - NOT EXECUTED` and nothing in it authorizes a run. Reviewers must not
   "helpfully" run it.
5. **Batch isolation (no 2025H2 scoring)** - the pooled population is the 3 dev folds ONLY;
   `confirm_2025H2` must never be fitted, scored, or bootstrapped in this batch, and no output
   may claim confirmation. Any artifact showing 2025H2 scores under `recency-batch-v1` is a
   violation.
