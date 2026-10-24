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
- **EP1 (K-marginal non-inferiority): CROSS-PATH UNRESOLVED** (Chat 2's reconciliation) — the non-inferiority contrast pairs the multiclass arm's probabilities with the frozen binary arm's `p_h3_raw`, which travel different feature paths; recorded execution results and artifacts preserved intact, but the endpoint's interpretation is suspended until the attach_prior_features defect (below) is isolated.
- **M0 descriptive count-RPS: CROSS-PATH UNRESOLVED** for the same reason (its interpretation contrasts multiclass-implied K vs the frozen binary arm through the registered aggregation).
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

## P0 EXECUTED (bounded compatibility check, corrected 2026-10-22)

Artifact: \eature_request_p0/\ (write-once; ledger_compatibility_sample
.parquet, independent_implementation_sample.parquet,
adversarial_cases.parquet, p0_report.json). Code: research/offseason_2026/pregame_pa_ext/feature_request_p0.py\.
Sampling recipe: ledger slots with exclusion_reason null, n=3,000,
seed 20261022; comparisons keyed on the request row id.

- **(a) Frozen-function interface vs preserved ledger** (keyed, n=3,000):
  batter-side features (p_batter_prior_w150, ew_batter, n_prior_batter),
  lg_rate, cold_start — **0 mismatches**. Pitcher-side:
  **611/3,000 (20.4%) mismatch** (n_prior max 1,100 PAs; rate max
  0.046; ew max 0.197).
- **(b) Independent inline implementation vs ledger**: 150/3,150 (4.8%)
  mismatch on every history-dependent feature; exact elsewhere. The
  same 150 slots mismatch under BOTH implementations -> those ledger
  rows carry state from a different history source (identity-level
  resolution pending).
- **(c) Adversarial cases**: cold fallbacks behave; post-data dates
  extend state; batters in the game but outside the projected lineup
  get features with NO realized-appearance requirement (verified) —
  the interface can serve the oracle construction.
- **Representative-mismatch resolution**: the original P0 report's 761
  pitcher-side mismatches were a P0-side join artifact — the direct
  keyed recomputation verifies the ledger's n_prior_pitcher EXACTLY
  (0/3,000) against entity_daily_state. The remaining defect is inside
  the frozen attach_prior_features chain itself (pitcher-side only).
- **Hypotheses tested**: the asof-sortedness explanation was TESTED AND
  EXCLUDED (re-sorting p_state by (pitcher, game_date) does not change
  the 611). Category separation — source-history difference: the 150
  both-implementation mismatches are candidates; cutoff/join
  difference: the 611 frozen-function-only mismatches are candidates;
  feature-definition and implementation differences: not yet
  implicated. ROOT CAUSE NOT DECLARED — the next bounded test isolates
  which join inside attach_prior_features corrupts pitcher-side values.

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
