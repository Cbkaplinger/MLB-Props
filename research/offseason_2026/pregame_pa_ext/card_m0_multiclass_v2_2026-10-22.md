# PRE-REGISTRATION CARD v2 — M0: four-class PA outcome model
# (pregame-pa-ext-v2 lane, 2026-10-22)
#
# STATUS: PROPOSED DESIGN — implementation in progress (taxonomy + model
# code on PR #34), NOT EXECUTED, NO REAL OUTCOMES READ. Real-data
# execution requires the §11 execution contract plus explicit owner
# authorization.
#
# SUPERSEDES: card_m0_multiclass_2026-10-21.md (v1). V1 is preserved as
# historical STOPPED evidence: its five-class taxonomy included a class
# with 0 training PAs in every block (class 4: baserunner events) and
# left six completed-PA event strings unmapped. V1 §2's taxonomy table,
# §7's rare-class examples, and §13's evidence table are all superseded
# by this card. V1's scientific sections (§1, §3-§6b, §8-§10) remain
# in force unchanged and are restated here by reference, not modified.

## 1. Scope

Same motivation as v1 §1: test whether a four-class PA outcome model
improves the count distribution through better per-PA probability
structure without sacrificing the K marginal. No new model family, no
new features, no workload simulation, no betting-layer changes.

## 2. Outcome taxonomy (v2, EXHAUSTIVE)

Four classes. Every completed-PA Statcast event string observed in the
frozen data maps to exactly one class; 0 rows are excluded. The mapping
below is exhaustive over `m0_multiclass.STATCAST_EVENT_TAXONOMY`
(22 event strings) and matches the raw Statcast `events` strings as
recorded in the 2022-2025 regular-season files.

| class | name | Statcast events (exact strings) |
| --- | --- | --- |
| 0 | strikeout | `strikeout`, `strikeout_double_play` |
| 1 | walk_hbp_interference | `walk`, `intent_walk`, `hit_by_pitch`, `catcher_interf` |
| 2 | in_play_out | `field_out`, `force_out`, `grounded_into_double_play`, `double_play`, `field_error`, `fielders_choice`, `fielders_choice_out`, `sac_bunt`, `sac_fly`, `sac_fly_double_play`, `triple_play` |
| 3 | hit | `single`, `double`, `triple`, `home_run`, `ground_rule_double` |

Non-completed-PA event strings (`caught_stealing`, `pickoff_*`,
`wild_pitch`, `passed_ball`, etc.) map to -1 and are excluded, but none
occur in the pa_table-joined population (see §5), so 0 rows are
excluded in practice.

CHANGES FROM v1 §2 (the v1 STOP condition trigger):
- Class 4 (`caught_stealing_or_pickoff`) REMOVED: it is a baserunner
  event, not a completed-PA outcome, and had 0 training PAs in every
  block in the frozen data.
- Six completed-PA event strings ADDED that v1's table omitted:
  `grounded_into_double_play`, `sac_fly`, `intent_walk`, `sac_bunt`,
  `double_play`, `sac_fly_double_play`. V1's mapping left these
  unmapped (class -1), incorrectly excluding 23,531 completed PAs.
- Class names corrected to match the mapping (v1/v2 mapping was always
  class 2 = in-play out, class 3 = hit; the v1-interim CLASS_NAMES
  list had the last two names swapped; fixed 2026-10-22).

## 3. Features, model family, blocks, endpoints (UNCHANGED from v1)

All scientific choices are unchanged from v1 and are binding:
- Features (v1 §3): the frozen FEAT_H3 eight, same as-of construction,
  same strictly-prior cutoff. No new features.
- Model family (v1 §4): StandardScaler + multinomial LogisticRegression
  (C=1.0, max_iter=1000), softmax output; per-class sigmoid calibration
  on the calibration sub-block per the frozen recipe's CAL convention.
- Fit/evaluation blocks (v1 §5): per dev block (block_2024H2,
  block_2025H1), train = realized PA rows 2023-01-01..block cal_first,
  cal = last 60 days before train_end. confirm_2025H2 is PROTECTED:
  it never enters training, calibration, or evaluation. The evaluation
  population is the preserved ledger's 4,823 eligible dev starts
  (43,407 slots; 82,817 pitcher-matched evaluation PAs), identical key
  sets to the frozen diagnostics.
- Endpoint 1 (v1 §6): K-marginal non-inferiority, paired log-loss
  delta, margin +0.005, slate-date bootstrap n=2000 seed 20261001;
  PASS iff the 95% CI upper bound < +0.005. The K probability is
  P(class 0), the same target as the frozen binary model.
- Endpoint 2 (v1 §6): multiclass log loss must beat BOTH the
  league-constant baseline and the log5 baseline.
- Count-RPS through the registered aggregation: DESCRIPTIVE only
  (never gated, never cited as primary).
- Holm m=2 (v1 §6): step-down at family level 0.05 across the two
  pre-declared contrasts.
- Effect-size budget (v1 §6b): margin/MDE ratio > 5; MDE ~0.00046 at
  80% power on 82,817 paired PAs.
- Provenance (v1 §9): receipt_initial.json written FIRST, receipt
  chaining by sha256, write-once outputs, no in-place repair.
- Stop conditions (v1 §8): K-marginal non-inferiority failure STOPs;
  any class with 0 training PAs STOPs (taxonomy too granular); both
  endpoints passing yields a development-only diagnostic, no promotion
  without a separate gate.

## 4. Required outputs (at execution)

- receipt_initial.json (written before any fit): checkpoint pin, input
  classification (consumed vs context), taxonomy table with per-class
  names, dev-block identities, seed, code SHA.
- receipt_final.json (chained): per-class per-block training counts,
  calibration table, both endpoint statistics with bootstrap CIs,
  Holm-adjusted decisions, descriptive count-RPS, |DP| bins, per-line
  probability summaries.
- Per-class calibration curves (synthetic-verified machinery).
- Disclosure note in the receipt (NOT in public cards) that
  confirm_2025H2 label counts were inspected for this taxonomy
  correction; the block remains excluded from all fitting and
  evaluation.

## 5. Populations and count reconciliation (v2, replaces v1 §13)

Windows are consistent and PA identity is the unique key
(game_pk, at_bat_number, batter), deduplicated. Available-source
partitions below are UPPER BOUNDS on fitting rows, not fitting
populations: actual fitting rows per dev block are the frozen recipe's
realized-PA lineage subset (2023-01-01..block cal_first), which is
never larger than the available rows shown.

### Per-class available-source rows (corrected four-class taxonomy)

| window | total PAs | class 0 (K) | class 1 (walk/HBP/CI) | class 2 (in-play out) | class 3 (hit) | excluded |
| --- | --- | --- | --- | --- | --- | --- |
| 2022-04-07..2024-12-31 (cumulative training window for block_2024H2) | 548,421 | 123,822 | 52,019 | 252,289 | 120,291 | **0** |
| 2025-01-01..2025-06-30 (block_2025H1 dev rows) | 95,357 | 20,914 | 9,180 | 44,369 | 20,894 | **0** |

The confirm_2025H2 row is deliberately omitted from this table (protected
block; see §4's disclosure note). Every one of the 731,347 pa_table rows
maps to classes 0-3 under the corrected taxonomy; 0 rows are excluded.
All four classes have large training counts in both dev blocks; the
v1 STOP condition (a class with 0 training PAs) no longer triggers.

### Reconciliation: 22,326 vs 23,531 excluded PAs (v1 defect accounting)

The 23,531 figure is REPRODUCIBLE from the frozen data and is the
authoritative v1 exclusion count. It is the number of pa_table-joined
completed PAs whose Statcast event string was absent from v1's
five-class mapping, over the full window 2022-04-07..2025-09-28:

| omitted event string | rows | became (v2) |
| --- | --- | --- |
| grounded_into_double_play | 13,168 | class 2 |
| sac_fly | 4,943 | class 2 |
| intent_walk | 2,014 | class 1 |
| sac_bunt | 1,831 | class 2 |
| double_play | 1,501 | class 2 |
| sac_fly_double_play | 74 | class 2 |
| total | **23,531** | |

The same six strings sum to 23,531 under every accounting variant
checked (raw rows without dedup; deduplicated PA keys without the
pa_table join; pa_table-joined), and the v1-interim per-block excluded
counts (17,619 + 3,133 + 2,779) also sum to 23,531.

The earlier 22,326 figure could NOT be reproduced from the frozen data
under any window or deduplication variant tried (full window, dev
window 2024-07-01..2025-06-30 = 5,883, calendar 2024 = 5,775,
<= 2025-06-30 = 20,752). It came from an earlier diagnostic pass and
is superseded by 23,531. No result in the accepted record depends on
either figure: both counted rows that were EXCLUDED (never fitted), so
the corrected taxonomy only ever ADDS rows to training.

### Correction of the v1 §13 class -1 note

V1 §13 described class -1 rows as "non-PA-terminal events (wild_pitch,
passed_ball, etc.) ... not in the pa_table's PA-level grain." That was
WRONG. The class -1 rows were completed plate appearances (the six
event strings above) that v1's mapping simply omitted. Under the v2
taxonomy there are no class -1 rows in the pa_table-joined population.

## 6. Implementation status (2026-10-22, non-author check)

- Taxonomy, model, receipts, CLI: implemented on PR #34
  (`m0_multiclass.py`); taxonomy tests green at the corrected
  four-class mapping, including regression assertions that the six
  v1-omitted event strings map to their classes and that CLASS_NAMES
  agree with the mapping.
- Synthetic runner tests: REPAIRED (Chat 2's ec8bd42; runner tests pass
  explicit synthetic `event_labels` from the shared factory
  `m0_synthetic.synthetic_m0_inputs`, which generates only classes
  0-3). Non-author check 2026-10-22: the 9-file affected suite runs
  101 passed / 0 failed / 0 skipped at ec8bd42, with a tripwire guard
  proving the synthetic runner never reads real Statcast and the label
  loader fails closed on a missing raw directory.
- Real-data execution: NOT AUTHORIZED, NOT PERFORMED.

## 7. Confirmation-block access disclosure (2026-10-22)

During the v1-to-v2 taxonomy correction, the confirm_2025H2 realized
outcomes and label counts were INSPECTED once (read-only) to verify
that the corrected four-class taxonomy maps every row and that no
per-class count is zero. This access was diagnostics-only: no
confirm-block row entered training, calibration, evaluation, or any
model artifact, and the block's 87,569 rows remain excluded from all
fitting populations. The inspection informed only the taxonomy
granularity decision (whether the v1 STOP condition still triggers
under v2). The card's training-count table (section 5) deliberately
omits the confirm_2025H2 row; the per-class counts from that
inspection are recorded in the execution receipt's disclosure note,
not in this public card. No further confirm-block access is planned
before the gated confirmation run.
