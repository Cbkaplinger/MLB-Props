# PA Feature Lineage — L3 / T1 / T2 (Phase 8.5 sweep, 2026-09-30)

Canonical lineage for the frozen development baseline (L3 logistic, sha `489b892b…`) and the
Phase 8 tree arms (card sha `95b9627d…`). Evidence: `logistic_pa/bundle/feature_manifest.json`,
`logistic_pa/bundle/build_bundle.py` (reproduces stored L3 to 2.2e-16), `tree_pa/run_tree.py`,
`tree_pa/card.json`. Point-in-time document; superseded only by a new dated sweep.

## 1. Exact arm specifications

| Field | L3 (T0) | T1 | T2 |
| --- | --- | --- | --- |
| Library / version | statsmodels Logit (Phase 7) | lightgbm 4.7.0 | lightgbm 4.7.0 |
| Objective | binomial logit | binary (logloss) | binary (logloss) |
| Feature count | 24 | 23 | 23 |
| Feature families | F1–F5 + F6(rest/debut) + 4 trip/index | F1–F5 + 4 trip/index + logit(P3) | identical to T1 |
| Relationship to L3 | — | same validated feature construction minus F6, plus logit(P3) as baseline input | identical to T1 |
| Relationship to old 58/72 game-level sets | NONE — different grain (PA binary vs game rate), different registry | NONE | NONE |
| Leaves / depth / min_data | n/a | 7 / 3 / 500 | same |
| Feature fraction / bagging | n/a | 0.8 (no row bagging) | same |
| Learning rate / rounds / early stop | n/a | 0.05 / 200 / none | same |
| L1 / L2 | n/a | 0 / 1.0 | same |
| Class weights | none | none | none |
| Missing policy | nan_to_num(0); b_hand_rate→LG; park_k→1.0; rest→15.0 | nan_to_num(0); b_hand_rate→LG; park_k→1.0 | same |
| Monotone constraints | none | none | +1 on 10 K-tendency rates (semantics-assigned, registered in card before fitting; vector = [x0=0] + NAMES order, aligned) |
| Seed / determinism | n/a | seed 0, n_jobs 1, deterministic=True | same |
| Selection | 2023 folds F1/F2 (C grid) | 2023 folds F1/F2 (32-config grid) | best T1 config only |

Answers to the Phase 8.5 tree questions: (1) Yes — compact tree on the L3-era manifest (minus
F6, plus logit(P3)). (2) Yes, T2 ≡ T1 except constraints. (3) No 58/72 inheritance. (4)
Constraints assigned by registered domain semantics, not copied. (5) Vector aligned to feature
order by construction (length corrected pre-evaluation; logged in tree_pa deviations). (6) All
10 constrained directions defensible (higher K-tendency rates → higher K probability). (7) No
features forced in; F6 was already excluded; history/park retained because the card froze the
manifest before Phase 8 ran (F4/F5 weakness discovered only in post-evaluation ablations). (8)
No categoricals — hand/split encoded as numeric rate columns; trip/spi numeric. (9) Tree used
logit(P3) — the transparent baseline — as an input column, not stored L3 output. (10) Residual
correlation 0.9965 = Pearson corr of (prediction − label) between P3-log5 OOF and tree OOF on
2023 fold-eval rows (registered proxy; fold-fitted L3 models were not serialized, deviation
logged).

## 2. Feature-lineage matrix (shared inputs; L3 = all 24, tree = all rows except F6, plus logit(P3))

| Feature | Family | Raw source | Formula / construction | Natural grain | Window | Shift | As-of | Missing | Window status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| same_hand | F1 | pa_table `p_throws`,`stand` | indicator(thrower == batter) | STATIC_CONTEXT | none | — | pregame | none | FIXED_BASELINE_INPUT |
| b_hand_rate | F1 | pa_table `b_k_rate_std_vL/vR` | batter K-rate vs handedness, season-to-date | BATTER_FACED | season-to-date | prior PA | as-of game | →LG | INHERITED_CONVENTION |
| b_whiff / b_swstr / b_chase | F2 | pa_table batter rolling | season-to-date standardized discipline rates | PLATE_APPEARANCE | season-to-date | prior PA | as-of game | →0 | INHERITED_CONVENTION |
| p_whiff/swstr/chase/zone/contact_std (10 cols) | F3 | pitcher_rolling.parquet | season-to-date standardized rates per BF | BATTER_FACED | season-to-date (std) | prior starts | as-of game (same-date excluded) | →0 | INHERITED_CONVENTION |
| p_*_P5 (5 cols) | F3 | pitcher_rolling.parquet | trailing-5-start window of same rates | START | trailing 5 starts | prior starts | as-of game | →0 | INHERITED_CONVENTION (stabilization-era) |
| log_pa_curr | F4 | pitcher_games K_curr/PA_curr0 | log1p(season-to-date BF, excluding current game) | BATTER_FACED | season-to-date | prior starts | cum_sum − current row, first-over-date | →0 | INHERITED_CONVENTION |
| log_pa_prior | F4 | (none) | **INERT: constant 0 in every frame** (2023 has no 2022 prior in counts; bundle build zeroes both seasons) | — | — | — | — | constant | INERT — L3 coefficient unidentifiable; candidates for removal in any future manifest revision |
| park_k | F5 | park_factors.parquet | season×team park K factor via is_home→park_team | STATIC_CONTEXT | season-static | — | pregame | →1.0 | FIXED_BASELINE_INPUT |
| rest / debut | F6 | pitcher_games date gaps | days-rest clip(1,15); first-start-of-season flag | START / CALENDAR_DAY | since prior start | prior start | as-of game | →15 | EXCLUDED (Phase 7 fold ablation ≈ 0); L3-only |
| trip_eq_2/3, trip_ge_4, spi_over_9 | L3 interactions | pa_table sequence | trip = 1+((spi−1)//9); spi = PA index within start | PLATE_APPEARANCE | within-start position | — | structural | none | FIXED_BASELINE_INPUT (structural) |
| logit(P3) | baseline input (tree only) | pitcher_games + pa_table | P3 = (K_prior_seas + K_curr + 100·lg)/(PA_prior_seas + PA_curr + 100), lg=0.223813, then log5 vs batter 200-PA EB | BATTER_FACED + PLATE_APPEARANCE | prior season + season-to-date | prior BF | as-of game | none | SELECTED_ON_2023_FOLDS (m=100, Phase 6) |
| batter EB m=200 (inside logit P3) | baseline | pa_table | batter K-rate shrunk 200 pseudo-PA toward lg | PLATE_APPEARANCE | season-to-date | prior PA | as-of game | none | INHERITED_CONVENTION (owner-flagged) |

As-of integrity (bounded leakage audit): pitcher season-cumulatives exclude the current game;
pitcher_rolling joins are prior-only with same-date exclusion (permanently tested);
batter rolling is prior-PA; park/lineup context is pregame; no same-game outcome fields
enter any feature. Serving availability: every column is computable from pregame data
(2023 zero-prior convention is reproducible in serving); F6 rest also available but excluded.

## 3. Selection funnel (Phase 7–8)

| Family | Considered | Availability gate | Prior evidence | 2023 ablation (fold Δll) | In L3 | In tree | 2024 interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F2 batter discipline | yes | pass | stabilization curves | +0.000915 (dominant) | yes | yes | strongest family (permutation +0.0032) |
| L3 trip/index terms | yes | pass | n/a (structural) | +0.001369 | yes | yes | second-strongest |
| F1 platoon | yes | pass | conventional | +0.000367 | yes | yes | small but consistent |
| F5 park | yes | pass | conventional | +0.000215 | yes | yes | ≈0 in permutation — retained by frozen-card rule, not evidence |
| F3 pitcher discipline | yes | pass | stabilization curves | +0.000148 | yes | yes | modest, right-signed |
| F4 history | yes | pass | conventional | −0.000036 | yes (one inert col) | yes | redundant with baseline; log_pa_prior inert |
| F6 rest/debut | yes | pass | Phase 7 ablation | ≈0 | yes (L3 only) | no | EXCLUDED_FROM_NEXT_PA_K_MANIFEST |
| Command/stuff, repertoire, age, weather, umpire | no | rejected pre-registration (availability/stability) | earlier kills (#52/#57/#60–#65/#63) | n/a | no | no | retired in writing (retrain spec) |

Evidence hierarchy: drop-family ablation primary; grouped permutation secondary (families
permuted jointly — correlated discipline features never judged individually); logistic
coefficient stability supporting. SHAP unused (no incremental claim beyond permutation);
VIF unused (tree phase has different collinearity semantics; logistic families stayed
grouped). Post-evaluation interpretation never pruned a feature.

## 4. Window status and the one bounded sensitivity candidate

Statuses: P5 windows — STABILIZATION_SUPPORTED (inherited from pre-PA stabilization curves,
never varied since). Season-to-date windows — INHERITED_CONVENTION. Batter EB m=200 —
INHERITED_CONVENTION (owner-flagged). P3 prior weight m=100 — SELECTED_ON_2023_FOLDS. Park —
FIXED_BASELINE_INPUT. No family uses exponential decay; no calendar-season reset where
carry-forward is more defensible was found (pitcher K_curr resets per season by registration;
the P3 prior season term is the carry-forward).

Exactly one future bounded sensitivity card is plausible: batter shrinkage m ∈ {100, 200, 400}
and P5 window length ∈ {3, 5, 7}, 2023-fold selection only, only if 2025 validation shows
calibration drift plausibly attributable to shrinkage. Do NOT run now; would reopen a search
already stopped. All windows reproduce identically in serving (bundle manifests freeze the
construction; guards G5/G8 pin it).

## 5. Tree stop decision

**TREE SEARCH: CLOSED.** The stop rule was applied correctly: T1 ties L3 in both blocks (paired
CIs straddle 0), the blend gate failed on residual correlation 0.9965, and oracle aggregation
shows no separation. The current feature representation contains no demonstrated nonlinear gain.
Reopen ONLY on: a materially new feature family (repertoire compatibility, lineup-quality), a
new representation, a different target, a proven Phase 8 implementation defect, or a
pre-registered card not conditioned on 2024. Never: more leaves/depth/rounds/seeds, repeated
2024 evaluation, or 58/72-feature revival without a new availability + transferability audit.

## 6. Canonical paths

- L3: `research/offseason_2026/experiments/logistic_pa/` (card, metrics, predictions, bundle/)
- Guards/contracts: `tests/test_pa_research_guards.py`, `research/offseason_2026/contracts/pa_contracts.py`
- Tree: `research/offseason_2026/experiments/tree_pa/` (card, metrics, predictions, report)
- Validation lanes: `research/offseason_2026/experiments/logistic_pa/validation_lanes.md`
- Durable record: `docs/reference/reports/pa_overhaul_phase4_5_record_2026-09-29.md`

## 7. Relation to the companion Phase 8.5 record (C8 cross-link, 2026-09-30)

- This document = detailed feature provenance and inheritance analysis (inputs,
  windows, selection funnel, inert-feature proof).
- `docs/reference/reports/phase8_5_truth_sync_2026-09-30.md` = concise current-state
  reconciliation (arm verdicts, doc-update queue, MLflow mapping).
- Neither supersedes the other; neither is deleted or obsolete. Entry point for
  "what does the model consume": this file. Entry point for "where do we stand":
  the truth-sync record. Known precision debt in the companion record (owned by the
  concurrent session, correction queued not applied): residual correlation 0.9965 is
  the P3-log5-OOF proxy pair only, and the 2.2e-16 reproduction belongs to L3 bundle
  reconstruction, not the tree run — see `pa_split_provenance_correction_2026-09-30.md`
  conventions for how execution actually behaved.
