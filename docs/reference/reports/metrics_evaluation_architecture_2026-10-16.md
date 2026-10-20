# Metrics-and-evaluation architecture map — 2026-10-16 (Chat 3, report-first)

Canonical map of **where each metric class is computed, persisted, and
reviewed**, converted from the repository-quality baseline per the owner's
report-first assignment. Base: `origin/main` @
`1927c8c8c8a4ae72af5be848dea865ce59bd5866`. No code changed; no PR opened.
Research-lane surfaces that live on PR #3 (`research/market-eval-v2` @
`3de017a1`) are marked `[PR #3]` — they are not on main yet.

## Metric hierarchy (the contract this map serves)

| Tier | Question | Metrics | Gate role |
|---|---|---|---|
| 1. Gate | Is the full predictive distribution better? | paired count-RPS (primary) | gate metric for model-family changes |
| 2. Accuracy | Is the point forecast right? | MAE, RMSE, bias | supportive; never gates alone |
| 3. Probability quality | Are the probabilities trustworthy? | log score, calibration, coverage/width, milestone Briers (K>=6/8/10/12) | required before line probabilities |
| 4. Decision quality | Are fair prices/takes sane? | fair-line error, take-rate behavior, boundary calibration | pre-market screen |
| 5. Economic | Does it make money on paper? | ROI, CLV, PnL, Sharpe, drawdown, Calmar, turnover, stake sensitivity | paper-only; evaluated LAST, never a substitute for tiers 1-4 |

A lower MAE/RMSE without better RPS means the mean improved while uncertainty
worsened; better RPS with flat MAE means the distribution, not just its center,
improved. Both views are required before any market-facing claim.

## Lane-by-lane computation/persistence/review map

### BF (workload) lane — B0/B1

| Aspect | Where |
|---|---|
| Computed | research runners on PR #3: `run_b1_ridge_v1.py`, `run_bf_ab_score_cohort.py` lineage; B0 audit via scaffold -> combiner seam |
| Metrics | BF MAE, RMSE, bias; BF-PMF calibration, coverage/width; BF-distribution RPS + log score |
| Persisted | immutable lake run dirs (`bf-lane-v1/b1_run_v1/`), keyed predictions, `metrics.json`, `run_manifest.json` — hashes in Git, outputs NEVER in Git |
| Known limitation | B1 retains B0 shape, integer shifts, 217/4,866 flagged recenter-mass-loss rows (4.5%) — permanently attached to the result |
| Reviewed | Chat 2 independent recomputation from persisted artifacts + reviewer tooling (`scripts/review_verify.py`, PR #6) |

### PA (probability) lane

| Aspect | Where |
|---|---|
| Computed | count-eval-v2 harness `[PR #3]` (`comparison.py`): log loss + Brier on RAW (principal), CAL lane separate (fold-internal calibrator) |
| Population | mixed-role eligible frame, 549,296 PAs (319,714 starter + 229,582 reliever); `pitcher_role` not a feature in any registered candidate |
| Persisted | write-once run dirs: `preds_<fold>__<cand>.parquet`, `metrics.json`, `bootstrap.json`, `run_manifest.json` |
| Status | model-family question CLOSED (LightGBM no detectable advantage; logistic retained) |
| Reviewed | eval-identity hash across candidates; Chat 2 reconciliation |

### Count (distribution) lane

| Aspect | Where |
|---|---|
| Computed | `research/offseason_2026/kcount_combiner.py` (BF PMF x per-PA P(K|PA) -> count PMF); I3b integration runner; count-layer errors reuse persisted `start_metrics_v2` values (`base_h3_rps`, `base_l5_rps`), never recomputed ad hoc |
| Metrics | count-RPS (GATE), count log score, count MAE/RMSE/bias, milestone Briers, calibration |
| Persisted | registered run dirs + card/metrics/manifest per experiment convention |
| Pending | ONE registered end-to-end comparison: B1-recentered PMFs vs frozen I3b/H3-LOG5, same folds/eligibility, paired slate-date bootstrap (2000, seed 20261001, shared draws, null-centered + Holm) — READY-gated |
| Reviewed | preregistration contract; Chat 2 exact-SHA review before the single run |

### Calibration

| Aspect | Where |
|---|---|
| Live | WS1c per-line Platt (`prob_calibration_production.json`), isotonic retired/lineage-only |
| Research | harness CAL lanes (fit within each training fold, applied to that fold's held-out rows; absent lanes recorded absent, never synthesized post-hoc) |
| Monitoring | `production/notebooks/results_calibration_lab.ipynb` (matchup/rest miss pockets) |
| Reviewed | reliability vs sharpness reported separately per the Gneiting-Raftery note (`docs/reference/reports/calibration_sharpness_note_2026-10-15.md`) |

### Line/take lane

| Aspect | Where |
|---|---|
| Computed | `src/Python/market.py` (two-way de-vig, edge, Kelly anchor); `production/odds/odds_board.py` (recommendations); `kpi_policy.json` floors/caps/veto |
| Metrics | edge (juiced multiplicative), fair-line error vs available books, take-rate/selection behavior, boundary calibration |
| Persisted | board `recommendations.parquet` -> ledger via parity-locked polling |
| Reviewed | policy pins (`tests/test_live_stack_pin.py`), board-ledger parity lock |

### Paper-quant (economic) lane — LAST by design

| Aspect | Where |
|---|---|
| Computed | `production/odds/grade_odds_ledger.py` (settle + CLV); `production/ops/market_research/juiced_replay_ledger.py` (#123 measurement), `paper_ladder.py`; research replay lane `score_historical_range.py` -> `join_universe.py` -> `juiced_replay_ledger.py` |
| Metrics | paper ROI, CLV (`clv_pp`, same-book headline), PnL, Sharpe/drawdown/Calmar/turnover, stake sensitivity |
| Persisted | `artifacts/odds_log/ledger.parquet` (generated, ignored); canonical money = `dedupe_ledger_props` |
| Citable numbers | `docs/reference/golden_metrics.md` + its JSON sources — cite, never recompute |
| Reviewed | KPI monitor / PnL+CLV notebooks; champion-challenger protocol gates |

## Evaluation order (binding for any new challenger)

1. Data/identity checks (cohort, strictly-prior construction, joins, leakage
   guards, hashes, row accounting)
2. Workload/BF evaluation (MAE/RMSE/bias, distribution RPS/log score,
   calibration, coverage/width, availability-state slices)
3. Strikeout count evaluation (count-RPS primary, log score, MAE/RMSE/bias,
   threshold Briers, calibration, interval diagnostics)
4. Statistical comparison (paired date-aware bootstrap, CIs, null-centered
   p-values, predeclared multiplicity)
5. Line/take evaluation (fair probabilities vs books, boundary calibration,
   selection behavior, robustness)
6. Quant/betting evaluation (paper-only ROI/CLV/PnL/risk + sensitivity)

This ordering prevents a model from looking profitable off a short betting
sample while its point forecasts or probabilities are biased or miscalibrated.

## Review/discipline layer (cross-cutting)

- **Pre-registration:** contract frozen before any fit/run; deviations recorded,
  never silently absorbed.
- **Exact-SHA review:** Chat 2 reviews published heads only; builder self-check
  is never independent READY.
- **Machine-generated result tables:** results index (PR #8) + run receipts with
  identity blocks; no manual transcription of metric values between runs.
- **Metric separation:** PA, BF/count, line/take, and betting evidence are
  reported separately; no PA/BF result alone promotes a model or implies edge.

## Map disposition

Report-only slice per assignment. Published at exact SHA on branch
`maintenance/quality-baseline-20261016` (second commit; no PR, per the
report-only hold and the PR-concurrency cap). Becomes citable context for the
count-layer registration review and any future model card.
