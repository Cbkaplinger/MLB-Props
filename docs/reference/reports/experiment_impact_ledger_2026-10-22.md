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

- Receipts: initial `aca95253…`, final `0d7decdf…`; eval keys `c9c2762f…`-free population: eval keys `c6568151…` exact (82,817 PAs, 4,823 starts); ledger `fd1841e1…`.
- EP1/EP2: per-PA metrics, registered population — defects excluded: D1 (market join never entered fitting/endpoints), D2 (per-PA scoring), D3. Pending: P0 ledger-path check (the refit features come from the ledger path).
- M0 descriptive count-RPS: ledger slots (verified) — D2 excluded; D1 excluded; pending P0.

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

## P0 EXECUTED (bounded compatibility check, mismatches preserved)

Artifact: `feature_request_p0/` (write-once; ledger_compatibility_sample
.parquet, independent_implementation_sample.parquet,
adversarial_cases.parquet, p0_report.json).

- **(a) Frozen-function interface vs preserved ledger** (3,000 sampled
  slots): p_pitcher_prior_w150, p_batter_prior_w150, lg_rate,
  cold_start — **0 mismatches** (exact). n_prior_pitcher **761
  mismatches** (max 2,440 PAs); n_prior_batter **150** (max 2,214);
  ew_pitcher **761** (max 0.20); ew_batter **150** (max 0.20).
- **(b) Independent inline implementation vs ledger** (3,150 rows):
  **150 mismatches (4.8%) on every history-dependent feature** (max
  diffs of the same magnitude); rates/cold_start exact on the rest.
- **(c) Adversarial cases**: cold batter/pitcher fall back to the
  league rate with n_prior=0 and cold_start=1; pre-data dates return
  pure league priors; post-data dates extend the state; **batters in
  the game but outside the projected lineup get features with NO
  realized-appearance requirement** (verified on 3 real cases) — the
  interface CAN serve the oracle construction.
- MISMATCHES PRESERVED; no frozen artifact repaired. The mismatch
  subset (~5-25% depending on feature) means the ledger's state was
  built from a history source that the pa_table-based reconstruction
  does not fully reproduce — the root-cause split (which window/rows)
  is the next bounded investigation.

## Revised endpoint-specific rerun plan

- **P0-result consequence**: the shared interface reproduces RATES
  exactly but NOT counts/EW for ~5-25% of slots — the ablation
  count-RPS recompute (P1) must NOT use the new interface blindly;
  first resolve the state-source mismatch (bounded: identify the
  150/761-mismatch slots' pitchers/dates and compare state windows).
- **P1 (after the state-source split)**: ablation count-RPS on the
  intended 4,823-start population, ledger-slot construction, using the
  VERIFIED feature source.
- **P2**: I3b/I4/I5 decision-logic re-audit — DOWNGRADED to optional:
  the BF builder is verified point-in-time; only the shared ledger
  feature path remains as a common dependency (P0-a).
- **P3**: lineup diagnostic redesign — blocked on the same
  state-source split (its two conditions need one path).
- **P4**: morning-market scoring on the 2,109-start cohort —
  UNAFFECTED by the P0 mismatch (it scores the ledger's own stored
  probabilities, no reconstruction) — eligible to run once this plan
  is accepted.
- 2026 holdout: untouched.

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
