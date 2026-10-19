# bf-lane-v1 — B1 RIDGE WORKLOAD CHALLENGER REGISTRATION (2026-10-16)

**FREEZE ONLY — NO FIT, NO SCORING, NO REAL-DATA RUN. This file registers ONE
challenger; execution requires separate owner authorization after the
exact-head CI + SELF-CHECK gate (SELF_CHECK_CHAT2.md).**

- Machine-readable registration: `b1_registration.json` (registration hash is
  the sha256 of that file, recorded in MANIFEST.json and reported in the
  session return).
- Reference (B0): the audited BASE empirical BF construction
  (`bf-workload-v1/scripts/build_bf_forecasts.py`, verdict PASS in
  B0_AUDIT.md).

## 1. Challenger identity

`B1_ridge_workload_v1` — ONE chronological Ridge workload challenger against
B0. Grain: (game_pk, side, pitcher) first-pitcher-of-record starts, identical
to the B0 builder grain. Target: realized BF per start. Population: the
registered assessment cohort 2024-07-01..2025-12-31 (7,194 starts; 272 slate
dates). This realizes the count-eval-v2-spec CANDIDATE_MAP stub
`B1_ridge_bf` ("Ridge replacing the BF-PMF-producing model's fit stage, same
folds, emits the identical PMF artifact shape") at start grain.

## 2. Feature set (predeclared, 5 features, all strictly prior)

| # | Feature | Source | Definition |
| --- | --- | --- | --- |
| 1 | `prior_mean_bf` | stored `prior_mean` | mean BF over the pitcher's prior starts in the 2023-01-01-onward pool; null iff prior_n == 0 |
| 2 | `prior_n` | stored `prior_n` | prior start count (the registered list's "prior n" and "prior start count" are this ONE column; declared once, no duplicate feature) |
| 3 | `lg_mean` | stored `lg_mean` | league mean BF over ALL starts strictly before game_date |
| 4 | `rest_days_since_last_start` | derived | (game_date − max prior start game_date of the same pitcher) in days; defined iff prior_n >= 1; uncapped |
| 5 | `season_progression` | derived | game_date ISO day-of-year (deterministic calendar feature, no data dependence) |

All five are available pregame by construction (features 1-3 are the B0
builder's strictly-prior pools, pool-update-after-date verified by the B0
audit; features 4-5 derive only from prior dates / the calendar). NO current
or eventual BF, NO realized lineup, NO outcome-dependent feature availability
enters pregame construction (hard rules, section 8).

## 3. Availability / missingness states (explicit, no imputation)

| State | Definition | Window count | B1 handling |
| --- | --- | --- | --- |
| `own_distribution` | prior_n >= 10 | 6,059 | scored by the Ridge |
| `insufficient_history_league_pool` | 1 <= prior_n <= 9 | 966 | scored by the Ridge — **short prior outings PRESERVED**, never excluded |
| `career_debut_league_pool` | prior_n == 0 (no prior start exists at all; prior_mean + rest_days undefined) | 169 | EXCLUDED from Ridge scored rows (registered exclusion, decided by PRIOR history only, outcome-independent); B1 forecast for these rows = B0 PMF unchanged (no recentering) |
| `failed_join` | cohort start missing from bf_forecasts or start_metrics_v2 realized-BF join | 0 (B0 audit) | would be excluded, reason-coded |
| `unavailable_lineup_starter_inputs` | — | 0, `not_applicable_lineup_free` | B0 and B1 are lineup-free by construction; the category is structurally absent |

Ridge scored rows = 7,194 − 169 = 7,025. No imputation, no missing-indicator
columns, no other exclusions.

## 4. Preprocessing and estimator (frozen, no search)

- StandardScaler fit on **base_train ONLY**, one scaler per fold; career-debut
  rows never enter the scaler (they are excluded before fitting).
- Estimator: `sklearn.linear_model.Ridge(alpha=1.0, fit_intercept=True,
  solver default)`. **alpha = 1.0 registered; NO alpha search, NO
  hyperparameter/feature/window/calibration search of any kind.**
- No calibration stage (no post-hoc calibrator; the PA lane's 60-day
  calibration sub-block is a PA-lane concept and is NOT used by B1).

## 5. Training windows — identical to the PA harness folds

Fold anchors verbatim from
`specs/count-eval-v2-spec/harness/comparison.py` BLOCKS (train_end /
assessment anchors exactly run_ladder.py:60-66), applied at START grain
(base_train = starts with game_date <= train_end, from the same 14,574-row
2023-2025 strictly-prior builder frame; training labels = realized_bf of
training-window starts — past outcomes as labels for past rows, the standard
supervised setup; no assessment-window or later outcome enters any fit):

| Fold | base_train | Assessment window | Cohort starts |
| --- | --- | --- | --- |
| block_2024H2 | 2023-01-01 .. 2024-06-30 | 2024-07-01 .. 2024-12-31 | dev-scored |
| block_2025H1 | 2023-01-01 .. 2024-12-31 | 2025-01-01 .. 2025-06-30 | dev-scored |
| block_2024H1 | 2023-01-01 .. 2023-12-31 | 2024-01-01 .. 2024-06-30 | 0 cohort starts (cohort begins 2024-07-01) — declared empty, not silently skipped |
| confirm_2025H2 | 2023-01-01 .. 2025-06-30 | 2025-07-01 .. 2025-09-28 | **EXCLUDED — NOT SCORED** in the dev run (confirmation requires separate registration) |
| 2026 | — | — | **CLOSED** (no 2026 loads) |

Development evidence = block_2024H2 + block_2025H1 assessment rows only.

## 6. Uncertainty representation (documented construction, NOT a new distributional model)

Per scored row, the B1 predictive distribution is the **B0 BASE empirical BF
PMF recentered on the Ridge predicted mean**, by this exact deterministic
construction:

1. `p37` = stored BASE `pmf37` (B0 arm, unmodified).
2. `p_ext` = `kcount_combiner.bf_pmf_from_37(p37)` — frozen combiner, exact
   support 1..60 (cap 60), overflow redistributed by the frozen
   mean-hazard-31..36 rule.
3. `m0` = `expected_bf(p_ext)`; `m1` = Ridge predicted mean, clipped to
   [1.0, 60.0].
4. `s` = round(m1 − m0), round-half-away-from-zero (deterministic integer
   shift).
5. `p'_ext[n] = p_ext[n − s]` for n = 1..60; mass shifted out of range is
   DROPPED and the result renormalized to sum 1. Registered guard: if the
   dropped mass exceeds 0.01 the row is flagged `recenter_mass_loss_flag`
   and reported — never silently accepted.
6. If s == 0 the row is unchanged.

Support/tail conventions are preserved (extended 1..60 exact support; the
count combiner folds the >= k_max tail into its last bucket), so the B1 arm
is downstream-compatible with the identical integration path. The B1 arm is a
RECENTERING of the audited B0 distribution — a documented construction, not a
new distributional model; no variance model, no shape fit.

## 7. Count-distribution integration + paired RPS evidence

- Integration path identical to the audited lineage (B0_AUDIT.md):
  per-row BF PMF (B0 arm: `bf_pmf_from_37(pmf37)`; B1 arm: the recentered
  `p'_ext`) -> `combine_count` (k_max 24) -> count PMFs -> `count_rps`
  (summed convention) + `count_logscore` + milestone Brier (6/8/10/12).
- **Registered pregame `p_bar`** (identical for BOTH arms, so the paired
  contrast is invariant to it): the frozen scalar shrunk pitcher K rate,
  w=150 log5 form (the kcount-integration I3b arm's prior construction:
  pa-k prior_rates, W=150, pool = completed PAs strictly before game_date
  under the pa-k label convention), rebuilt per start for this cohort and
  hash-recorded at run time. The realized-sequence diagnostic's realized-PA
  `p_bar` is explicitly NOT reused.
- Paired slate-date uncertainty: **2000 resamples, seed 20261001**,
  block-stratified slate-date bootstrap, ONE shared draw stream across arms
  and contrasts (the PA-harness C3.8 convention); predeclared contrast set =
  {`C_b1_ridge_vs_b0_empirical`} on count-RPS, null-centered approximate
  bootstrap test, Holm at family level 0.05; ordinary percentile CIs are
  UNADJUSTED. Per-candidate RPS intervals reported alongside.

## 8. Hard rules (binding on the future execution)

1. **No current/eventual BF** in pregame construction: features 1-5 never
   read the assessed game's BF; verified by the B0 prior-pool recompute for
   the stored columns; derived features use prior dates only.
2. **No realized lineup**: B0/B1 are lineup-free; no lineup, lineup-starter,
   or batter-level input is permitted in B1 pregame construction.
3. **No outcome-dependent feature availability**: the ONLY exclusion
   (career debut, prior_n == 0) is decided by strictly-prior history.
4. **Short prior outings preserved**: rows with 1 <= prior_n <= 9 are scored,
   never excluded; their BF outcomes stay in the pools.
5. **Explicit availability states** per section 3, persisted per row.
6. **No real-data run at registration**: this packet freezes only; any fit
   needs owner authorization and runs write-once with the identity gates.

## 9. Persistence (registered outputs of the eventual authorized run)

Write-once run dir under `MLB-Props-Research\bf-lane-v1\<run_id>\` (run_id =
64-hex of the run config), persisted via the shared
`track_and_verify.py` chain (compare once -> save -> log(MLflow) -> verify
fresh-process), with a sha256 inventory in metrics.json:

- **Forecast-row IDs + as-of timestamps**: (game_pk, side, pitcher) +
  `forecast_as_of = game_date` — the reconstructed deterministic cutoff
  (labelled: NO captured pregame timestamps exist in this 2024-25 lineage;
  cutoff provenance per the pa_ext reviewer verdict).
- **Feature availability/missingness states** per row (section 3 enum) +
  per-row feature values.
- **BF predictive distributions, not merely means**: full 37-cat BASE PMF
  (B0) AND full recentered extended PMF (B1) per scored row.
- **Observed BF** per scored row.
- **Mean bias / MAE / RMSE** of both arms' mean forecasts (per fold + pooled
  dev), with mean-bias sign and magnitude reported.
- **Calibration**: predicted-mean decile reliability (10 quantile bins) +
  milestone exceedance Brier (P(K>=6/8/10/12) vs realized) per arm.
- **Interval coverage/width**: central P10-P90 and P25-P75 from each arm's
  extended PMF; empirical coverage and mean width per fold + pooled.
- **Distributional score**: count-RPS + count-logscore per arm, per fold +
  pooled dev.
- **Count-integration inputs/outputs**: per-row `p_bar` (registered section 7
  construction, hash-recorded) + 24-bucket count PMFs both arms.
- **Paired RPS evidence**: per-date paired draws, contrast delta, null-
  centered 95% CI, p, Holm-adjusted p (2000, seed 20261001, shared stream).
- Per-fold fit-row counts asserted equal where arms share rows (Ridge scored
  rows vs B0 rows differ ONLY by the registered career-debut exclusion,
  reported as a counted difference, never silent).
