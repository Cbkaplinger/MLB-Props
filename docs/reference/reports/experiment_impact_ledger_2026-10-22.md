# Experiment impact ledger — pregame-pa-ext-v2 lane (2026-10-22)

Purpose: trace every decision-bearing experiment through its actual
dependencies (decision → metric → scored cohort → forecasts → feature
builder → input artifacts → code version), classify it
(invalid / unresolved / unaffected / corrected-and-reverified), and
propose the minimal rerun plan. NO reruns or tuning performed for this
ledger; all original artifacts preserved.

## Verified dependency facts (code-level evidence)

| fact | evidence |
| --- | --- |
| `cold_start` is a COMBINED flag: 1 when either the pitcher OR the batter has no prior history | `adapter.py:284-286` — `(prior_n_pitcher == 0) \| (prior_n_batter == 0)`. Therefore the "PITCHER-only" ablation arm contains batter-dependent information and is NOT a valid batter-independent control |
| The registered count layer's per-start p9 comes from the preserved LEDGER's nine projected slots (`p_h3_raw`), NOT from realized-PA-conditioned slots | `count_agg_eval.py:227-273` (slots from the ledger); `m0_multiclass.py` stage 6 (same source) |
| The FEATURE-ABLATION count-RPS used realized-PA-conditioned slots (first realized PA per projected slot; requires all nine projected batters to have batted) and therefore scored only ~277 starts/block | `ablation_features.py:count_rps_from_eval` (unique per (start, slot) on the eval-PA frame); measured: 277 scored / 4,546 skipped in the diagnostic run |
| The lineup diagnostic's two conditions draw probabilities from DIFFERENT feature-construction paths (ledger as-of slot states vs pa_table-attached states) | Control invariant failure: max PMF diff 0.1143 >> 1e-12 for the batter-independent arm (lineup_diagnostic_v1_attempt6 receipt) |
| The oracle condition is outcome-selected (requires >= 9 distinct batters actually faced) and uses first-nine-DISTINCT-batter order, not the official lineup when substitutions precede a first appearance | `lineup_diagnostic.py:_appearance_order_p9` |
| The runner's per-start output attaches FULL scores positionally to PITCHER records in list order, not by key | `lineup_diagnostic.py`: `pl.DataFrame(per_start).with_columns(pl.Series("rps_full_projected", rpF)...)` where rpF is aligned to sorted common keys |
| The drop counters are not mutually exclusive: 4,823 − 284 ≠ 4,681 | The oracle loop counts a missing-p9 start, and the completion filter recounts starts whose projected row was later dropped; the TRUE exclusion is 142 (4,823 − 4,681); the 284 figure double-counts |
| Market-eval identity repair: verified_odds_for_start + per-start consensus + full-key join, independently reviewed at the repaired version | `market_eval_k.py`; owner code inspection; repaired rescore `market_eval_k_v3_fullkey_attempt2` (scored parquet `1d9a00343d17956f`) |

## STATUS 11 (v2 source RECOVERED from the reflog, 2026-10-24, latest)

The detached-HEAD v2 commit b7aad8e2d9914cc59b7e158a694890b53961d5f6
was RECOVERED from the originating worktree reflog (no reconstruction
needed) and restored as the branch head. RECOVERY VERIFICATION: the
recovered runner re-executed in a new write-once directory
(ablation_count_rps_canonical_v2_recovered2) reproduces the preserved
attempt5 numbers EXACTLY (4,823 starts, PITCHER 1.33457, FULL
1.31744; train windows 2024-05-02/2024-08-02 cutoffs from actual max
game dates 2024-06-30/2024-09-30; drop table sums matched). The
recovered source IS the original executed code. CANONICAL BUNDLE:
ablation_count_rps_canonical_v2_recovered2/ (per-start outputs,
metrics, receipts). The ablation count-RPS correction is now
CANONICAL: PITCHER 1.33457, FULL 1.31744, FULL-frozen -0.00017 CI
[-0.00037, +0.0000282] (includes zero; no improvement over frozen
binary demonstrated). Earlier failed attempts preserved:
ablation_count_rps_canonical_v1 (calendar cutoffs + hardcoded
comparator - superseded), _v2 (NameError), _v2_attempt2/5 (pre-recovery
executions of the same recovered code).

## The ledger

Classification key — "unaffected" now states the SPECIFIC defects
excluded and the upstream checks still pending:

- D1 = opposing-starter quote mixing + per-game market collapse
  (market join; repaired)
- D2 = realized-PA-conditioned slot construction (count layer)
- D3 = projected/oracle feature-path divergence (lineup diagnostic)
- P0 = the ledger-path compatibility check (executed this turn, below)

### 1. Market evaluation (pitcher_strikeouts vs near-close)

- Code: `market_eval_k.py` at `23db50d` (rescore), accounting at `a4ded18`, runner fixes at `70883ae`.
- Cohorts: 2025H1 true T-5 close n=2,154; 2024 prior-evening n=2,182 (`b517101d6d6967b7`).
- Feature builder: frozen FEAT_H3 via the serialized checkpoint (pin `176fb18b…`); ledger `fd1841e1…`; BF `c9c2762f…`; realized `af6814ec…` (label-audited 100%).
- Defects excluded: D1 (repaired + independently reviewed), D2 (its slots were always ledger-projected), D3 (no lineup conditions).
- Upstream checks still pending: the ledger feature path itself (see P0 results — PARTIAL mismatch found).
- Classification: **corrected and reverified** for D1/D2/D3; **unresolved on the ledger feature-path mismatch** (P0-a).

### 2. Feature/half-life ablation

- Corrected coverage counts (exact, per block): block_2024H2 scored
  **117 of 2,314 starts (5.1%)**; block_2025H1 **160 of 2,509 (6.4%)**;
  total **277 of 4,823 (5.7%)**. Slot-count distribution: median 7
  distinct realized slots; only 5.7% of starts have all nine.
- PA metrics (multiclass LL 1.22305 FULL vs 1.23192 PITCHER; K-marginal): scored on all 82,817 eval PAs — defects excluded: D1, D2 (per-PA scoring has no slot requirement), D3. Pending: P0 ledger-path check.
- Count-RPS column: **invalid for the intended cohort** (D2 demonstrated); the ranking derived from it: retracted.
- Half-life: PA evidence retained (D1/D2/D3 excluded); count evidence invalid.

### 3. M0 v2

- Receipts: initial `aca95253…`, final `0d7decdf…`; eval keys `c6568151…` exact (82,817 PAs, 4,823 starts); ledger `fd1841e1…`. Recorded execution results and original artifacts intact.
- EP2 (vs baselines): per-PA metrics, registered population — defects excluded: D1, D2, D3. Pending: P0-b ledger-path check.
- **EP1 + descriptive count-RPS: CROSS-PATH BLOCKER CLOSED** (keyed check): both arms consumed the SAME builder (`build_checkpoint.build_feature_frame` on the same realized-PA lineage), and that builder's output reproduces exactly against the independent implementation (0/8 features, 3,000 keyed rows). Same path confirmed at the comparison boundary -> no replay required for the feature-path concern. The attachment order-sensitivity defect never fired on these chronological inputs (caller assessment + full-population check). Recorded results stand as development-only acceptance.
- Status: execution recorded; EP1 + descriptive count interpretation unresolved; EP2 pending P0-b.

### 4. C-B1 (rejected)

- Per-start PMFs from LEDGER slots (verified); population 4,823; comparator = the frozen arm through the same machinery; receipts `18c98d81…`/`1d125e6f…`.
- Defects excluded: D1, D2, D3 (its prior and comparator both live on the ledger path — no cross-path divergence). Pending: P0 ledger-path check.
- Classification: **unaffected by D1/D2/D3; pending P0** — the rejection stands unless the ledger-path mismatch (P0-a) reaches its prior/comparator.

### 5. Batter-recency diagnostic (rejected)

- Paired per-PA log-loss, registered 82,817-PA population, frozen features, receipts hash-pinned.
- Defects excluded: D1, D2, D3. Pending: P0 ledger-path check (shares `build_feature_frame`).
- Classification: **unaffected by D1/D2/D3; pending P0**.

### 6. Count aggregation / Question A

- p9 = ledger slots (verified); population 4,823; receipts in `results_count_agg_eval_v1/`.
- Defects excluded: D1, D2, D3. Pending: P0 ledger-path check.
- Classification: **unaffected by D1/D2/D3; pending P0**.

### 7. Workload / BF gates, I3b/I4/I5

- **P0-parallel trace EXECUTED**: `build_bf_forecasts.py` verified as a
  point-in-time chronological expanding pregame builder — per-pitcher
  state is READ BEFORE the start's outcome is added (lines 132-133 vs
  179-181), lineup-free, cold-start handled, league priors shrunk
  (W_SHRINK); realized BF stored only as the TARGET. No
  realized-appearance conditioning of the forecast.
- I3b/I4/I5 artifacts consumed this same builder's output
  (i3-opportunity-*, i4-card-source-*, i5-tail-*).
- Classification: **BF builder traced, point-in-time verified**; the
  I3b/I4/I5 decision logic itself is not re-audited (documentation
  level). Their dependence on the ledger feature path does not exist
  (lineup-free) — their inputs are the BF artifact + start_metrics.

### 8. Lineup/oracle diagnostic

- **Invalid as a lineup-effect estimate** (D3 control-invariant failure, outcome-selected oracle cohort, positional assignment, drop double-counting). Preserved as failure evidence.

### 9. Market comparisons (historical)

- Pre-repair: **invalid, preserved**. Repaired split baselines: **corrected and reverified**. Morning scoring: paused pending this ledger.

## STATUS 10 (attachment defect REPAIRED, 2026-10-22, latest) —
The owner's code-level lead CONFIRMED and REPAIRED: attach_prior_features
did not sort the incoming frame before the first grouped as-of join;
request-order sensitivity was DEMONSTRATED (same 3,000 requests,
591-621 feature mismatches by input order) and the mechanism was
demonstrated (pre-sorting the LEFT frame eliminates it: 0 mismatches).
PATCH: the function sorts long by game_date internally (join contract
enforced at the function boundary; request identity preserved).
REGRESSION TESTS: tests/test_attach_order_invariance.py (4 tests,
chronological/shuffled/reversed invariance + pairwise equality).
CALLER ASSESSMENT: both historical callers (build_checkpoint's
realized-PA training frame and the ledger build) pre-sort their inputs
chronologically — the historical training/scoring paths were NOT
affected by the order defect. FULL-POPULATION CHECK: the patched
function reproduces the entire 64,215-row eligible+confirm ledger slot
population exactly (0 mismatches, all 8 features).
P0 v2 (previous section) results re-interpreted under the repair: the
611 pitcher-side mismatches were ORDER artifacts of the sampled
request input, not a persistent pipeline corruption. The independent
reproduction (Part B) and the patched attachment (this section) AGREE
with the preserved ledger everywhere.
SCOPE CLOSED for the attachment contract; the ledger feature path is
VERIFIED end-to-end (frozen state tables -> attach -> stored values).
Remaining open items are unchanged: none blocking the morning
benchmark or the 2026 holdout protocol; morning scoring and 2026
access remain gated by their own orders.

## P0 v2 EXECUTED (identity-safe, non-overwriting, 2026-10-22, latest)

Artifact: `feature_request_p0_v4/` (write-once; partA/partB comparison
parquets keyed on request _rid with validate="1:1", adversarial cases
labeled by ID, report JSON). The ORIGINAL P0 directory is preserved
with PRESERVED_MANIFEST.json (all four file hashes recorded before the
corrected run). Code: `feature_request_p0.py` committed; the v2 audit
script to be committed alongside this ledger update.

- **Part A** (frozen attach_prior_features vs ledger, keyed): 611/3,000
  (20.4%) hard mismatches — ALL pitcher-side (n_prior_pitcher max
  1,100 PAs; rate max 0.046; ew max 0.197); zero one-sided nulls;
  batter-side, lg_rate, cold_start exact.
- **Part B** (independent formulas vs ledger, keyed): **0 mismatches on
  all 8 features** — the independent reproduction reproduces the
  preserved ledger EXACTLY.
- **Part C**: the 150-row "source-history class" DISAPPEARS after the
  incomplete-key join is removed — it was an audit-side fan-out
  artifact (game_pk+slot is not a unique request key: both starters
  share slot numbers).

DEMONSTRATED DIAGNOSIS (not a hypothesis):
1. The preserved ledger's stored features are CORRECT (exactly
   reproduced by an independent implementation).
2. The frozen attach_prior_features chain corrupts ~20.4% of
   pitcher-side values when called on request-row inputs — the defect
   is in the attachment chain, not the historical state.
3. The earlier "different history source" hypothesis is withdrawn.

SCOPE RESOLVED: both historical callers (build_checkpoint's training
frame and the ledger build) pre-sorted their inputs chronologically,
and the full-population check (64,215 ledger slot rows + the M0 EP1
boundary check) reproduces every stored feature exactly. The order
defect never fired on historical paths. The state-source-split
hypothesis is WITHDRAWN (no residual mismatch survives the
sorted-input check). The ablation count-RPS correction is EXECUTED
(PITCHER 1.29880 / FULL 1.28419 on the intended 4,823-start cohort).


## Authoritative status per endpoint

- Market evaluation (repaired): corrected and reverified (D1/D2/D3
  excluded); P0-b ledger-path check pending on the frozen-function
  defect.
- M0 v2: execution recorded (receipts intact). EP2 pending P0-b.
  EP1 and descriptive count-RPS: CROSS-PATH UNRESOLVED (Chat 2
  reconciliation).
- C-B1: rejection stands on its verified population; P0-b pending.
- Batter-recency: rejection stands; P0-b pending.
- Question A: stands; P0-b pending.
- Ablation: PA metrics stand (D1/D2/D3 excluded); count-RPS invalid
  for the intended cohort (D2 demonstrated).
- Lineup/oracle diagnostic: invalid as a lineup-effect estimate.
- BF/workload builder: traced, point-in-time verified; I3b/I4/I5
  lineage closed at the builder level, their decision logic documented
  as consumed (no re-audit triggered).

## Smallest matched-path endpoint replay (proposed, after provenance)

Once the attach_prior_features defect is isolated and a verified
single-path feature source exists: replay ONE endpoint first — the
ablation count-RPS on the 4,823-start ledger-slot population (smallest,
self-contained, directly corrects a retracted ranking) — then re-verify
M0's EP1 pairing on the same single path. Original settings preserved;
no tuning during repair. Nothing reruns until the defect isolation
passes.
