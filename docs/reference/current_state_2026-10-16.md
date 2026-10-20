# Current state — research model stack (2026-10-16)

Authoritative current-state summary, provided by the owner 2026-10-16 (Chat 3
transcription). Numbers and definitions here describe the registered
count-eval-v2 research harness and the closed PA model-family question.
**Pointers, not claims to recompute** — cite the registered run JSONs
(`research/offseason_2026/experiments/<batch>/metrics.json` and the MLflow
receipts) for citable values. This page supersedes no evidence; it replaces
stale *narrative* only.

## PA population (precise)

- `pa_table` = 731,347 rows: **all pitchers' completed PAs — starters and relievers.**
- Eligible loaded frame = 549,296 rows over 2023-03-30 → 2025-09-28:
  **319,714 starter PAs + 229,582 reliever PAs.**
- First-pitcher-only restriction was the **older pa-k-baseline prespecification**.
  The current count-eval-v2 harness trains on the **mixed-role eligible frame**.
- `pitcher_role` is loaded as a column but is **not a feature** in any registered candidate.
- Open modeling consideration: downstream K contracts are starter props, so
  mixed-role training may dilute starter-specific signal. The BF lane is
  inherently starter-focused. A role-restricted-training or role-aware-feature
  experiment is a legitimate **future registered batch** — never a silent change.

## Harness mechanics (count-eval-v2, precisely)

**Partitioning** — 4 chronological walk-forward folds. Per fold:
- `base_train` = [2023-01-01, cal_first) — all PAs in this span.
- `calibration` = the 60 PA-bearing days ending at the fold's train_end anchor
  (`cal_last = max game_date <= train_end`, `cal_first = cal_last - 59d`, derived at runtime).
- `assessment` = the registered evaluation window.
- Disjointness asserted by an explicit overlap guard; date-based, so all PAs of
  one game stay in the same partition.

**Predictive eval** — every candidate predicts on **identical** assessment rows
(eval-identity hash asserted equal across candidates). Metrics: log loss + Brier
on RAW (principal); CAL lane separate (sigmoid calibrator fit only on the
calibration sub-block). Pooled dev = **row-weighted mean over all concatenated
dev rows** — never the average of fold means.

**Bootstrap** — 2,000 resamples, seed 20261001. Resampling unit = **slate date
(game_date), whole clusters**: each block contributes its original date count,
rows ride with their date. Statistic = row-weighted ratio (sum of per-row metric
over sampled rows / sampled row count). **One draw stream shared across all
candidates and contrasts** — paired by construction.

**Null-centered tests** — two-sided approximate bootstrap p-values on the 4
predeclared RAW Brier contrasts: `p_j = (1 + #{|e_jb| >= |D_j|}) / (B+1)` where
`e_jb = D*_jb - D_j` (centered errors). Nonparametric; the bootstrap replicate
distribution is the reference (not t/z/F). Holm step-down at family alpha=0.05.
Declared **approximate** (not exact randomization; no finite-sample validity guarantee).

## LightGBM tuning (none — by design)

Fixed hyperparameters frozen in the freeze JSON: `objective=binary, lr=0.05,
num_leaves=31, min_data_in_leaf=100, feature_fraction=1.0, bagging_fraction=1.0,
bagging_freq=0, lambda_l1=0.0, lambda_l2=0.0, seed=20261001, deterministic=true,
force_row_wise=true, num_boost_round=400, early_stopping_rounds=50`, evaluated on
the inner base_train carve-out. **No search, no Optuna, no grid** — the
equal-information test isolates model family, not hyperparameter quality. A
future tuning batch needs its own registered search budget.

## Feature choices

The 8 both-EW features (inherited from the executed overnight-p2 ladder, not
chosen by search): `p_pitcher_prior_w150`, `p_batter_prior_w150`, `lg_rate`,
`n_prior_pitcher`, `n_prior_batter`, `cold_start`, `ew_pitcher`, `ew_batter`.

- **w150 is a fixed-width shrinkage prior**: the pitcher's prior K rate is
  shrunk toward the league rate with weight 150 regardless of actual prior PAs
  (a 30-PA / 0.400 pitcher and a 500-PA pitcher get the same weight).
  `n_prior_pitcher` and `cold_start` carry support information so the *model*
  can learn to weight low-support rows differently, but the *feature
  construction* uses a non-dynamic denominator. EW-90d addresses recency, not
  support-adaptivity.
- Legitimate improvement direction: **support-adaptive priors** (effective
  sample size growing with history) — testable only as a registered feature
  ablation.

## MLflow pattern

Baselines are already imported and reconciled: first-run-v1 (parent + 20
children) and recency-batch-v1 (parent + 12 RAW children). **Execute first,
import after** is the established pattern for the BF lane too; no upfront
logging. Cross-comparison value comes from one MLflow experiment with
consistent metric names + tag conventions (provided by the D-1 wrapper + import
pattern).

## K vs TBF separation (clean by design and by grain)

| Lane | Scores | Metrics |
| --- | --- | --- |
| PA | `P(K\|PA)` on PA rows | log loss / Brier |
| BF | workload distribution of N | MAE / RPS of N |
| Count layer | `P(K=k) = sum_n P(N=n) * P(K=k\|N=n)` | — |
| Market | contract probabilities | de-vig comparison, CLV, ROI |

Metrics never cross lanes. Count-layer errors in the market-eval run were
**reused persisted values** (`base_h3_rps`, `base_l5_rps` from
`start_metrics_v2`), not recomputed from PA. The one meeting point is the
aggregation step (homogeneous `p_bar` vs per-batter Poisson-binomial) — a
registered open question.

## Test sequence (where we are)

| Stage | What | Status |
|---|---|---|
| PA model family | LightGBM vs logistic, equal information | **CLOSED** — no detectable development advantage for LightGBM on the registered estimand |
| B0 reference audit | Verify existing BF forecasts are pregame-valid and reproducible through the combiner seam | Next |
| B1 Ridge challenger | One workload challenger vs B0 | After B0 |
| B2/B3 | LightGBM regression / exit-hazard | Only if B1 shows a reason |
| Aggregation | Ordered Poisson-binomial vs I3b p_bar | After BF layer improves |
| Market re-eval | New PA+count pipeline vs de-vig | After count layer improves |

PA representative going forward: **logistic**. Do not keep tuning
equal-information boosting.

## Multi-class future (parked)

Binary K is correct for now. The adapter contract generalizes (the
`settle_result` / `payout_units` pattern already handles win/lose/push; outs and
hits would add classes), but only after the BF lane is resolved. The harness's
identity/bootstrap/metrics machinery is outcome-agnostic; only the adapter's
target definition and metric set change.

## Learned vs still unknown

**Learned (evidence-backed):**
- Market de-vig probability beats both frozen PMF arms at matched contracts —
  PA probability quality is the binding constraint.
- EW-90d recency features give small, consistent dev-only PA gains; LightGBM
  does not improve on logistic under matched exposure.
- Full BF distribution beats point exposure at count level (I1 - C1 = -0.0116).
- Card-informed average rates beat league-average; ordered heterogeneity adds
  ~nothing at count level.
- Identity/population handling is the recurring defect class — now structurally guarded.

**Still unknown:**
- Whether pitcher EW, batter EW, or both drive the PA gain (EW-only ablation
  adapters exist, not run).
- Whether any nonlinear model helps at PA level with genuinely new features
  (current 8 features are insufficient for trees to shine).
- Whether BF uncertainty can improve (Ridge vs hazard vs empirical residual).
- Whether ordered per-batter aggregation beats homogeneous p_bar at count level.
- Whether the September drift is a training-window issue or structural nonstationarity.
- Whether any PA/count improvement survives the market comparison.

## Architecture diagram

See [`../diagrams/06-count-eval-harness-2026-10-16.md`](../diagrams/06-count-eval-harness-2026-10-16.md).

## Related

- Glossary/lifecycle: [`../../CONTEXT.md`](../../CONTEXT.md)
- Canonical surfaces: [`repo_canonical_map.md`](repo_canonical_map.md)
- Work queue: [`../EXECUTION_BACKLOG.md`](../EXECUTION_BACKLOG.md)
