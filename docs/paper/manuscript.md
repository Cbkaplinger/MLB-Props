# Leakage-Safe Pregame Pitcher Strikeout Projection from Baseball Savant

**A quant ML engineering study of rate modeling, exposure projection, and governed decisioning**

Cameron Kaplinger  
Independent Researcher

*Technical manuscript · Updated Aug 2026*

**Code repository:** [https://github.com/Cbkaplinger/MLB-Props](https://github.com/Cbkaplinger/MLB-Props)

**Acknowledgments.** Baseball Savant / Statcast pitch-level data provided the empirical foundation for this work.

---

## Abstract

This paper presents a leakage-safe **pregame** machine learning pipeline for starting-pitcher strikeout projection from Baseball Savant (Statcast) pitch-level data. The core target is game-level strikeout rate `k_rate = K / PA` for starters who face at least nine batters, using only pregame features. A Polars-first three-level pipeline builds game aggregates, lagged rolling form, and a model-ready training frame under strict chronological validation.

The active production lane uses a **two-model LightGBM blend** across frozen feature sets (`production_sparse72_monotone`, `production_final58_consensus`) with weights `0.60 / 0.40`, plus a Ridge projected-TBF companion [2]. Count projections follow `E[K] = k_rate_hat × TBF_hat`, then convert to line probabilities via binomial/Poisson on projected exposure only [3, 4].

**Statistical caution is the headline.** Trial-adjusted significance testing with the Bailey–López de Prado Deflated Sharpe Ratio [12] yields `DSR = 0.0349` on the audited `n=26` manual lane, with `PSR = 0.9701` against a zero-Sharpe benchmark. At the observed sample size and `N=5161` configuration search breadth, the raw Sharpe is positive but *not* evidence of a durable post-selection edge: the DSR power plan indicates roughly `n≈98` graded bets are needed to reach `DSR > 0.5` and `n≈147` for `DSR > 0.8`. We report performance transparently precisely because it is underpowered; no persistent betting-edge claim is made on the current sample.

**Policy-freeze audit (2026-09-01): FAIL.** The same `n=26` ROI `0.4363` / Sharpe `0.4438` / PnL `+24.17u` window spans slate dates `2026-07-30`–`2026-08-17`, entirely *before* the declared `KING_PROFILE_AUG2026` freeze (`2026-08-21T16:10:00Z`). The live blend was explicitly selected as `best_manual_roi_after_open_calibration_transfer_deduped`. Those decision metrics are therefore **pre-freeze policy-search evidence**, not post-freeze out-of-sample deployment performance, and are demoted from headline claims (full audit: `docs/reference/reports/ssac27_policy_freeze_audit_2026-09-01.md`).

**Post-freeze operational sample (through 2026-08-31):** under the locked dual-ensemble KING floor gate (`passes_floor`, `game_date > 2026-08-21`) the live ledger has **`n=74`** settled tickets with ROI **`−1.55%`**, win rate `48.6%`, and thin-sample CLV mean `+1.59`pp (beat-close share `58.6%` on `n_clv=29`). Side split is severe: overs `n=45` / ROI `−24.6%` vs unders `n=29` / ROI `+29.3%`. This is the honest replacement lane for the demoted 26-bet story — larger, still underpowered, and **not** a validated edge (detail: `docs/reference/reports/postfreeze_king_profile_metrics_2026-09-01.md`). A placebo/null decision-lane control remains required before any edge claim (see §8.2, §8.4).

The main contribution is an end-to-end quant workflow that links leakage-safe modeling, chronological evaluation, and governed decision operations in a reproducible system.

---



## 1. Introduction

Strikeout props are a natural target for pregame modeling: the outcome is well-defined, Statcast supplies rich pitch- and PA-level detail, and the quantity of interest separates into a **rate** component and an **exposure** component. Many published baseball analytics workflows emphasize descriptive leaderboards or postgame attribution. Betting-oriented systems often blur the pregame information set. This work treats the problem as **supervised prediction under a strict pregame constraint**.

The modeling claim is simple and compositional. A leakage-safe estimate of strikeout rate, multiplied by a leakage-safe projection of batters faced, yields expected strikeouts and line probabilities without ever using same-game outcomes as inputs:

<div align="center"><code>k_rate × TBF → E[K] → P(K ≥ L)</code></div>

**Goal.** Estimate a starter’s strikeout rate before first pitch, project how many batters that starter will face, and convert the pair into expected strikeouts and `P(K >= L)` for common prop lines `L`.

**Estimand.** Research metrics use the PA ≥ 9 cohort defined in Section 3.3.

**Figure 1.** Leakage-safe architecture. Raw Statcast pitches are aggregated into game records (Level 1), lagged rolling form (Level 2), and a model-ready training frame (Level 3). A LightGBM strikeout-rate model and a Ridge projected-TBF model combine in a count layer that yields expected strikeouts and line probabilities from projected exposure only.

### 1.1 Related work

**Sabermetric rate-based pitching models.** Fielding Independent Pitching (FIP) and related estimators such as xFIP summarize pitcher skill from strikeouts, walks, hit batsmen, and home runs (or home-run rates normalized by fly-ball environment), reducing dependence on balls in play and defensive context [7, 8]. Those metrics are primarily descriptive or talent-estimation tools at the season or large-sample level. The present work is complementary: it retains FIP/xFIP-style components as *candidate features*, but the prediction target is game-level `k_rate` under an explicit pregame information constraint, not a restatement of FIP as the forecast.

**Season-level baseball projection systems.** Systems such as Marcel [9], PECOTA [10], Steamer, and ZiPS forecast season (or rest-of-season) player rates from weighted recent performance, regression to the mean, aging, and—depending on the system—comparable-player paths. They are useful conceptual baselines for talent estimation, while this manuscript focuses on production pregame decision governance under chronological constraints.

**Chronological evaluation and leakage control.** When targets are ordered in time, randomly reshuffled cross-validation overstates accuracy by allowing future information into training folds [11]. Forecasting practice therefore prefers expanding or rolling windows and features that are known at the forecast origin. This paper treats those constraints as hard engineering rules (shifted rolling windows, prior-season park factors, date-disjoint partitions) and verifies them with tests and audits rather than as an after-the-fact caveat.

**Count models for rate × exposure.** Once a mean rate and an exposure (here, projected batters faced) are specified, Poisson or binomial probabilities are standard for count outcomes [3, 4]. Line probabilities use those trials on *projected* exposure only. A beta-binomial dispersion check collapses to the binomial limit under the frozen mean, consistent with a well-specified mean model absorbing extra-binomial variance [4].

**Governed decisioning and performance evaluation.** Reporting strategies built on small, post-selection samples are vulnerable to overstatement. The Bailey–López de Prado performance-evaluation framework—Deflated and Probabilistic Sharpe Ratios with trial-count adjustment—provides a principled way to deflate observed risk-adjusted returns for the number of configurations searched [12]. This manuscript adopts that framework (§8.2–§8.4) and complements it with market-relative skill diagnostics (Brier/LogLoss skill vs market) and closing-line-value (CLV) as decision-level evidence, consistent with practice standards that separate model accuracy from market edge.

---



## 2. Contributions

1. **Leakage-safe feature architecture.** Same-game outcomes never enter predictors; rolling statistics are shifted; park factors use prior seasons only; chronological splits never divide a calendar date across partitions.
2. **Frozen multi-set rate modeling.** The rate lane is now governed across three frozen feature sets (`sparse72`, `sparse72_monotone`, `final58`) with explicit champion/challenger workflow and artifact lineage.
3. **Dual-layer projection stack.** A weighted LightGBM ensemble for `k_rate_hat`, Ridge for projected TBF, and a count layer on projected exposure produce expected strikeouts and line probabilities.
4. **Quant governance integration.** Open-universe skill ranking, deduped manual replay, isotonic transfer calibration, and board-to-ledger parity checks are wired into the daily production decision path.
5. **Reproducible operations.** Policy profiles, calibration pointers, and model lineage are versioned so retraining, promotion, and daily execution are auditable.

---



## 3. Data and pipeline

Because the stack multiplies rate by exposure, both quantities must be built from the same leakage-safe information set. The pipeline below is the shared foundation for that claim (Figure 1).

### 3.1 Source

Pitch-level regular-season Statcast via Baseball Savant (local parquet cache, seasons 2015–2026 retained for coverage; **model fitting uses 2023–2024 rows**). Season 2022 supplies prior-only park and league context for 2023 boundaries and does not enter training rows. Postseason files are retained but not used in the strikeout stack documented here.

### 3.2 Three levels

**Table 1.** Three-level pipeline outputs.


| Level        | Role                                   | Primary outputs                                                     |
| ------------ | -------------------------------------- | ------------------------------------------------------------------- |
| 1 · Games    | Pitch → starter/batter game aggregates | `pitcher_games`, `batter_games`, `pitch_type_games`, `park_factors` |
| 2 · Rolling  | Leakage-safe lagged form + context     | `pitcher_rolling`, `batter_rolling`                                 |
| 3 · Training | Join lineup + park into model frame    | `pitcher_training`, `batter_training`                               |


Level 1 is the audit surface: denominators, events, and identities are defined once. Level 2 applies rolling and season-to-date windows with an explicit lag so the game being predicted never contributes to its own features. Level 3 assembles opponent-lineup aggregates and prior-season park factors.

Implementation is Polars-first, with automated tests for feature safety, pipeline stages, and the trainer/splitter. Repository paths and artifact names are collected in Appendix A.

### 3.3 Population filter

Default research rows require PA ≥ 9. This is a **postgame** cohort definition for a **pregame** model: it does not leak feature values, but it conditions every reported metric. Population audits show excluded share ≈ **3.5%** (2023–2024). Cutoffs 8–10 change exclusion by about half a percentage point; nine remains the frozen policy.

---



## 4. Leakage methodology

Leakage control is not a preamble to the rate × exposure claim—it is what makes the claim scientifically meaningful. If same-game outcomes contaminate features, both the rate model and the TBF model become postgame reconstructions rather than pregame forecasts.

The following rules are treated as hard constraints:

- Same-game K, PA, Outs, and `k_rate` are labels / evaluation fields only.
- Rolling and season-to-date player statistics are shifted by one game or start.
- Season-to-date windows reset at season boundaries.
- Park factors for season Y use only seasons before Y.
- Opponent lineup aggregates use each batter’s **pregame** form; historical membership is the first nine distinct batters by first PA.
- Train / validation / test splits are chronological; a calendar date lies in exactly one partition.
- Unexpected numeric columns are rejected unless they match approved pregame naming rules.

Verification combines notebook spot checks (first start of season, season boundary resets, manual rolling recomputation) with an automated test suite. Process bugs (for example relocated-park blending; Section 9) were logged with before/after evidence in the research log.

**Evaluation scope.** Development metrics use 2023–2024 chronological partitions and nested folds. Any 2025 reporting is treated as non-selection context rather than a pristine post-freeze holdout.

---



## 5. Feature design

With the information set fixed, feature design is treated as a quant selection problem: keep only pregame signals that survive chronological evaluation and operational governance checks.

### 5.1 Active feature sets

The rate lane is maintained through three frozen sets:

- `production_sparse72` (compact baseline),
- `production_sparse72_monotone` (same sparse spine with monotone constraints),
- `production_final58_consensus` (consensus-pruned compact set).

These sets are evaluated both as individual models and as ensemble members.

### 5.2 Monotone-constraint implementation scope

Monotone constraints are implemented in the LightGBM production lane because that path is hardened in the current training/evaluation stack [1]. XGBoost also supports monotonic constraints, and Aug 2026 parity runs include explicit constrained-vs-unconstrained XGBoost comparisons.

### 5.3 Model selection criteria

Production promotion decisions are driven by:

1. feature-level pruning outcomes on frozen sparse sets,
2. rolling-window sensitivity checks,
3. out-of-sample market-skill governance lanes (open and deduped manual),
4. deployment robustness (calibration transfer and parity checks).

Family ablation serves as a challenger screen, while production promotion is determined in the governance lane.

### 5.4 Empirical-Bayes style shrinkage in features

The production feature pipeline uses empirical-Bayes style shrinkage selectively to stabilize low-sample pregame rates:

- `src/Python/batter_rolling.py`: batter rolling K% shrinkage (`k_rate_std_shrunk`) toward batter prior + league prior with pseudo-PA strength.
- `src/Python/pitcher_rolling.py`: prior-season shrunk pitcher K/PA (`add_prior_season_shrunk_k`) and low-sample pitch-type shrinkage toward prior-date league means.
- `src/Python/pitcher_features.py`: league HR/FB prior smoothing (`lg_hr_fb_prior`) with explicit prior-strength blending.

This gives cold-start and small-sample rows a stable prior-date fallback while preserving leakage safety (no same-game outcomes in predictors).

---



## 6. Models

Feature design supplies the inputs; models convert those inputs into rate and exposure, then into count probabilities.

### 6.1 Strikeout-rate lane

**Table 2.** Active rate-model structure.

| Component | Role |
| --- | --- |
| LightGBM (`sparse72_monotone`) | Ensemble member with monotone constraints |
| LightGBM (`final58`) | Ensemble member |
| Active blend (`0.60 / 0.40`) | Active production scorer (`sparse72_monotone`, `final58`) |

The production decision is not a single-model claim; it is a governed ensemble
choice validated across open-universe and deduped-manual lanes.

**Table 2a.** Current contender `k_rate` MAE (model-family lane, sparse-set run).

Table 2a is a challenger-screen table for single-model error behavior on shared sparse feature sets; it is not the deployment champion table.

| Rank | Model family | Feature set | Mean `k_rate` MAE |
| --- | --- | --- | ---: |
| 1 | ridge | `production_sparse72` | 0.07668 |
| 1 (tie) | ridge | `production_sparse72_monotone` | 0.07668 |
| 3 | lightgbm | `production_sparse72_monotone` | 0.07669 |
| 4 | lightgbm | `production_sparse72` | 0.07707 |
| 5 | histgbr | `production_sparse72` | 0.07721 |

**Table 2b.** Chronological game-level naive baselines (Marcel lane; **not** the Table 2a outer-fold protocol).

| Baseline | Test `k_rate` MAE | n | Notes |
| --- | ---: | ---: | --- |
| Marcel (3/2/1 + EB regress, no age) | 0.08257 | 1413 | `marcel_baseline.py` |
| Prior-season only | 0.08301 | 1413 | same split |
| Train-mean | 0.08538 | 1413 | same split |
| Frozen LightGBM (registry freeze ref.) | ≈0.0787 | — | same test start; not re-fit here |

Delta over Marcel for the freeze reference: ≈ **−0.0039** absolute MAE. Sparse72 ridge **0.07668** (Table 2a) cannot be subtracted from Marcel without fold-aligned preds — different evaluation contract. Source: `docs/reference/reports/ssac27_naive_mae_baseline_2026-09-01.md`.

The current ensemble-sweep ranking artifact does **not** include `k_rate` MAE
columns; it is ranked on decision metrics (ROI/risk/market-skill). Therefore,
ensemble `k_rate` MAE is reported as **not available in that artifact lane**.
Also, family-model tags in this lane reflect a mixed budget (some default configs,
some small inner-fold tuning), so rankings should be read as practical challenger
screens rather than a perfectly equal hyperparameter-budget bakeoff.

Why Ridge can rank first in Table 2a and not be the deployment champion:

1. Table 2a is a **single-model `k_rate` error lane**.
2. Deployment championing is a **full decision lane** (`k_rate × TBF → P(K ≥ L)` with market-skill and risk metrics).
3. A tiny `k_rate` MAE edge does not guarantee better calibrated line probabilities or better realized risk-adjusted return after exposure, pricing, and bet-selection gates.

**Note: Why ensemble over single model (paper/interview short form)**

- **Single model = best point forecaster** in chronological MAE lanes.
- **Ensemble = best deployable decision engine** after calibration + market/risk governance.
- The project selects single-model leaders for challenger tracking and model-quality reference.
- The project selects deployment champions on decision metrics (skill vs market, ROI, Sharpe/Sortino, drawdown, CLV behavior).
- Therefore, “best MAE model” and “best deployed profile” can differ without contradiction.

### 6.2 Projected batters faced (TBF)

Rate alone is not a strikeout count. The second factor is projected batters faced: same-game PA is used only as a historical exposure oracle for training and evaluation, never as a predictor. Predictors include rest, lagged PA / Outs / Pitches, home/park/lineup K context, and thin team bullpen L1–L3d pitch/pitcher-use lookbacks (**24** features).

**Frozen choice:** Ridge with the thin bullpen feature set (coefficients persisted for reproducible scoring).

### 6.3 Count layer

The count layer is where rate and exposure become the paper’s target quantities, following the standard mean × exposure construction for count probabilities [3, 4]:

<div align="center"><code>E[K] = k_rate_hat × TBF_hat</code></div>
P(K ≥ L) via Binomial / Poisson with n = round(TBF_hat)

Same-game PA never enters prop probabilities.

Notation used throughout Sections 6–8 is: model probability (`p_model`), de-vig market probability (`p_market`), edge (`p_model − p_market`), expected strikeouts (`Ê[K]`), and CLV in probability points (`CLV_pp`).

The production evaluation emphasis is now decision-lane quality (market-skill, replay ROI/risk path, and deployment robustness) rather than legacy internal MAE tables alone.

---



## 7. Ablations and feature-set freeze

The ablation framework now has two jobs: (a) quantify single-model sensitivity, and (b) provide candidate inputs for the ensemble governance lane.

### 7.1 Current protocol

- Outer chronology: anchored walk-forward windows.
- Inner chronology: model/feature tuning only inside training spans.
- Final rank surface: open-universe skill first, then deduped one-opportunity manual replay, then deployment checks.

### 7.2 Current takeaway

Current decisions are made on compact frozen sets (`sparse72_monotone`, `final58`) and their weighted ensemble behavior.

### 7.3 XGBoost monotone in the promotion workflow

XGBoost monotonic constraints were evaluated in follow-up parity runs. The active promotion workflow remains centered on the currently deployed LightGBM monotone stack because it carries the complete production artifact and governance contract.

1. the production monotone pathway (constraint mapping, validation, and artifact lineage) was already hardened around the LightGBM implementation,
2. the sparse-set challenger sweep prioritized chrono-safe comparability and decision-lane governance checks over expanding multiple monotone implementations at once,
3. adding XGBoost-monotone as a promoted lane would require its own constraint-sign audit and equal governance artifact contract before fair promotion.

The evidence claim is: **multiple model families were tested** on shared sparse datasets and chronological splits, and monotone behavior was checked in both LightGBM and XGBoost challenger lanes.

### 7.4 Aug 2026 follow-up parity checks (targeted reviewer questions)

To reduce ambiguity, a focused parity sweep was added after the manuscript rewrite:

1. enable XGBoost monotone constraints in the sparse-set family ablation runner,
2. run base-budget and tuned-small-budget comparisons on the same sparse sets and chronological folds,
3. bridge the MAE lane to decision-lane metrics in a separate governance replay comparison.

Key findings from the added artifact runs:

- **Ablation (base budget):** XGBoost unconstrained (`expected_K` MAE `1.8451`) and XGBoost monotone (`1.8511`) both trailed LightGBM and Ridge in this sparse-lane setup.
- **Ablation (tuned-small):** best XGBoost variants remained behind (`~1.8242` unconstrained, `~1.8352` monotone), while Ridge remained the MAE leader and LightGBM stayed closer to the top cluster.
- **Decision-lane bridge:** high MAE rank did not map one-to-one to best market/risk profile; best governance rows in the added replay comparisons were model-family dependent and changed with tuning budget, reinforcing lane separation.

These checks convert prior process rationale into direct evidence: XGBoost monotone was tested as a challenger, but did not clear the sparse-lane promotion bar in this cycle.


---



## 8. Full-stack evaluation

Component metrics are necessary but incomplete. Once rate and TBF are frozen, the object that must be judged is the full composition:

<div align="center"><code>k_rate × TBF → E[K] → P(K ≥ L)</code></div>

**Table 3.** Full-stack evaluation gates and current production results.


| Evaluation gate | Result |
| --- | --- |
| Active deployment blend (frozen `2026-08-21`) | `0.60 sparse72_monotone / 0.40 final58` |
| Policy-search ROI (`n=26`, pre-freeze; **not OOS**) | `0.4363` (95% CI `[0.0337, 0.8072]`) |
| Policy-search PnL (same lane; **not OOS**) | `+24.17u` (`1u = 50 USD`) (95% CI `[+1.85u, +45.45u]`) |
| Policy-search Sharpe (same lane; **not OOS**) | `0.4438` (95% CI `[0.0431, 0.9997]`) |
| Policy-search Sortino (same lane; **not OOS**) | `0.4277` (95% CI `[0.0459, 0.7866]`) |
| Policy-search Calmar (same lane; **not OOS**) | `2.2903` |
| Policy-search max drawdown (same lane; **not OOS**) | `0.1905` |
| Market-skill deltas (search window) | `+0.2069` Brier skill vs market, `+0.1551` LogLoss skill vs market |
| Probability quality (search-window profile) | Brier `0.2090`, LogLoss `0.6087`, ECE `0.0639`, MCE `0.1353` — *pre-freeze 26-bet manual search lane, post-isotonic-transfer fit, `n=26`* |
| Execution controls | Board-to-ledger parity lock, quality gates, policy profile freeze `KING_PROFILE_AUG2026` (`frozen_utc=2026-08-21T16:10:00Z`) |

*Bootstrap 95% CIs (10,000 resamples) on the decision metrics are the pinned values in `artifacts/odds_log/quant_honesty_aug21_summary.json`; full intervals including the date-block bootstrap are reported in §8.2. Calmar has no interval in that artifact and is shown as a point estimate. **Policy-freeze audit 2026-09-01:** slate dates for this lane are `2026-07-30`–`2026-08-17` (all before freeze); ROI/Sharpe/PnL are policy-search diagnostics only (`docs/reference/reports/ssac27_policy_freeze_audit_2026-09-01.md`).*

Calibration is summarized by expected calibration and scoring diagnostics [5, 6]. On the pre-freeze search window the profile reports ECE `0.0639`, MCE `0.1353`, and positive market-skill deltas versus market baseline; these remain search-window diagnostics, not post-freeze proof of edge.

### 8.1 Metric hierarchy used in this manuscript

- `k_rate` MAE: single-model rate accuracy lane.
- `expected_K` MAE: full-stack point-forecast lane (`k_rate_hat × TBF_hat`).
- Brier/LogLoss skill vs market and ROI/risk metrics: deployment-governance lane.

Each lane answers a different question; winners are not interchangeable across lanes.

### 8.2 Backtest uncertainty and multiple-testing correction (pre-freeze 26-bet policy-search lane)

The audited manual lane contains `n=26` graded recommendations (`top3`, floor `0.12`) with slate dates `2026-07-30`–`2026-08-17`. The declared production freeze `KING_PROFILE_AUG2026` is `2026-08-21T16:10:00Z`, and `production/ops/live_krate_ensemble.json` records selection rule `best_manual_roi_after_open_calibration_transfer_deduped`. **Policy-freeze audit 2026-09-01: FAIL** — every bet in this lane is pre-freeze, so ROI/Sharpe/PnL here are policy-search evidence, not post-freeze OOS evaluation (`docs/reference/reports/ssac27_policy_freeze_audit_2026-09-01.md`). Uncertainty and selection effects are still reported explicitly because the search window is small and was used to choose the blend.

Point estimates below are the authoritative values from the replay artifact `artifacts/odds_log/open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.json`; the 95% CI bounds below are the pinned values in `artifacts/odds_log/quant_honesty_aug21_summary.json` (bootstrap `bootstrap_iid_ci` and `bootstrap_block_by_date_ci`) and are shown for transparency. Note that the *point estimates* in Table 3 / §8.2 are taken from the replay artifact, while `quant_honesty_aug21_summary.json` still carries the pre-correction Sharpe/max-DD/Calmar values for the same lane; the CI bounds themselves are carried by that artifact. All corrected point estimates sit within their stated intervals.

Bootstrap percentile intervals (10,000 resamples):

- ROI `0.4363` with 95% CI `[0.0337, 0.8072]`
- Sharpe `0.4438` with 95% CI `[0.0431, 0.9997]`
- Sortino `0.4277` with 95% CI `[0.0459, 0.7866]`
- PnL `+24.17u` (`1u = 50 USD`) with 95% CI `[+1.85u, +45.45u]`

Date-block bootstrap (resampling by slate date to reduce same-day dependence assumptions) yields similarly wide intervals:

- ROI 95% CI `[0.0084, 0.7739]`
- Sharpe 95% CI `[0.0885, 0.9296]`
- Sortino 95% CI `[0.0946, 0.7457]`

Multiple-testing-aware Sharpe diagnostics (Bailey/López de Prado style):

- Probabilistic Sharpe Ratio (PSR, benchmark Sharpe `0`): `0.9701`
- Deflated Sharpe Ratio (DSR, trial-adjusted using `N=5161` tested configurations): `0.0349`

Interpretation: raw Sharpe is positive, but trial-adjusted significance remains weak at the current sample size and search breadth. Deployment claims are therefore framed as governed operational evidence rather than conclusive statistical dominance. **DSR here diagnoses selection breadth on the policy-search configuration space (blend×floor), not post-freeze OOS edge** (enumeration: `docs/reference/reports/ssac27_n5161_enumeration_2026-09-01.md`).

> **DSR provenance (updated 2026-09-01).** `PSR`, `DSR`, `sigma_sr`, `sr_star`, the
> `N=5161` trial count, and the §8.4 power targets come from
> `artifacts/odds_log/quant_honesty_aug21_summary.json` (`n_trials=5161`;
> `sr_star=0.8544`). Method: Bailey & López de Prado (2014), *The Deflated Sharpe
> Ratio*, JPM [12]. **What 5161 is:** eligible **blend × edge-floor** configurations from
> the Aug-21 deduped ensemble sweep — 3 feature-set lanes on a weight-0.05 simplex
> (231 blends) × floors `0.005…0.12` step `0.005` (24) = 5544 grid rows, minus 383 with
> `n_bets < 25` → **5161** (`ensemble_sweep_ranked_ensemble_full_aug21_deduped.csv`;
> metadata `ensemble_sweep_ensemble_full_aug21_deduped.json`; producer
> `production/ops/run_model_ensemble_sweep.py`). **What it is not:** Optuna HP trials or
> model-family architecture search. Full write-up:
> `docs/reference/reports/ssac27_n5161_enumeration_2026-09-01.md`.

### 8.2.1 Post-freeze KING-floor lane (honest OOS replacement, through 2026-08-31)

After the FAIL freeze audit, the only epistemically valid money lane is **post-freeze** under the locked profile. Extracted from the deduped settled ledger with `game_date > 2026-08-21` and `passes_floor == True` (live dual-ensemble gate; stake &gt; 0):

| Lane | n | ROI | Win rate | CLV mean (pp) | CLV &gt;0 (n) | Span |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Post-freeze KING floor | 74 | −0.0155 | 0.486 | +0.0159 | 0.586 (29) | 2026-08-22–08-31 |
| · overs only | 45 | −0.2464 | 0.378 | +0.0058 | 0.632 (19) | same |
| · unders only | 29 | +0.2933 | 0.655 | +0.0351 | 0.500 (10) | same |

Source: `docs/reference/reports/postfreeze_king_profile_metrics_2026-09-01.md`. Interpretation: sample size is improved vs the demoted n=26 search lane but still below DSR power targets; aggregate ROI is slightly negative; side asymmetry is first-order. **Do not treat this table as a claimed edge.**

### 8.2.2 Null / placebo decision lanes (post-freeze)

Matched nulls vs the locked KING floor (`0.12`) on post-freeze settled opportunities (`game_date > 2026-08-21`), produced by `production/ops/run_null_decision_lane.py`:

| Lane | n | ROI | Win rate | CLV mean (pp) | CLV &gt;0 |
| --- | ---: | ---: | ---: | ---: | ---: |
| KING `passes_floor` | 74 | −0.0155 | 0.486 | +0.0159 | 0.586 |
| Random-prob (matched n/floor) | 74 | −0.0917 | 0.459 | +0.0108 | 0.464 |
| Naive-prior (matched n/floor) | 74 | −0.0562 | 0.473 | +0.0112 | 0.474 |
| Shuffle-edge on KING set | 56 | −0.0256 | 0.482 | +0.0203 | 0.600 |

Report: `docs/reference/reports/ssac27_null_decision_lane_2026-09-01.md`. Random/naive may impute stake on non-bet ledger candidates and are **null references**, not production policies. KING is less red than the matched nulls and posts a higher beat-close share than random/naive, but absolute ROI remains negative and margins are not DSR-grade — consistent with the demoted n=26 / weak DSR posture. **No decision-layer edge claim.** These nulls are **illustrative diagnostics only** (stake imputation + crude priors); they are not a validated placebo control for abstract claims.

**Interim ops (2026-09-01; live veto promoted same day).** Post-freeze side×line bleed is first-order (esp. 4.5 overs). Shadow counterfactuals on real KING stakes (`production/ops/run_shadow_asymmetric_policy.py`) showed vetoing 4.5 overs moving the post-freeze floor set from ROI ≈ −1.55% (n=74) to ≈ +8.3% (n=56); raising the over floor to 0.16 (shadow) was also green on that window. Brier skill vs market is **negative on overs** and **positive on unders**. The **4.5-over hard veto** (plus soft probation on 2.5/3.5 overs) was **promoted to live** on 2026-09-01 (`docs/reference/reports/live_policy_promotion_2026-09-01.md`); broader asym-floor live promote and calib/champion swaps remain gated. This is **risk control**, not a claimed durable edge. Live work-state: `docs/EXECUTION_BACKLOG.md`.

### 8.3 Slippage sensitivity (fixed 26-bet policy-search set)

To test execution fragility, adverse fill haircuts were applied to the same 26-bet audited set (no re-selection of bets).

| Probability haircut (pp) | ROI | PnL (u, `1u=50 USD`) | Sharpe | Sortino |
| ---: | ---: | ---: | ---: | ---: |
| 0.0 | 0.4363 | 24.17 | 0.4352 | 0.4277 |
| 0.5 | 0.4313 | 23.89 | 0.4301 | 0.4206 |
| 1.0 | 0.4263 | 23.62 | 0.4250 | 0.4135 |
| 2.0 | 0.4163 | 23.06 | 0.4148 | 0.3997 |

The profile remains positive under this small haircut grid, but risk-adjusted metrics compress as expected.

> **Source + freshness note (2026-08-27).** All five rows come verbatim from
> `artifacts/odds_log/slippage_sensitivity_top3_floor12_aug21.csv`. A prior revision
> of this table carried a Sharpe column extrapolated from the deployment profile's
> `0.4438`; the authoritative slippage artifact instead reports a self-consistent
> Sharpe series beginning at `0.4352`. That base-row value (`0.4352`) differs from the
> deployment-profile Sharpe `0.4438` reported in Table 3 / §8.2 because the
> `quant_honesty` and `slippage` artifacts were generated with the **pre-correction**
> Sharpe/max-DD/Calmar point estimates, while the deployment-profile figure comes from
> the re-audited `open_top3_transfer...replay` JSON. The adjudicated authoritative
> deployment Sharpe is `0.4438`; the slippage series is the internally consistent
> source for §8.3 and should be re-seeded/rebuilt alongside the quant-honesty artifact
> when the deployment-profile point estimates are next refreshed.

### 8.4 Sample-size plan from DSR power targets

Holding observed return-shape moments and trial count fixed, the DSR power check implies approximate sample targets of:

- `n ≈ 98` bets to reach `DSR > 0.5`,
- `n ≈ 147` bets to reach `DSR > 0.8`.

At the current recommendation density (about one recommendation per slate day), this corresponds to roughly `72` to `121` additional graded recommendations beyond the current audited set.

For clarity of interpretation: Sharpe is mean excess return per unit total
volatility, Sortino is mean excess return per unit downside volatility, and ROI
is return over stake in the same evaluation lane.

Metric-purpose rule used in this manuscript:

- MAE/RMSE/R² claims come from chronological model-evaluation lanes (2023–2024 walk-forward/CV and 2025 holdout protocol).
- Open 2025–2026 and manual replay lanes are used for market/decision metrics (Brier/LogLoss skill vs market, ROI, Sharpe, Sortino, drawdown, CLV), not MAE promotion claims.

**Figure 2.** Reliability diagram for count-layer line probabilities. Points near the diagonal indicate well-calibrated bins. Mean ECE ≈ 0.024 with no post-hoc recalibration — **pre-deployment walk-forward 2024 diagnostic only** (`artifacts/model_quality/phase11c_calibration/`, `n=4607` rows across 3 chronological windows, `ece_mean=0.0243`, `ece_max=0.0403`; raw probabilities, no isotonic transfer applied).

> **Lane clarification (ECE 0.024 vs 0.0639).** The two ECE values cited in this
> manuscript are *not* comparable and must not be conflated:
> - **ECE ≈ 0.024** (here and in Fig. 2) is the broad **pre-deployment walk-forward
>   2024 diagnostic** across `n=4607` raw predictions / 3 windows — it is an internal
>   calibration-quality check of the frozen stack, not a deployed-lane claim.
> - **ECE 0.0639 / MCE 0.1353** (Table 3 / A.5) is the **deployed 26-bet audited manual
>   lane** (`open_top3_transfer...replay` JSON), computed on only `n=26` graded bets on
>   the *post-isotonic-transfer* integrated profile. Small-sample realization on a
>   different, far smaller population — not evidence of a calibration regression.
> Both numbers are artifact-backed; the apparent 2.6× gap is a population/lane artifact,
> not a defect.

These checks are confirmatory: they did not uncover large unused gains on the frozen stack’s internal metrics.

---

### 8.5 Production governance state (Aug 2026)

Current live operations use a compact three-lane governance model:

1. **Skill lane (open universe):** rank candidates on market-skill metrics across broad opportunity sets.
2. **Decision lane (manual, deduped):** enforce one-opportunity-one-bet fairness and evaluate realized risk/return behavior.
3. **Deployment lane:** transfer calibration and push the winning blend to live runtime with parity controls.

Key active controls:

- profile lock: `KING_PROFILE_AUG2026`,
- edge floor: `0.12` with line-aware side floors,
- isotonic probability calibration in production,
- fractional Kelly criterion is used as the sizing heuristic (reported here in `50 USD` units),
- segmented line/price/maturity correction overlays,
- board-to-ledger parity reconciliation before governance status.

Failure-mode behavior in operations: if parity or quality gates fail, the promotion path is fail-closed (no automatic profile promotion) until reconciliation and gate re-clearance.

**Current artifact-backed winners**

- **Open-universe deduped sweep top profile:** `0.05 sparse72 / 0.45 sparse72_monotone / 0.50 final58`  
  ROI `0.6612`, Sharpe `0.9468`, Sortino `0.6954`, skill deltas `+0.0825` Brier / `+0.0645` LogLoss.
- **Active deployment champion (deduped transfer lane):** `0.60 sparse72_monotone / 0.40 final58`  
  ROI `0.4363`, PnL `+24.17u` (`1u = 50 USD`), Sharpe `0.4438`, Sortino `0.4277`, max drawdown `0.1905`, skill deltas `+0.2069` Brier / `+0.1551` LogLoss.

Interpretation note: this profile generated `26` recommendations in the audited manual lane, approximately one recommendation per slate day over the sampled period.

Execution note: reported replay metrics assume fills at recorded replay prices; explicit slippage/transaction-cost haircuts should be applied in subsequent robustness updates.

This split keeps winner selection explicit: open-universe breadth ranking and
deployment robustness are related but distinct optimization targets.

**Larger settled-threshold view (operational diagnostic; mixed pre/post-freeze).**  
To calibrate floor behavior on a broader operations sample, settled positive-stake rows from `2026-07-31` forward were bucketed by policy floor. This window **includes both pre-freeze and post-freeze days** and is an execution-policy diagnostic (volume/ROI tradeoff), **not** a pure post-freeze OOS claim and not a replacement for either the demoted 26-bet search lane or the §8.2.1 KING-floor post-freeze lane.

| Policy | Bets (`n`) | ROI |
| --- | ---: | ---: |
| Single floor `0.08` | `277` | `0.0182` |
| Single floor `0.10` | `248` | `0.0331` |
| Single floor `0.12` | `222` | `0.0710` |
| Single floor `0.14` | `175` | `0.0482` |
| Single floor `0.16` | `127` | `0.0859` |
| Dual floor (`over=0.10`, `under=0.08`) | `263` | `0.0281` |

> **Freshness note (2026-09-01).** The counts above are the *post-dedupe* operational bucketing of settled positive-stake rows from `2026-07-31` forward, drawn from the regenerable `artifacts/odds_log/runtime_floor_calibration.csv` (regenerated with the morning monitoring snapshot). Earlier manuscript revisions reported inflated raw-row counts (`307/285/265/209/159/299`), then an Aug-27 deduped snapshot (`233/214/193/153/112/225`); the live deduped ledger now yields the `n` above. Because these counts roll forward as the ledger settles, this table is a point-in-time operational snapshot — not a frozen evaluation claim.

Interpretation: higher floors still cut volume; ROI is not strictly monotone in floor (the `0.14` bucket dips vs `0.12`/`0.16` in this window). The active `0.12` deployment floor remains the current balance point between throughput and edge quality.

Working hypothesis for edge persistence: strikeout-prop markets are thinner and adjust less uniformly than major side/total markets, so leakage-safe pitcher-form and lineup-context features can remain underpriced at some times of day. This is a practical market-microstructure hypothesis, not a proof of persistent inefficiency.

**Figure 3.** Cumulative PnL overlay for `top3` vs `top1` at floor `0.12` (`1u = 50 USD`). **Lane:** Aug-21 transfer picks / policy-search window (not post-freeze OOS). **n:** top3 = 26, top1 = 27. **Date span:** `2026-07-30`–`2026-08-17` on the pinned picks CSV. **Generator:** `docs/paper/make_figures.py` → `fig_equity_top3_vs_top1()` from `artifacts/odds_log/open_top3_transfer_bestfloor_picks_aug21_deduped_top3_from_dedupedsweep.csv` (`pnl_u = stake × rpd / 50`). Bootstrap CIs for the top3 lane’s ROI/Sharpe are in `quant_honesty_aug21_summary.json` (§8.2); the figure itself is a path overlay, not a CI ribbon. Headline Sharpe/DD/Calmar for this lane follow the authoritative replay JSON (0.4438 / 0.1905 / 2.2903); honesty/slippage artifacts retain pre-correction baseline Sharpe 0.4352 by intentional freeze — see `docs/reference/reports/ssac27_honesty_slippage_lineage_2026-09-01.md`.

![Equity curve overlay](figures/equity_curve_top3_vs_top1_aug21.png)

---

### 8.6 Interpretability and model-driver evidence (artifact-backed)

Interpretability is handled here as **stable directional evidence** from leakage-safe ablations and challenger parity runs, rather than as one-off global importance ranks.

Primary evidence used in this manuscript:

- nested family/window ablation records (`docs/research/historical-step-findings-summary.md` and linked `artifacts/feature_research/*ablation*` outputs),
- sparse-lane model-family parity artifacts (`artifacts/model_quality/sparse72_model_family_ablation/aug21_parity_base/` and `aug21_parity_tuned_small/`),
- governance-lane bridge artifacts (`artifacts/odds_log/model_family_governance_compare_aug21_governance_base.csv` and `..._tuned_small.csv`).

Driver-level interpretation used for interviews and operational review:

- **Point-forecast lane:** Ridge remains the best single-model MAE challenger (`expected_K` MAE about `1.7621`, `k_rate` MAE about `0.07668`) on the sparse-lane parity contract.
- **Monotone-rate lane:** LightGBM monotone remains in the near-frontier cluster (for example `expected_K` MAE about `1.7689` in base-budget parity) while preserving the production monotone policy path.
- **Challenger variation:** XGBoost was evaluated in both unconstrained and monotone forms; both trailed current sparse-lane leaders in this cycle (tuned-small examples: about `1.8242` unconstrained and `1.8352` monotone `expected_K` MAE).
- **Deployment implication:** MAE rank and deployment rank diverge by design; governance winners are selected on market-skill and risk metrics, not MAE alone.

### 8.7 Start-level case narratives (audited 26-bet lane)

The narrative cases in this section are **explicitly illustrative and anecdotal**: `n=3` individual starts are presented to convey decision behavior, not to support any statistical claim. No directional inference for the lane's edge should be drawn from them; the aggregate evidence is governed by §8.2–§8.4.

The audited lane (`top3`, floor `0.12`) contains both high-edge confirmations and misses. The purpose of these examples is to show **decision behavior under uncertainty**, not to re-argue MAE.

- **Right-call example (high edge, under):** 2026-07-31 `Paul Skenes` under `7.5` (`edge=0.2742`) settled as a win (`rpd=+1.10`, positive CLV).
- **Right-call example (high edge, over):** 2026-07-30 `Roki Sasaki` over `5.5` (`edge=0.2293`) settled as a win (`rpd=+1.00`).
- **Wrong-call example (high edge, under):** 2026-08-15 `Ian Seymour` under `6.5` (`edge=0.2292`) settled as a loss (`rpd=-1.00`) despite positive pre-bet edge and positive CLV.

These cases illustrate the practical pattern seen across the lane: edge/CLV signal can be directionally useful while individual outcomes remain noisy at start level.

### 8.8 Operational benchmark snapshot (local workstation)

To make the MLE-facing reliability claims auditable, this manuscript records concrete runtime slices from the parity and governance workflow used in the Aug 2026 checkpoint:

- sparse-lane base parity run (`ablate_sparse72_model_families.py`): about `234s`,
- sparse-lane tuned-small parity run: about `797s`,
- governance bridge run (`compare_model_family_governance.py`, base): about `120s`,
- governance bridge run (tuned-small): about `235s`.

End-to-end parity-plus-governance refresh for that checkpoint was about **23 minutes** wall-clock on the local workstation.

Operational controls remain fail-closed: if parity/quality gates fail, promotion does not proceed until reconciliation clears (`production/ops/build_validation_ops_report.py`, `production/ops/build_policy_governance_report.py`).

---



## 9. Limitations

**Population scope.** Reported core metrics use the PA ≥ 9 cohort and therefore describe conventional-length starts.

**Game-level variance ceiling.** Even with modern features and ensemble blending, pitcher-game outcomes retain substantial irreducible variance.

**Exogenous signal coverage.** Some high-impact context channels (weather micro-effects, travel fatigue, umpire framing) remain outside the frozen production feature set.

**Statistical confidence under small audited lane.** The active manual lane (`n=26`) yields wide intervals on ROI and risk ratios, and trial-adjusted Sharpe significance is limited at current sample size.

**Interpretability breadth.** This version includes artifact-backed family/parity evidence and start-level narratives, but it does not yet include a full SHAP/conditional-permutation atlas on every frozen deployment profile.

**Operational stress breadth.** Runtime slices are now documented for the parity/governance checkpoint workflow, but continuous production SLO tracking (for example multi-month p95 refresh latency and rollback-time distribution) is still open.

---



## 10. Conclusion

This work delivers a leakage-safe pregame strikeout system that now behaves like a quant production stack: compact frozen feature sets, ensemble rate scoring, TBF exposure modeling, calibrated count probabilities, and governed execution controls.

The core engineering result is not just lower error versus simple baselines; it is a reproducible operating workflow where model selection, policy thresholds, and daily execution are linked through auditable artifacts and chronological validation.

Quant-honesty checks in this version show positive raw performance, but deflated-Sharpe evidence remains low (`DSR=0.0349`), so additional live sample accumulation is required before claiming durable statistical edge.

---



## Reproducibility statement

Code for the leakage-safe pipeline, nested selection utilities, trainers, and count layer lives in the public repository: [https://github.com/Cbkaplinger/MLB-Props](https://github.com/Cbkaplinger/MLB-Props) (Python ≥ 3.11; Polars for feature construction; scikit-learn and LightGBM for models; pytest for automated leakage and pipeline checks). Experiments reported here were run on a local Windows workstation with a project-local virtual environment. Primary data are pitch-level Statcast exports accessed via Baseball Savant (commonly retrieved with community tooling such as pybaseball); users should respect Baseball Savant / MLB terms of use for redistribution and commercial use. Generated local artifacts (model binaries, fold summaries, and governance outputs) are reproducible from the documented runners but are not required to read the manuscript’s tables and figures.

At the Aug 2026 freeze checkpoint, operator and research notebook surfaces were
re-executed end-to-end after policy and calibration updates, with successful
execution recorded in the notebook execution artifacts under `artifacts/odds_log/`.

### Data Availability

Statcast data can be retrieved per-user via public tools (e.g., pybaseball) rather than redistributing bulk parquet, which helps sidestep Baseball Savant / MLB terms-of-use concerns around bulk redistribution.

---



<div style="page-break-before: always;"></div>

## Appendix A. Repository map

Internal repository names, paths, and frozen-artifact identifiers are collected here so the body text can stay narrative. They do not change any metric reported above.
Repository cleanup governance and keep/hold/delete audit protocol are maintained in `docs/reference/repo_canonical_map.md` and `docs/reference/repo_waste_sweep_checklist.md`, with the latest pass report at `docs/reference/reports/repo_quality_passthrough/2026-08-21.md`.

### A.1 Feature-set aliases

**Table A1.** Feature-set aliases used in code.


| Alias | Size | Description |
| --- | --- | --- |
| `production_sparse72` | 72 | Compact sparse baseline |
| `production_sparse72_monotone` | 72 | Sparse baseline with monotone constraints |
| `production_final58_consensus` | 58 | Consensus-pruned compact challenger |
| `ridge_vif` | 73 | Linear-model research companion |
| `workload_context_bullpen` | 24 | Frozen TBF feature set (thin bullpen) |




### A.2 Frozen model artifacts

Frozen model stems, model sidecars, and artifact hashes are maintained in the repository model card and the locked comparison-pack manifest:

- `docs/reference/model-card.md`
- `docs/reference/reports/model_comparison_pack/2026-08-21.manifest.json`

Generated research outputs under `artifacts/` are local/reproducible and typically gitignored.

### A.3 Documentation and code map

**Table A3.** Documentation and code map.


| Topic                                        | Location                                                           |
| -------------------------------------------- | ------------------------------------------------------------------ |
| Governance metric lanes                      | `docs/reference/governance_metric_stack.md`                        |
| Model card                                   | `docs/reference/model-card.md`                                     |
| Canonical production runbook                 | `production/README.md`, `production/RUNBOOK.md`                    |
| Feature/pipeline implementation notes        | `docs/reference/dev-notes.md`, `src/Python/`                       |
| Rate training                                | `models/Strikeout-Model/train.py`                                  |
| TBF training                                 | `models/TBF-Model/train.py`                                        |
| Count layer findings                         | `docs/research/count_layer_findings.md`                            |
| Walk-forward quality gates                   | `docs/research/phase11_model_quality_gates.md`                     |
| Live assembly plan                           | `docs/reference/live_assembly_plan.md`                             |
| Research chronology (historical log)         | `docs/research/PAPER_NOTES.md`                                     |


---

### A.4 Quant-governance artifacts (Aug 2026 expansion)

Raw governance artifact filenames are maintained in the repository documentation instead of duplicated in the manuscript body:

- `production/README.md`
- `docs/reference/model-card.md`
- `docs/reference/reports/model_comparison_pack/2026-08-21.md`
- `docs/reference/reports/model_comparison_pack/2026-08-21.manifest.json`

**Three-lane methodology now used in governance:**

1. **Skill lane (open universe):** rank candidates on market-skill metrics over large opportunity sets.
2. **Decision lane (manual, deduped):** enforce one-opportunity-one-bet fairness and evaluate realized quant path metrics.
3. **Deployment lane (transfer + runtime):** transfer calibration from open panel to manual lane, then deploy via config-driven live scorer.

### A.5 Active production profile snapshot

**Table A5.** Current deployment profile from
`open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.json`.

| Metric | Value |
| --- | --- |
| Blend weights | `0.60 sparse72_monotone / 0.40 final58` |
| Edge floor | `0.12` |
| Bets | `26` |
| Stake | `55.40u` (`1u = 50 USD`) |
| PnL | `+24.17u` (`1u = 50 USD`) |
| ROI | `0.4363` |
| Sharpe / Sortino / Calmar | `0.4438` / `0.4277` / `2.2903` |
| Max drawdown | `0.1905` |
| CLV mean (pp) | `0.0252` |
| Positive CLV share | `0.70` |
| Brier / LogLoss | `0.2090` / `0.6087` — deployed 26-bet manual lane, post-isotonic-transfer, `n=26` |
| ECE / MCE | `0.0639` / `0.1353` — deployed 26-bet manual lane, post-isotonic-transfer, `n=26` |
| Market skill deltas | `+0.2069` Brier / `+0.1551` LogLoss |

*Bootstrap 95% CIs: ROI `[0.0337, 0.8072]`, Sharpe `[0.0431, 0.9997]`, Sortino `[0.0459, 0.7866]`, PnL `[+1.85u, +45.45u]` (10,000-resample percentile, pinned in `quant_honesty_aug21_summary.json`; date-block variant in §8.2). Note: `quant_honesty_aug21_summary.json` still carries pre-correction Sharpe/DD/Calmar point estimates for this lane; they are superseded by the values above, which come from the deduped replay artifact named at the head of this table.*

**Consistency note on ablation tables.**  
`k_rate` MAE contender comparisons come from sparse-set ablation artifacts,
including the parity snapshots at
`artifacts/model_quality/sparse72_model_family_ablation/aug21_parity_base/ablation_summary_ranked.csv`
and
`artifacts/model_quality/sparse72_model_family_ablation/aug21_parity_tuned_small/ablation_summary_ranked.csv`.
Deployment-king tables come from deduped replay/transfer artifacts and are
ranked on decision metrics, not `k_rate` MAE.

---



## References

1. Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q., and Liu, T.-Y. LightGBM: A highly efficient gradient boosting decision tree. In *Advances in Neural Information Processing Systems (NeurIPS)*, 2017.
2. Hoerl, A. E., and Kennard, R. W. Ridge regression: Biased estimation for nonorthogonal problems. *Technometrics*, 12(1):55–67, 1970.
3. Cameron, A. C., and Trivedi, P. K. *Regression Analysis of Count Data*. Cambridge University Press, 2nd edition, 2013.
4. Hilbe, J. M. *Negative Binomial Regression*. Cambridge University Press, 2nd edition, 2011. (Also discusses overdispersion relative to the Poisson/binomial mean–variance relationship; beta-binomial used here as a related overdispersion check.)
5. Naeini, M. P., Cooper, G. F., and Hauskrecht, M. Obtaining well calibrated probabilities using Bayesian binning. In *Proceedings of the AAAI Conference on Artificial Intelligence*, 2015.
6. Guo, C., Pleiss, G., Sun, Y., and Weinberger, K. Q. On calibration of modern neural networks. In *Proceedings of the 34th International Conference on Machine Learning (ICML)*, 2017.
7. Tango, T. M., Lichtman, M. G., and Dolphin, A. E. *The Book: Playing the Percentages in Baseball*. Potomac Books, 2007. (FIP lineage and defense-independent pitching intuition.)
8. Slowinski, P. xFIP. FanGraphs Library / glossary documentation. URL: [https://library.fangraphs.com/pitching/xfip/](https://library.fangraphs.com/pitching/xfip/) (accessed 2026-07-28). (xFIP replaces HR with expected HR via fly-ball rate × league HR/FB.)
9. Tango, T. M. Marcel the Monkey Forecasting System. Tangotiger / Hardball Times documentation of the minimal season projection baseline (weighted recent seasons, regression to the mean, age adjustment). URL: [https://www.tangotiger.net/marcel/](https://www.tangotiger.net/marcel/) (accessed 2026-07-28).
10. Silver, N. Introducing PECOTA. In Huckabay, G., Kahrl, C., Pease, D., et al. (Eds.), *Baseball Prospectus 2003*. Brassey’s, 2003, pp. 507–514.
11. Bergmeir, C., Hyndman, R. J., and Koo, B. A note on the validity of cross-validation for evaluating autoregressive time series prediction. *Computational Statistics & Data Analysis*, 120:70–83, 2018.
12. Bailey, D. H., and López de Prado, M. The Deflated Sharpe Ratio: correcting for selection bias, backtest overfitting and non-normality. *The Journal of Portfolio Management*, 40(5):94–107, 2014.

