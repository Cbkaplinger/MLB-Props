# Lineup prediction-path reconciliation — specification (2026-10-27)

Status: **SPECIFICATION PUBLISHED FOR CHAT 2 REVIEW — not executed, not
authorized.** This is a measurement-reconciliation candidate only. It is
NOT evidence that lineup quality is the dominant model bottleneck.

Frozen calibration branch `research/calibration-exec-gate-v1` at
`1321e4bf45ca1673985612b2994cbda4eca23f9f` (PR #48) is untouched by this
spec; calibration remains unexecuted and unauthorized.

## 1. What is established (valid evidence only)

**D3 demonstrated measurement defect (the failure being reconciled).**
The lineup/oracle diagnostic's control invariant FAILED: for the
batter-independent arm — whose probabilities should be identical across
the two construction routes — the maximum absolute PMF difference was
**0.1143** (required bound: 1e-12). The two conditions drew probabilities
from DIFFERENT feature-construction paths (ledger as-of slot states vs
pa_table-attached states), and the runner attached FULL scores to
PITCHER records positionally in list order rather than by key.
Consequence: **no valid lineup-effect estimate exists.** The diagnostic
is preserved as failure evidence.

**Aggregate motivation (valid).** The repaired market evaluation
(`market_eval_k_v3_fullkey_attempt2`; scored-cohort parquet
`1d9a00343d17956f`; receipts `d652e42a…` / `6f69286c41765bb0…`) shows the
closing line beats the frozen model on the 2025H1 true T-5 close cohort
(n=2,154): close 0.6890, model **+0.0234** paired over/under log loss
(positive = worse than close; decision `model_not_better_than_close`,
CI [+0.0236, +0.0373] recorded on the full repaired cohort). No valid
component estimate explains this gap.

**Metric-label reconciliation.** The previously circulated "+0.0227"
figure is RETIRED: it does not appear in the authoritative result table.
The authoritative paired delta (model − close) is **+0.0234 log loss**
(2025H1 true T-5 close, n=2,154; STATUS 5/6 of
`results_market_eval_k_v1/RESULT_RECORD.md`). The +0.0303 figure on the
n=4,336 combined cohort is itself retired from headline use (mixed
timing tiers). The metric is log loss, not count-RPS.

**What valid component evidence already shows (all null or negative).**

| challenger | result | status |
|---|---|---|
| Exact heterogeneous aggregation (Question A) | count-RPS delta (challenger − baseline) **−0.000333**, CI entirely negative | valid; tiny |
| FULL vs PITCHER features, count layer | FULL-frozen **−0.00017** CI [−0.00037, +0.0000282] — includes zero | valid (canonical `ablation_count_rps_canonical_v2_recovered2/`) |
| FULL vs PITCHER features, PA layer | multiclass LL 1.22305 vs 1.23192 on all 82,817 eval PAs | valid; PA-level gain does not transmit to the count layer |
| C-B1 exposure-band sequence | **+0.0859** count-RPS (LOST) | valid rejection of that specific challenger |
| Batter-recency | rejected on paired per-PA log loss | valid |

None of these is a lineup estimate; none explains the aggregate gap.

**Invalid oracle-effect magnitudes are NOT a prioritization argument.**
The stopped diagnostic's oracle-condition count-RPS levels
(`rps_full_oracle`, `rps_pitcher_oracle`, and the derived contrasts) are
contaminated by the demonstrated defects: outcome-selected cohort,
cross-path probability divergence, positional assignment, and
drop-counter double-counting (4,823 − 284 ≠ 4,681). They are excluded
from this specification's motivation and from any forward planning.

## 2. What "oracle lineup" actually contains

Per the impact ledger (verified-facts table): the oracle condition
conditions each projected slot on the game's **realized plate
appearances**. Specifically it:

1. requires ≥9 distinct batters actually faced (an outcome-selected
   subpopulation — availability is determined by what happened);
2. uses **first-nine-DISTINCT-batter appearance order**, not the
   official lineup, whenever substitutions precede a first appearance;
3. builds each slot's features from the as-of player states at that
   slot's first realized PA.

It is therefore unavailable at prediction time, is a diagnostic only,
and must never enter a deployable model input. Any Stage B contrast
involving it is interpreted on the scored subpopulation only.

## 3. Stage A — prediction-path equivalence (measurement repair)

**Purpose:** demonstrate that both lineup conditions' probabilities come
from ONE feature-construction path, so that any later contrast is
interpretable. Stage A reads NO outcomes.

- **Invariant:** for the batter-independent control arm, the two
  construction routes must produce identical PMFs: per start, per
  bucket k=0..23, `max |PMF diff| ≤ 1e-12` for every keyed start.
- **Allowed inputs (already-registered artifacts only):** the preserved
  ledger `projected_pa_probs_v1.parquet` (`fd1841e1…`), the frozen
  serialized checkpoint (pin `176fb18b…`; raw sha `d266a1cd…`),
  `bf_forecasts.parquet` (`c9c2762f…`), and the feature lineage verified
  by the M0 EP1 keyed check and the P0 full-population check
  (64,215 slot rows, 0 mismatches). No new feature construction beyond
  the two registered conditions' existing definitions.
- **Keyed cohort construction:** every start keyed by
  `(game_pk, side, pitcher)`; both arms attach features by KEY (never
  list order); exactly one row per key; fail-loud fan-out checks at
  every join (the game_pk+slot non-uniqueness lesson from P0 Part C
  applies).
- **Exclusion accounting:** the eligible population is the 4,823
  ledger-slot starts. Exclusions are counted in **mutually exclusive**
  buckets with a mandatory sum check
  (`4,823 = scored + excluded`, each start counted once). The prior
  demonstrated double-count (the 284 figure vs the true 142 exclusion)
  must be reconciled and reported in the receipt.
- **Tolerance:** 1e-12 absolute per-bucket PMF difference — the same
  bound used by the registered preflight identity checks.
- **Failure behavior:** if the control invariant fails on ANY start or
  bucket, STOP immediately: write the failure receipt, run NO Stage B,
  attempt NO variant or rescue, and report SHA / command / exit code /
  receipt to the architect (Chat 1 registered-stop rule).
- **Stage A output:** keyed comparison parquet + receipt recording the
  control max |PMF diff|, the exclusion accounting, and the consumed
  input hashes. No outcome-based numbers of any kind.

## 4. Stage B — outcome scoring (gated on Stage A PASS)

- Runs ONLY after Stage A PASS is recorded in a receipt.
- Metric: paired count-RPS, projected-lineup states vs oracle lineup
  states, on the single verified path; slate-date bootstrap (n=2000,
  seed 20261001 convention); Holm correction m=1 — the same registered
  machinery as prior accepted runs.
- Cohort: the keyed starts surviving Stage A. Every receipt discloses
  that the oracle condition is outcome-selected (Section 2); the
  contrast bounds the value of lineup-state information for the SCORED
  subpopulation only and is not a deployable performance estimate.
- **Stop condition:** publish the paired delta + CI, then stop for
  Chat 2 review. No tuning, no subgroup search, no additional arms.

## 5. Required authorization

Owner approval for ONE diagnostic run (Stage A; Stage B only on PASS).
Prohibited without separate authorization: protected-partition access
(`confirm_2025H2`, anything 2026), fitting, threshold search,
live-path changes, and any calibration execution.

## 6. Artifact identities

In-repo paths (at merged main `058bee1f`):

| artifact | path | identity |
|---|---|---|
| Impact ledger (D3 facts, P0, statuses) | `docs/reference/reports/experiment_impact_ledger_2026-10-22.md` | git blob `1a56598754ecbbc79ff9bc44b610c4ee716c5cf5` |
| Lineup diagnostic code | `research/offseason_2026/pregame_pa_ext/lineup_diagnostic.py` | git blob `c16003369692c589a249a958679c840b8f867844` |
| Authoritative market-eval table | `research/offseason_2026/pregame_pa_ext/results_market_eval_k_v1/RESULT_RECORD.md` | STATUS 5/6 sections |
| Question A record | `research/offseason_2026/pregame_pa_ext/results_count_agg_eval_v1/RESULT_RECORD.md` | primary table, delta −0.000333 |
| Ablation record | `research/offseason_2026/pregame_pa_ext/results_ablation_v1/RESULTS.md` | correction header |

Research-data-area artifacts (under the registered research data root,
`diagnostics/` directory; verified by SHA-256, not by transcription):

| artifact | directory | sha256 |
|---|---|---|
| Lineup diagnostic metrics | `lineup_diagnostic_v1_attempt6/` | `7a73578a2dda93bbb11df6215fec6409c22c942f2d2515221221d93ca4e59d40` |
| Lineup diagnostic final receipt | `lineup_diagnostic_v1_attempt6/` | `46d40962d8959f96250b58f481782aa029464df18c0414a9127d7379a3c98196` |
| Lineup diagnostic per-start parquet | `lineup_diagnostic_v1_attempt6/` | `582c81c30834395072698acf0c76d62ccfad38db61b912930e8c72857886e97a` |
| Ablation canonical bundle | `ablation_count_rps_canonical_v2_recovered2/` | contents hash-pinned in its receipts |
| Repaired market-eval scored parquet | `market_eval_k_v3_fullkey_attempt2/` | `1d9a00343d17956f…` (recorded in STATUS 5/6) |

Registered input identities consumed by any authorized run: ledger
`fd1841e1…`, checkpoint raw `d266a1cd…`, BF `c9c2762f…`, realized-K
`af6814ec…` (labels only, Stage B).

## 7. Review target

Chat 2 reviews THIS document as the complete specification: classification
(Section 0 header), established evidence and retired figures (Section 1),
oracle definition (Section 2), Stage A contract (Section 3), Stage B gate
(Section 4), authorization scope (Section 5), and artifact identities
(Section 6). Return `SPEC READY FOR OWNER AUTHORIZATION` or one
consolidated blocker list. No diagnostic execution before the owner
authorizes the exact run.
