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

### 1. Market evaluation (pitcher_strikeouts vs near-close)

- Code: `market_eval_k.py` at `23db50d` (rescore), accounting at `a4ded18`, runner fixes at `70883ae`.
- Cohorts: 2025H1 true T-5 close n=2,154 (key hash in receipt); 2024 prior-evening n=2,182 (`b517101d6d6967b7`).
- Feature builder: frozen FEAT_H3 via the serialized checkpoint (pin `176fb18b…`); ledger `fd1841e1…`; BF `c9c2762f…`; realized `af6814ec…` (label-audited 100%).
- Comparator: de-vigged near-close consensus, per-start identity (repaired).
- Classification: **corrected and reverified** (2025H1 cohort). The 2024 cohort is a prior-evening benchmark, not a close comparison. Historical pre-repair results: **invalid, preserved**.

### 2. Feature/half-life ablation

- Code: `ablation_features.py` at `f46b064`.
- PA metrics (multiclass LL 1.22305 FULL vs 1.23192 PITCHER; K-marginal): scored on all 82,817 eval PAs, registered population, frozen recipe features — **unaffected** by the count-slot defect and the market join; retained.
- Count-RPS column: scored ~277/block (realized-PA slot conditioning) — **invalid for the intended 4,823-start cohort**; the "batter features hurt count-RPS" ranking derived from it: **retracted**.
- Half-life conclusion "does not matter": the PA log-loss evidence stands (EW30-180 within 0.0002 multiclass LL on all eval PAs); the count-RPS evidence was on the invalid subset — **retain 90d operationally; withdraw the universal claim**.

### 3. M0 v2 (four-class PA model)

- Code: `m0_multiclass.py` at `2e2482b` (+ae3cd19 fixes); executed once at the owner's delegated order.
- Receipts: initial `aca95253…`, final `0d7decdf…`; eval keys `c6568151…` exact (82,817 PAs, 4,823 starts); ledger `fd1841e1…`.
- EP1/EP2 are per-PA metrics on the registered population with frozen features — **unaffected** by the market-join and count-slot defects (development-only acceptance; the market join never entered M0's fitting or endpoints).
- M0 descriptive count-RPS: used the LEDGER slots (verified) — **unaffected** by the realized-PA conditioning defect; status: development-only diagnostic (close-benchmark comparison now supersedes it as context).

### 4. C-B1 exposure profile (rejected)

- Code: `exposure_profile.py` at `b026646`; executed once; receipts `18c98d81…`/`1d125e6f…`.
- Its per-start PMFs used the LEDGER slots (verified in `exposure_profile.py:count-rps` wiring via the frozen prior from ledger slots and the registered aggregation), population 4,823, comparator = the frozen arm through the same machinery.
- Classification: **unaffected** by the realized-PA slot defect and the market-join defect — the rejection (delta +0.0859 CI [+0.0719, +0.0997]) stands on its own verified population. Residual caveat: the frozen prior and comparator share the ledger feature path; a defect in THAT path would reach C-B1 — covered by the ledger-path verification below.

### 5. Batter-recency diagnostic (rejected)

- Code: `batt_recency.py`; paired log-loss on the registered 82,817-PA eval population; frozen features; receipts hash-pinned in `results_batt_recency_v1/`.
- Classification: **unaffected** (per-PA metric, registered population, no count-layer or market dependency). Shares `build_feature_frame` — covered by the same ledger-path verification as C-B1.

### 6. Count aggregation / Question A (count_agg_eval_v1)

- Code: `count_agg_eval.py`; executed once on the registered 4,823 starts; p9 = ledger slots (verified); receipts in `results_count_agg_eval_v1/`.
- Classification: **unaffected** by the realized-PA conditioning defect (its slots were always ledger-projected). Its comparator/PMF machinery is shared with everything above — same ledger-path coverage.

### 7. Workload / BF gates, I3b/I4/I5, earlier transfer decisions

- Artifacts: lake `bf-workload-v1` (bf_forecasts `c9c2762f…`, start_metrics_v2 `af6814ec…`), `i3-opportunity-*`, `i4-card-source-*`, `i5-tail-*`, `pa-aggregation-abc-*`, `kcount-integration-*`.
- These lanes produced the BF artifact that EVERY count metric consumes; their internal validation used the same builders (entity_daily_state lineage, pregame-state-v1 lineups).
- Classification: **unresolved — shared-builder trace pending**. Historical age is not evidence of independence. The BF artifact's inputs (prior_n/prior_mean per start) are pregame state; no realized-APPEARANCE conditioning has been demonstrated in it, but the trace has not been performed.

### 8. Lineup/oracle diagnostic

- Classification: **invalid as a lineup-effect estimate** (control-invariant failure + outcome-selected oracle cohort + positional output assignment + drop double-counting). Preserved as diagnostic-failure evidence.

### 9. Market comparisons (historical)

- Pre-repair results: **invalid, preserved**. The repaired 2025H1/2024 split baselines: **corrected and reverified** (independently reviewed). Morning scoring: paused pending this ledger.

## The four runner issues (investigated, fixes deferred to the plan)

1. **Combined cold_start in PITCHER**: verified — the flag is `(prior_n_pitcher == 0) | (prior_n_batter == 0)`; a genuine pitcher-only control requires a pitcher-only cold-start definition (a NEW diagnostic definition, not a silent redefinition).
2. **Outcome-selected oracle cohort**: verified — >= 9 distinct batters actually faced excludes short outings by outcome.
3. **Positional per-start assignment**: verified — FULL arrays aligned to sorted keys are attached positionally to PITCHER list-order records; row-level outputs can be misassigned while aggregate means survive.
4. **Drop accounting**: verified — 4,823 − 284 ≠ 4,681; the counters double-count (the oracle loop and the completion filter both increment; the true exclusion is 142). Mutually exclusive start-level reasons required.

## Proposed shared as-of feature-request interface

`feature_request(pitcher_id, batter_id, as_of_date) -> the 8 FEAT_H3
values`, built from the frozen entity state tables
(`entity_daily_state` for pitcher/batter + `league_daily_state`):
attachable to ANY (pitcher, batter, date) triple — including projected
batters who never batted and actual batters outside the projection —
with NO dependence on realized appearances. Compatibility proof before
replacing any historical path: recompute the interface for a sample of
the preserved ledger's projected slots and verify equality with the
ledger's stored feature values (bounded check; NOT yet run — it is the
first item of the rerun plan).

## Prioritized minimal rerun plan (no execution yet)

- **P0 — ledger-path compatibility check** (bounded, no tuning):
  verify `feature_request` reproduces the preserved ledger's stored
  slot features on a sample; this validates the shared path that M0,
  C-B1, Question A, and the market baseline all inherit.
- **P1 — ablation count-RPS recompute** on the intended 4,823-start
  population using ledger-slot construction (restores the feature
  ranking; informs whether batter features help or hurt the count
  layer on the correct cohort).
- **P2 — shared-builder trace** for the BF/workload and I3b/I4/I5
  lanes (documentation-level; rerun only if a defect surfaces).
- **P3 — lineup diagnostic redesign** (pitcher-only cold-start split,
  same-path features, keyed outputs, mutually exclusive drop
  accounting) — only if the lineup question remains decision-bearing
  after P1.
- **P4 — morning-market scoring** on the published 2,109-start cohort
  (protocol already frozen) — after P0-P2 restore confidence.
- 2026 holdout: untouched until all of the above are accepted.
