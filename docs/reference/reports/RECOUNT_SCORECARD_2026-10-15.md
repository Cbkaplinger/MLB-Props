# RECOUNT Scorecard - count-lane B0/B1 vs market benchmark (2026-10-15)

Compact single-file record of the count-lane (per-start strikeout distribution) scoring
results, assembled read-only from existing artifacts in the research lake. Nothing here is
a new run; every number cites its artifact.

## Provenance (artifacts read, no lane crossed)

| Artifact | Path (lake root = `C:\Users\ckaplinger\MLB-Props-Research\`) | Role |
| --- | --- | --- |
| bf-workload-v1 | `bf-workload-v1\report_v2.json`, `data\start_metrics_v2.parquet` | BF PMF + milestone correction source; count-layer H3/LOG5 arms |
| pregame-state-v1 | `pregame-state-v1\report_v3.json`, `data\start_metrics_v3.parquet` | Pregame state inputs feeding the BF lane |
| market-eval-v1 score_v2 | `market-eval-v1\outputs\score_v2\score_summary.json`, `skill_metrics.json` | Market-lane benchmark (matched contracts) + persisted count-layer reuse |
| count-eval-v1 | `count-eval-v1\SPEC.md`, `bf-2026-eval-v1-outputs\report.json` | Count-lane freeze (`count-eval-v1`) that pins the B0/B1 integration |
| B1 ridge run | `bf-lane-v1\b1_run_v1\metrics.json`, `run_manifest.json` | B0/B1 per-row forecasts, aggregates, bootstrap (accepted with limitation, Chat 2 reconciliation `bf-lane-v1\B1_RECONCILIATION_CHAT2.md`) |
| count B1 recovery run | `bf-2026-eval-v1-outputs\count_b1_recovery_v1\`, receipt `..\execution_receipt_count_b1_recovery_v1.json` | Count-lane paired B0-vs-B1 re-execution. **Status caveat: FAILED_AT_FINALIZE (inventory nonconformance, write-once consumed); numbers citable only with this failure status (receipt `results.status_caveat`).** |

## Count target definition

- Target: **K = pitcher strikeouts in a single start** (game-level count, per start).
- Grain: one row per pitcher-start; paired arms score the identical row.
- Outcome on the count scale is realized strikeouts (`realized_k`), never the BF or PA lane.

## Support / buckets

- Frozen convention: **24 categories, K = 0..22 exact + absorbing K >= 23**
  (`k_max = 24`; last bucket absorbs the tail). Source: `research/offseason_2026/kcount_combiner.py`
  (combine_count), `eval_package.py` ("support": "K=0..22 exact + absorbing >=23 (24 categories)"),
  pinned in the count-eval-v1 freeze and `count_b1_recovery_v1\metrics.json` config.

## Log convention

- All log scores are **natural log** (negative log likelihood, summed per row then averaged
  by the runner's convention; lower is better). Same convention in the PA-lane harness.

## Threshold meanings

| Threshold | Meaning |
| --- | --- |
| K >= 6 | P(start reaches 6 strikeouts) - quality-start marker |
| K >= 8 | P(reaches 8) - strong-start marker |
| K >= 10 | P(reaches 10) - elite-start marker |
| K >= 12 | P(reaches 12) - rare, near-max marker |

Milestone Briers at these thresholds are descriptive only; the single predeclared
registered test is the paired count-RPS contrast C_b1_ridge_vs_b0_empirical.

## Threshold event rates (realized, dev population, n = 4,866)

Computed from `count_b1_recovery_v1\count_b1_per_row_scores.parquet` (`realized_k` column):

| Threshold | Pooled | block_2024H2 (n=2,334) | block_2025H1 (n=2,532) |
| --- | --- | --- | --- |
| K >= 6 | 0.3693 | 0.3800 | 0.3594 |
| K >= 8 | 0.1457 | 0.1500 | 0.1418 |
| K >= 10 | 0.0378 | 0.0364 | 0.0391 |
| K >= 12 | 0.0076 | 0.0060 | 0.0091 |

## B0 vs B1 count-lane scores (dev population, n = 4,866)

From `b1_run_v1\metrics.json` aggregate (reconciled bit-for-bit by Chat 2, max dev 4.44e-16)
and confirmed by the recovery run `count_b1_aggregates.json`:

| Score | B0 (empirical PMF + shrunk league-rate p_bar) | B1 (Ridge-recentered PMF) | delta (B1-B0) |
| --- | --- | --- | --- |
| count-RPS (summed) | 1.3303025482 | 1.3021239827 | **-0.0281785654** |
| count-log score (nat log) | 2.2810254005 | 2.2565295116 | -0.0244958888 |
| Brier ge6 | 0.2140738641 | 0.2118782986 | -0.0021955654 |
| Brier ge8 | 0.1160247936 | 0.1167033373 | +0.0006785438 |
| Brier ge10 | 0.0356908781 | 0.0364084543 | +0.0007175761 |
| Brier ge12 | 0.0075954082 | 0.0078031220 | +0.0002077138 |

Per-fold: block_2024H2 delta RPS -0.0429399 (B0 1.3419200 -> B1 1.2989801);
block_2025H1 -0.0145715 (B0 1.3195935 -> B1 1.3050220). Registered uncertainty: block-stratified
slate-date bootstrap (2,000 reps, seed 20261001), null-centered p = 0.0005 (bootstrap floor),
95% CI [-0.0366, -0.0198]. ge6 Brier improves, small ge8/10/12 degradations are descriptive only.

## Prior-data baseline scores - what exists and what does NOT

- **No count-lane league-rate/historical-rate predictor score exists** in any cited artifact.
  The count-lane reference IS B0: the empirical BF PMF (own distribution if prior_n >= 10, else
  league pool) combined with the shrunk league K-rate `p_bar` (w=150, log5 form). There is no
  separate "league-rate predictor" arm scored on the count lane to quote.
- The pooled dev log loss **0.520552 is a PA-lane metric** (P0_log5 arm, 277,623 PA rows,
  `first-run-v1\...\metrics.md` in the lake). It scores per-PA strikeout probability on a
  different target, population, and unit. It is **not** comparable to count-lane log scores
  (~2.26) and must not be placed in the same table.

## Baseline clarification: 0.693 is NOT the count baseline

- A binary 50/50 event has log loss -ln(0.5) = **0.6931**. The count lane is a 24-category
  distribution, not a binary event, so 0.693 is not its reference point.
- The uniform 24-category baseline is -ln(24) = **3.1781**; it is also weak (B0/B1 log scores
  of ~2.26-2.28 already beat it by a wide margin). Neither 0.693 nor 3.178 is a meaningful
  target for the count lane; B0 (the empirical prior-data PMF) is the reference arm.

## Dev vs confirmation separation

- **Count lane (B0/B1):** dev-only. Scored rows are block_2024H2 + block_2025H1 (n = 4,866);
  `confirm_2025H2` (2,328 rows) is excluded and NOT scored; 2026 is CLOSED
  (`count_b1_recovery_v1\metrics.json` config folds; receipt row accounting).
- **Count layer H3/LOG5 arms** (persisted reuse in score_v2, sourced from bf-workload-v1):
  dev (n=4,471 starts): H3 RPS 1.2874495 / log 2.2526952; LOG5 1.2913613 / 2.2557673.
  confirm_2025H2 (n=2,172 starts): H3 1.2610379 / 2.2343027; LOG5 1.2700346 / 2.2387890.
  Dev and confirm are reported separately; no pooled dev+confirm headline.
- **Market lane (score_v2):** dev headline is dev-only; confirm reported separately
  (see below). Population rule pinned by skill_metrics.json.

## Market-lane benchmark (matched contracts, dev population)

From `market-eval-v1\outputs\score_v2\skill_metrics.json` (multi-class Brier at matched
contracts, classes {win, push, lose}; identical contract set across arms; dev = block_2024H2 +
block_2025H1, 25,978 contract-side rows):

| Arm | Dev Brier | Dev log loss (non-push) |
| --- | --- | --- |
| **De-vig market** | **0.446854** | 0.637793 |
| H3 | 0.468393 | 0.662082 |
| LOG5 | 0.466334 | 0.659790 |

The de-vig market Brier 0.4469 beats H3 0.4684 (skill -0.0215) and LOG5 0.4663 (skill -0.0195)
on matched contracts. Confirm population (14,030 rows): market 0.439679 vs H3 0.456890 /
LOG5 0.457369 - same ordering, reported separately from dev. This is the market-lane benchmark;
the market lane and the count lane measure different contracts and are never pooled.

## Status notes

- The count-B1 recovery run is analytically complete and MLflow-verified but formally
  FAILED_AT_FINALIZE (pooled aggregate filenames missed the declared 22-file inventory;
  write-once destination consumed; no rerun). Any conforming rerun needs a NEW registration
  (receipt `failure.disposition`, `no_rerun_statement`).
- b1_run_v1 verdict: ACCEPT WITH LIMITATION (D1 descriptive-only CI bug, L2/L3 documentation;
  no registered number affected - `bf-lane-v1\B1_RECONCILIATION_CHAT2.md`).
- This scorecard is docs-only; it changes no code, policy, or live path.
