# Lineup prediction-path reconciliation — specification (2026-10-27)

Status: **SPECIFICATION PUBLISHED FOR CHAT 2 REVIEW — not executed, not
authorized.** This is a measurement-reconciliation candidate only. It is
NOT evidence that lineup quality is the dominant model bottleneck.

**Active scope (2026-10-27 revision): STAGE A ONLY.** Stage A
(prediction-path equivalence) is the only active task. Stage B (outcome
scoring) is DEFERRED: a Stage A PASS does NOT authorize Stage B; Stage B
requires its own explicit owner authorization after review of the Stage
A receipts.

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
interpretable. Stage A reads NO outcomes and computes NO scores.

### 3a. Data boundary (complete)

- **No realized-K labels.** `start_metrics_v2.parquet` (`af6814ec…`) is
  NOT consumed in Stage A. No scoring, no RPS, no log loss, no Brier, no
  bootstrap is computed in Stage A.
- **Realized-PA-derived inputs — full disclosure.** Two distinct things
  must not be conflated:
  1. **Pregame player-history features** (prior PA counts, rates, EWMA
     as of the start) are derived from plate appearances BEFORE the
     start. These are legitimate pregame inputs, identical to what every
     authorized experiment consumed, and are permitted in Stage A.
  2. **Within-game realized-PA conditioning** (the "oracle" slot
     construction of Section 2) is realized-PA-derived selection and is
     EXCLUDED from Stage A entirely. Stage A compares construction
     routes for the batter-independent control arm only, where both
     routes must use pregame states.
  If any consumed value is found to embed within-game realized-PA
  conditioning, Stage A stops and reports it as a boundary violation.
- **Every consumed artifact (enumerated):**

| artifact | role in Stage A | identity |
|---|---|---|
| Preserved ledger slot projections | the registered per-(start, slot) p_h3_raw probabilities and pregame states | `projected_pa_probs_v1.parquet`, sha `fd1841e1…` |
| Frozen serialized checkpoint | the feature-builder lineage (FEAT_H3, pin `176fb18b…`) | `h3_raw_checkpoint.json`, raw sha `d266a1cd…` |
| BF workload forecasts | pregame BF distribution feeding both arms' count-PMF aggregation identically | `bf_forecasts.parquet`, sha `c9c2762f…` |
| Verified builder code | `build_feature_frame` (M0-EP1 keyed check) + repaired `attach_prior_features` (P0 full-population check) | committed code at the executing SHA |
| NOT consumed | `start_metrics_v2.parquet` (realized K) — Stage B only; anything 2026 or `confirm_2025H2` — prohibited | — |

### 3b. Fixed features

The eight registered FEAT_H3 features, exactly as verified in P0 Part B
(independent reproduction, 0/8 mismatches on 3,000 keyed rows; full
64,215-slot population check, 0 mismatches): pitcher-side prior PA
count, pitcher-side prior rate, pitcher-side EWMA rate, batter-side
prior PA count, batter-side prior rate, batter-side EWMA rate, league
rate, `cold_start` (combined pitcher-or-batter flag, `adapter.py`
definition). NO feature is modified, added, dropped, or recomputed with
different settings. Any deviation is a spec violation.

### 3c. Keyed attachment

- Every start is keyed by `(game_pk, side, pitcher)`; every slot by
  `(game_pk, side, pitcher, slot)`. The `game_pk+slot` non-uniqueness
  lesson from P0 Part C is enforced: both starters share slot numbers,
  so all joins carry the full key.
- `attach_prior_features` sorts the incoming frame chronologically
  internally (repaired contract; regression-tested
  `tests/test_attach_order_invariance.py`); request identity is
  preserved; attachment is by KEY, never by list position.
- As-of joins use each slot's pregame timestamp; no state may read at or
  after first-pitch.
- Fan-out checks at every join fail loud (`validate="1:1"` keyed
  comparisons).

### 3d. Intermediate comparisons (each gets its own receipt section)

| # | intermediate | comparison | tolerance |
|---|---|---|---|
| I1 | attached feature vectors | each route vs the ledger's stored per-(start, slot) values, keyed | exact (0 mismatches, all 8 features) |
| I2 | per-slot PA probabilities | route A vs route B per (start, slot) | ≤1e-12 absolute |
| I3 | per-start count PMFs (24 buckets) | route A vs route B after identical BF aggregation | ≤1e-12 absolute per bucket |
| I4 | control invariant (the gate) | max over I3 | ≤1e-12 for every keyed start |

### 3e. Eligibility and exclusions

- Eligible population: all 4,823 ledger-slot dev starts
  (`block_2024H2` ∪ `block_2025H1`). The control arm has no
  completion filter — the ≥9-realized-slots requirement belonged to the
  oracle condition and does not apply in Stage A.
- Any exclusion must be pre-declared in this spec, counted in mutually
  exclusive buckets, and must satisfy the sum check
  `4,823 = scored + excluded` with each start counted exactly once.
  The prior demonstrated double-count (the 284 figure vs the true 142
  exclusion) is reconciled in the receipt.
- Protected partitions (`confirm_2025H2`, anything 2026) are absent from
  the consumed frame; the runner rejects unexpected block labels.

### 3f. Justification of the control invariant

The batter-independent control arm must be path-invariant BY
CONSTRUCTION: batter-side inputs are identical by definition, and
pitcher-side inputs come from the same pregame state tables through the
same verified builder. The merged evidence chain — M0 EP1 keyed check
(same builder on both arms, reproduces the independent implementation
0/8 features on 3,000 keyed rows) and P0 (attachment reproduces the
64,215-row ledger population exactly after the order repair) — supports
identical outputs up to floating-point associativity noise. The 1e-12
bound is the same absolute tolerance already used by the registered
preflight identity checks. The demonstrated failure (max |PMF diff| =
0.1143, ~11 orders of magnitude above the bound) was therefore a real
path divergence, not noise — which is exactly what Stage A must rule
out deterministically.

### 3g. Synthetic end-to-end smoke-test plan (no real data)

Implemented as committed tests before any authorized Stage A run, on a
deterministic fixture (2 games × 2 starters × 9 slots with
hand-computable pregame states):

1. **Keyed-attachment order invariance:** chronological, shuffled, and
   reversed request orders produce identical attached features and
   identical PMFs (extends `test_attach_order_invariance.py` to the
   count-PMF boundary).
2. **Fan-out detection:** a duplicate/ambiguous key fixture must fail
   the join loudly (no silent borrowing).
3. **Exclusion accounting:** a fixture with a declared exclusion
   satisfies the exclusive-bucket sum check; an inconsistent counter
   fixture must fail.
4. **Control invariant PASS:** the synthetic two-route control
   comparison holds at ≤1e-12 across all 24 buckets.
5. **Failure-mode proof:** a deliberately corrupted route (one feature
   attached by list order) MUST fail the control invariant — proving
   the gate can actually fire.
6. **Boundary check:** the Stage A code path asserts it never reads
   realized-K labels (e.g., the synthetic frame omits them entirely and
   the loader would raise).

The smoke tests are synthetic-only and require no authorization beyond
the standing synthetic-test permission; they are the precondition for
requesting Stage A authorization, not a substitute for it.

### 3h. Failure behavior

If the control invariant fails on ANY start or bucket at any
intermediate I1–I4, STOP immediately: write the failure receipt, run NO
Stage B, attempt NO variant or rescue, and report SHA / command / exit
code / receipt to the architect (Chat 1 registered-stop rule).

### 3i. Stage A output

Keyed comparison parquet + receipt recording: control max |PMF diff|,
the I1–I4 intermediate tables, the exclusion accounting with sum check,
the consumed-input hashes, and the executing code identity. No
outcome-based numbers of any kind.

## 4. Stage B — outcome scoring (DEFERRED)

**Stage B is deferred. A Stage A PASS does NOT authorize it.** Stage B
requires its own explicit owner authorization after Chat 2 reviews the
Stage A receipts. For completeness, its registered shape when and if
authorized:

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

- **Synthetic smoke tests (Section 3g):** permitted under the standing
  synthetic-test permission; precondition for requesting Stage A.
- **Stage A real-data run:** requires owner approval of the exact run
  after this spec passes Chat 2 review.
- **Stage B:** separately authorized only after Stage A receipts are
  reviewed.
- Prohibited without separate authorization: protected-partition access
  (`confirm_2025H2`, anything 2026), fitting, threshold search,
  LightGBM or any model tuning, live-path changes, and any calibration
  execution.

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
(header), established evidence and retired figures (Section 1),
oracle definition (Section 2), the Stage A contract with data boundary,
fixed features, keyed attachment, intermediate comparisons, eligibility,
invariant justification, and synthetic smoke tests (Section 3), the
DEFERRED Stage B shape (Section 4), authorization scope (Section 5), and
artifact identities (Section 6). Return `SPEC READY FOR OWNER
AUTHORIZATION` (Stage A only) or one consolidated blocker list. Only the
changed content relative to the previously reviewed head `b2090cc` needs
re-review. No diagnostic execution before the owner authorizes the exact
Stage A run.
