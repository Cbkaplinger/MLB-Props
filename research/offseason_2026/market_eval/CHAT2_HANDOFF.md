# Chat 2 Review Handoff — market-eval-v1 score_v2

Status: **PRELIMINARY — pending integrity review.** Numbers below are the executed
run's outputs, serialized 2026-10-14. No rerun, no new analysis was performed to
produce this handoff. All canonical outputs and logs are preserved unchanged.

- Output dir (write-once): `C:\Users\ckaplinger\MLB-Props-Research\market-eval-v1\outputs\score_v2\`
- Execution log: `C:\Users\ckaplinger\MLB-Props-Research\market-eval-v1\outputs\score_v2_execution_log_2026-10-14.txt`
- Spec: market-eval-v1 score (EXPERIMENT_CARD.md corrections C2/C3; F-6 population separation)
- `report.json` is NOT present in the output dir; the actual files are listed below.

## 1. Output files and sha256

Full sha256 of every file in the output dir, plus the execution log:

| File | Bytes | sha256 |
| --- | ---: | --- |
| bets_ledger.parquet | 488,965 | `be02861afafc526e7184ac13f4825ec613c06a92209818e44f6f7c465e973b80` |
| bootstrap.json | 2,579 | `d237037bb263dbc3149013408fb7d026eb70622fb51241aa8c4c1819ec220e65` |
| clv_table.parquet | 184,576 | `78e7d8c1f3a50a54179b63f79f9461089d7345fcf5151208ad2dc1fe6a9f6559` |
| confirm_metrics.json | 1,564 | `8f052c192572e9819dabce62c1067dc6257c1aeea4e8d57ea6d1b8851993c982` |
| score_manifest.json | 376 | `bc9ed9e31750f6e6ac6ad5ec7f0ed35a24b30f8098a23106c449a2d1bb0a2bd2` |
| score_summary.json | 2,869 | `deec1c21f61a3f9827c799dccda9ecf3e234f779cd7e96623520f18a5c8c6214` |
| skill_metrics.json | 8,709 | `08c99f3997eacbbde989fbcb5e703b53a1709e9146f0ad5bf92d4b387061cba6` |
| ..\score_v2_execution_log_2026-10-14.txt | 5,826 | `7c61ff31644e203adec9c90e08675187e83d8fc89786a320a24ea3817060ed16` |

The 16-char digests inside `score_manifest.json` (`outputs_sha256_16`) match the
full hashes above for `bets_ledger.parquet` (`be02861afafc526e`) and
`clv_table.parquet` (`78e7d8c1f3a50a54`).

## 2. Executed scorer identity

| Item | Value |
| --- | --- |
| Executed file | `C:\Users\ckaplinger\MLB-Props-Research\market-eval-v1\market_eval.py` |
| Executed sha256 | `c2745980ada20c0942a811ac6e58245418a45cd8f7d83b265f17f54f834cd6c5` |
| Committed git blob | `99db556c676878aab5336989fbc7fccd9f4e31f5` |
| Source commit | `108d5ba9ca4075017c7590a6c90e967fe3b18707` (branch `research/market-eval-v2`; descendant of pinned review snapshot `02ce162f119208b762edf1fd690edd5e7ee9b8ea`) |
| Stale lake copy (replaced pre-run) | `457991d81d44f9541dcb6a2889f35979aa0d9d844cd1ab91d57e1aea5e20e929` |

The raw bytes of blob `99db556c...f4e31` hash to `c2745980...4c6c5`, and the
lake's `market_eval.py` on disk hashes to `c2745980...4c6c5` — the executed
scorer is byte-identical to the reviewed committed bytes.

## 3. Resolved command and input hashes

Run from `C:\Users\ckaplinger\MLB-Props-Research\market-eval-v1\`, command as
registered in EXPERIMENT_CARD.md (score section):

```
python market_eval.py --score --prep-dir outputs\prep_v2 --start-metrics "C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\data\start_metrics_v2.parquet" --score-dir outputs\score_v2 --seed 20261001 --n-boot 2000
```

Input hashes (full sha256; 16-char prefixes match `score_manifest.json`
`inputs_sha256_16` and the prep_v2 `manifest.json`):

| Input | sha256 |
| --- | --- |
| `outputs\prep_v2\matched_contracts.parquet` | `185abda9a238dd9742f76cb9c88a0e3c4b656696ab82da3a8312b405d5def183` |
| `outputs\prep_v2\paper_bets.parquet` | `6e310c49bc238795a9f7a6293b6d4fc6ed68d72cadf9b422fbf93e742ed7b9cf` |
| `..\..\bf-workload-v1\data\start_metrics_v2.parquet` | `af6814ec7ea73b4ac941dd52f185139062b987762d639203b867e15bb4817fde` |
| `outputs\prep_v2\manifest.json` (prep inputs + registered constants) | `f89f5d9e72c2c15fd36e08752877bde25fe603a3500e75186e3793147f93c2ce` |
| `outputs\prep_v2\prep_summary.json` | `5da72b55121d55de8ed69a7faa7c047cef8a69b0d6f62df55d4b404d91b935b6` |

## 4. Population and tier counts

Matched contracts (side rows; complementary over/under sides share one
realization and are not independent):

| Population | Side rows | Slate dates | Tier A_verified_clock | Tier B_clock_proxy |
| --- | ---: | ---: | ---: | ---: |
| dev (block_2024H2 + block_2025H1) | 25,978 | 184 | 14,014 | 11,964 |
| confirm (confirm_2025H2) | 14,030 | 86 | 14,030 | 0 |
| Total | 40,008 | 270 | — | — |

Effective counts (whole run): 40,008 contract side rows / 20,004 distinct
start-line pairs / 6,643 distinct starts / 270 slate dates / 0 push rows.
Reconciliation: dev rows + confirm rows = contract side rows (no silent row
loss; pinned by the F-6 regression).

Paper bets:

| Population | Bets | Wins | Losses | ROI/bet |
| --- | ---: | ---: | ---: | ---: |
| dev | 7,856 | 3,440 | 4,416 | -7.07% |
| confirm | 3,579 | 1,470 | 2,109 | -9.80% |
| Total | 11,435 | 4,910 | 6,525 | -7.93% |

7,856 + 3,579 = 11,435 (dev + confirm = total; reconciled in
`score_summary.json`). 473 bets have no closing reference.

## 5. Registered metric conventions

All conventions are as registered in
`research/offseason_2026/market_eval/EXPERIMENT_CARD.md` and
`research/offseason_2026/market_eval/METRIC_SCHEMA.md` in the repo worktree
`C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\main-active`
(pinned snapshot commit `02ce162f`; population-assignment amendment in
`108d5ba9ca4075017c7590a6c90e967fe3b18707`).

- **Primary metric — multi-class 3-way Brier at matched contracts.** One
  observation per (start, line) side row; classes {win, push, lose};
  `Brier = mean over rows of sum_c (p_c - y_c)^2`. Identical matched contracts
  across H3-raw / LOG5-raw / de-vig market.
- **De-vig (registered).** Proportional no-vig method from the PAIRED
  contemporaneous same-book same-snapshot over/under (prep_v2
  `manifest.json` `registered_constants.devig`; card C2/C3).
- **Log loss (secondary).** Binary log loss on non-push rows only (1e-12
  floor), same matched contracts. This cohort has 0 push rows, so push
  semantics were unexercised (disclosed).
- **CLV definition.** `clv_pct = (d_bet - d_close)/d_close` — decimal odds,
  percent scale — vs the bet book's OWN closing side price. Bets without a
  closing ref (473) keep their ledger row and count in ROI, but are excluded
  from CLV stats only, with the count disclosed.
- **Bootstrap.** Paired slate-date bootstrap: unit = game_date (slate),
  2000 resamples, seed 20261001, identical resample indices across all
  competitors, 95% percentile intervals. Dev pooled draws = block_2024H2 +
  block_2025H1 only; confirm_2025H2 rows never enter dev pooled points or
  bootstrap draws (card C3.3/C3.7); confirmation reported separately.
  ROI uses the same slate-date unit (ratio estimator; separate draw stream,
  same seed family, documented).

## 6. Headline result (PRELIMINARY — pending integrity review)

**The de-vig market beats both H3-raw and LOG5-raw on 3-way Brier in both
populations. The dev H3-vs-LOG5 ordering is NOT replicated in confirm. Paper
ROI is negative in both populations.**

Dev (block_2024H2 + block_2025H1; 25,978 rows, 184 dates):

| Competitor | 3-way Brier | 95% CI |
| --- | ---: | --- |
| H3-raw | 0.46839 | [0.46207, 0.47475] |
| LOG5-raw | 0.46633 | [0.46039, 0.47210] |
| Market (de-vig) | 0.44685 | [0.44267, 0.45139] |

- h3_minus_market: +0.02154, CI [+0.01713, +0.02607] — market better.
- l5_minus_market: +0.01948, CI [+0.01517, +0.02409] — market better.
- h3_minus_l5: +0.00206, CI [+0.00041, +0.00385] — H3 worse than LOG5 in dev.

Confirm (confirm_2025H2; 14,030 rows, 86 dates): H3 0.45689 CI
[0.44971, 0.46446]; LOG5 0.45737 CI [0.45003, 0.46508]; market 0.43968 CI
[0.43362, 0.44588]. Market beats both again. h3_minus_l5 = -0.000479,
CI [-0.002513, +0.001591] — crosses zero and flips sign vs dev: the dev
H3-vs-LOG5 ordering is **non-replicated**.

Paper ROI (slate-date bootstrap): dev -7.07% CI [-10.41%, -3.85%]; confirm
-9.80% CI [-15.86%, -3.36%]. Total -906.54 units over 11,435 bets, ROI/bet
-7.93%, win rate 42.94%. Negative in both populations; all CIs exclude zero.

Count-layer (start-level, persisted and reused): dev RPS H3 1.2874 vs LOG5
1.2914 (LOG5 better); confirm RPS H3 1.2610 vs LOG5 1.2700 (H3 better) —
consistent with the non-replicated H3/LOG5 ordering.

## 7. Deviations

1. **Stale lake scorer replaced pre-run.** The lake's `market_eval.py` was a
   stale copy (sha256 `457991d81d44f9541dcb6a2889f35979aa0d9d844cd1ab91d57e1aea5e20e929`,
   matching the pre-amendment pinned-snapshot bytes) and was replaced BEFORE
   the run with the reviewed committed bytes from commit
   `108d5ba9ca4075017c7590a6c90e967fe3b18707` (blob
   `99db556c676878aab5336989fbc7fccd9f4e31f5`, sha256
   `c2745980ada20c0942a811ac6e58245418a45cd8f7d83b265f17f54f834cd6c5`).
   Byte-identity between the executed file and the committed blob was verified
   for this handoff. No other deviations from the registered plan are known.

## 8. Preservation

All files in `outputs\score_v2\` and the execution log are canonical outputs of
the single executed run and were not modified by this handoff — the only file
written is this `CHAT2_HANDOFF.md`. Hashes in section 1 were taken from the
files as they stand after the run.
