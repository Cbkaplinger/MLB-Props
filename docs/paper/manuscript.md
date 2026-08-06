# Leakage-Safe Pregame Pitcher Strikeout Projection from Baseball Savant

**A modeling study of rate estimation, batters-faced exposure, and count probabilities**

Cameron Kaplinger  
Independent Researcher

*Technical manuscript · July 2026*

**Acknowledgments.** Baseball Savant / Statcast pitch-level data provided the empirical foundation for this work.

---

## Abstract

This paper presents a leakage-safe machine learning pipeline for **pregame** starting-pitcher strikeout projection from Baseball Savant (Statcast) pitch-level data. The target is game-level strikeout rate krate = K / PA for pitchers who ultimately face at least nine batters, using only pregame features. A three-level Polars pipeline builds game aggregates, lagged rolling form, and a training frame; nested chronological cross-validation freezes a **180**-feature LightGBM [1] rate model as the primary rate result. Ridge [2] is a linear sanity check in rate screens and the production projected-TBF companion. Strikeout counts use E[K] = k̂rate × TBF̂ with binomial/Poisson line probabilities [3, 4] on **projected** exposure—never same-game PA. On a 2023–2024 chronological test, frozen rate MAE / RMSE / R² ≈ **0.0787 / 0.0987 / 0.147**, beating a Marcel-lite [9] season-talent baseline (MAE ≈ 0.0826) and a train-mean floor (MAE ≈ 0.0854) on the same partition. Walk-forward expected-K MAE ≈ **1.78**; mean line ECE [5, 6] ≈ **0.024** without recalibration. Leave-family-out screens retain opponent lineup as the only family with both-fold, within-fold bootstrap support; the primary contribution is leakage-safe engineering and nested evaluation around that stack.

---



## 1. Introduction

Strikeout props are a natural target for pregame modeling: the outcome is well-defined, Statcast supplies rich pitch- and PA-level detail, and the quantity of interest separates into a **rate** component and an **exposure** component. Many published baseball analytics workflows emphasize descriptive leaderboards or postgame attribution. Betting-oriented systems often blur the pregame information set. This work treats the problem as **supervised prediction under a strict pregame constraint**.

The modeling claim is simple and compositional. A leakage-safe estimate of strikeout rate, multiplied by a leakage-safe projection of batters faced, yields expected strikeouts and line probabilities without ever using same-game outcomes as inputs:

krate × TBF → E[K] → P(K ≥ L)

**Goal.** Estimate a starter’s strikeout rate before first pitch, project how many batters that starter will face, and convert the pair into expected strikeouts and P(K ≥ L) for common prop lines L.

**Non-goals.** In-game (live) betting and de-vig staking mechanics beyond what is needed to report closing-line value are out of scope; this manuscript is primarily a **modeling** paper. Section 8.5 reports an exploratory, pre-registered closing-line pilot as a secondary, clearly-labeled extension — its result is **inconclusive** as of this writing (sample below the pre-registered minimum) and should not be read as a claim of market edge.

**Estimand.** Research metrics use the PA ≥ 9 cohort defined in Section 3.3.

**Figure 1.** Leakage-safe architecture. Raw Statcast pitches are aggregated into game records (Level 1), lagged rolling form (Level 2), and a model-ready training frame (Level 3). A LightGBM strikeout-rate model and a Ridge projected-TBF model combine in a count layer that yields expected strikeouts and line probabilities from projected exposure only.

### 1.1 Related work

**Sabermetric rate-based pitching models.** Fielding Independent Pitching (FIP) and related estimators such as xFIP summarize pitcher skill from strikeouts, walks, hit batsmen, and home runs (or home-run rates normalized by fly-ball environment), reducing dependence on balls in play and defensive context [7, 8]. Those metrics are primarily descriptive or talent-estimation tools at the season or large-sample level. The present work is complementary: it retains FIP/xFIP-style components as *candidate features*, but the prediction target is game-level krate under an explicit pregame information constraint, not a restatement of FIP as the forecast.

**Season-level baseball projection systems.** Systems such as Marcel [9], PECOTA [10], Steamer, and ZiPS forecast season (or rest-of-season) player rates from weighted recent performance, regression to the mean, aging, and—depending on the system—comparable-player paths. They are the natural external baselines for *talent* estimation. This manuscript scores a **Marcel-lite** game-level krate baseline (Section 6.1)—prior-season weighted K/PA with league-mean regression, without an age curve—on the same chronological test as the frozen LightGBM model. It does not re-implement PECOTA/Steamer/ZiPS.

**Chronological evaluation and leakage control.** When targets are ordered in time, randomly reshuffled cross-validation overstates accuracy by allowing future information into training folds [11]. Forecasting practice therefore prefers expanding or rolling windows and features that are known at the forecast origin. This paper treats those constraints as hard engineering rules (shifted rolling windows, prior-season park factors, date-disjoint partitions) and verifies them with tests and audits rather than as an after-the-fact caveat.

**Count models for rate × exposure.** Once a mean rate and an exposure (here, projected batters faced) are specified, Poisson or binomial probabilities are standard for count outcomes [3, 4]. Line probabilities use those trials on *projected* exposure only. A beta-binomial dispersion check collapses to the binomial limit under the frozen mean, consistent with a well-specified mean model absorbing extra-binomial variance [4].

---



## 2. Contributions

1. **Leakage-safe feature architecture.** Same-game outcomes never enter predictors; rolling statistics are shifted; park factors use prior seasons only; chronological splits never divide a calendar date across partitions.
2. **Nested selection into a frozen feature set.** Feature-family and window decisions are chosen on inner chronological folds that lie wholly inside each training window, then evaluated on a later held-out period. The production LightGBM feature set is frozen at **184** features (Step 10 P1 spine of 180 plus four opposing-lineup discipline nominees).
3. **Dual-model strikeout stack.** Unweighted LightGBM for krate; Ridge for projected TBF; binomial count layer on projected exposure. Chronological test clears a Marcel-lite talent floor (Table 3b).
4. **Process evidence, including negative results.** PA-weighting, linear binomial / beta-binomial rate arms, nested LightGBM hyperparameter search, and several expanded feature families did not clear promotion bars—documented rather than buried.

What this paper does **not** claim: large accuracy lifts, feature-family effects beyond what Table 6 and the within-fold bootstrap support, or a resolved market-edge finding — Section 8.5's live pilot is explicitly reported as statistically inconclusive at current sample size, not a positive result. Absolute game-level R² remains limited (Section 9).

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

Default research rows require PA ≥ 9. This is a **postgame** cohort definition for a **pregame** model: it does not leak feature values, but it conditions every reported metric. Population audits show excluded share ≈ **3.5%** (2023–2024). Cutoffs 8–10 change exclusion by about half a percentage point without a sharp elbow; nine remains the frozen policy.

---



## 4. Leakage methodology

Leakage control is not a preamble to the rate × exposure claim—it is what makes the claim scientifically meaningful. If same-game outcomes contaminate features, both the rate model and the TBF model become postgame reconstructions rather than pregame forecasts.

The following rules are treated as hard constraints:

- Same-game K, PA, Outs, and krate are labels / evaluation fields only.
- Rolling and season-to-date player statistics are shifted by one game or start.
- Season-to-date windows reset at season boundaries.
- Park factors for season Y use only seasons before Y.
- Opponent lineup aggregates use each batter’s **pregame** form; historical membership is the first nine distinct batters by first PA.
- Train / validation / test splits are chronological; a calendar date lies in exactly one partition.
- Unexpected numeric columns are rejected unless they match approved pregame naming rules.

Verification includes notebook spot checks (first start of season, season boundary resets, manual rolling recomputation) and an automated test suite. Process bugs (e.g., relocated-park blending; Section 9) were logged with before/after evidence in the research log.

**Evaluation honesty.** Early baselines consulted 2025. That season is retained as historical context only. It is **not** a pristine final holdout for the frozen stack. Development metrics use 2023–2024 chronological partitions and nested folds.

---



## 5. Feature design

With the information set fixed, the next question is which pregame signals belong in the rate model that feeds expected strikeouts. Feature design here is deliberately conservative: candidates must be available before first pitch, and promotion requires nested chronological evidence—not descriptive plausibility alone.

### 5.1 Families (conceptual)

Production features fall into families such as:

- pitcher rates (K%, Whiff%, SwStr%, chase, …) over rolling and season-to-date windows;
- pitch physics / usage / mechanics means;
- FIP / xFIP-style components [7, 8] with leakage-safe league priors;
- expected-contact summaries;
- opponent lineup aggregates;
- park and game context (home/away, …).

Expanded research candidates (two-start arsenal summaries, count-state, BIP/BABIP, arm angle, SIERA, run-expectancy value, additional batter discipline/quality) were built and screened; **none cleared nested promotion** into the frozen LightGBM set.

### 5.2 Stabilization and reliability

Denominator-aware stabilization curves estimate when rates become repeatable enough to justify short windows. These studies inform **window hypotheses**; they do not alone change the production feature set. Promotion requires nested chronological evaluation on held-out periods.

### 5.3 Correlation and VIF

Pearson / Spearman diagnostics and VIF cluster reduction support a separate **Ridge** research feature set of **73** features (after dropping a collinear five-start xFIP window). LightGBM does **not** use VIF as a prune rule: tree models tolerate correlated inputs differently. Dual feature sets—one for trees, one for linear models—are intentional.

### 5.4 Window policy

Default generation retains multiple mean windows (including a last-start mean after midseason work). Nested screens supported thinning overlapping mean windows for physics / usage / mechanics / FIP families (keep three- and five-start means; drop the ten-start mean) and a targeted last-start swap for five physics stems. A later LightGBM-primary screen promoted four opposing-lineup discipline rates. The frozen production size is **184**, built from a prior **180**-feature P1 spine (itself reduced from a **185**-feature mean-window thin of an earlier **248**-feature allow-list).

---



## 6. Models

Feature design supplies the inputs; the models convert those inputs into the two factors of the paper’s identity—strikeout rate and projected exposure—and then into count probabilities.

### 6.1 Strikeout rate

**Table 2.** Candidate models for game-level strikeout rate.


| Model                     | Role                                      |
| ------------------------- | ----------------------------------------- |
| Mean baseline             | Sanity floor                              |
| Ridge                     | Linear sanity check (secondary)           |
| **LightGBM (unweighted)** | **Frozen production rate model (primary)**|


Figure 2 compares Mean, Ridge, and LightGBM chronological test error on the earlier **248**-feature date-disjoint screen (Appendix B). LightGBM achieves the lowest MAE and RMSE among the three; the frozen production model later locks a **184**-feature LightGBM stack with test MAE / RMSE / R² ≈ **0.0780 / 0.0982 / 0.156** (prior Step-10 180-feature gate ≈ 0.0787 / 0.0987 / 0.147).

**Figure 2.** Chronological test MAE and RMSE on krate for Mean, Ridge, and LightGBM under the 248-feature date-disjoint screen (Appendix B). Lower is better. The production frozen 184-feature LightGBM model’s test MAE is 0.0780, distinct from the 248-feature screen shown here.

Likelihood comparisons on nested 2023–2024 folds showed that PA sample-weighting did not beat unweighted game-level MAE for LightGBM or Ridge. An L2 binomial GLM and a two-stage beta-binomial challenger [3, 4] did not overturn unweighted LightGBM. With the frozen mean model, estimated concentration κ hits the binomial limit. **Decision:** keep unweighted LightGBM as the rate backbone.

**Table 3.** Frozen chronological evaluation for the production LightGBM rate model (2023–2024 fit; test from 2024-08-06).


| Partition  | MAE        | RMSE       | R²        |
| ---------- | ---------- | ---------- | --------- |
| Validation | 0.0764     | 0.0966     | 0.151     |
| Test       | **0.0787** | **0.0987** | **0.147** |


On the earlier 248-feature chronological screen (Appendix B), LightGBM reduces MAE from **0.0854** (mean baseline) to **0.0783** (~**8%** relative).

**Target transform check.** Tree splits are invariant to monotonic transforms of *input* features, so this check transforms only the target: refit the same chronological LightGBM protocol with a logit(krate) label, inverse-transform predictions to rate space before scoring, and compare to the untransformed target (Table 3a). Both fits use the same train/validation/test split and identical early stopping (patience 200 rounds on chronological validation L2).

**Table 3a.** Logit-target vs untransformed krate (same chronological split; early stopping).


| Target | Test MAE | Test RMSE | Test R² |
| ------ | -------- | --------- | ------- |
| Untransformed krate | 0.0787 | 0.0987 | 0.147 |
| Logit(krate), inverse to rate | 0.0807 | 0.1032 | 0.067 |


The logit target does not help (MAE rises by ~0.002) and is not adopted into the frozen pipeline.

**External talent baseline (Marcel-lite).** The same chronological test is scored against a Tangotiger-style Marcel [9] K/PA projection: weights **3/2/1** on seasons Y−1…Y−3, **100 PA** of league-mean regression, **no age adjustment** (birthdates are absent from the project identity map), using only prior seasons. Rookies with no history receive the prior-year league mean (Table 3b).

**Table 3b.** Chronological test krate error vs external / naive baselines (test from 2024-08-06; n = 1413).


| Predictor                       | Test MAE   | Test RMSE  | Test R²   |
| ------------------------------- | ---------- | ---------- | --------- |
| Train-mean constant             | 0.0854     | 0.1070     | −0.001    |
| Prior-season K/PA (regressed)   | 0.0830     | 0.1038     | 0.056     |
| Marcel-lite (3/2/1, no age)     | 0.0826     | 0.1034     | 0.064     |
| **Frozen LightGBM (180 feat.)** | **0.0787** | **0.0987** | **0.147** |


LightGBM beats Marcel-lite by about **0.0039** MAE (~**5%** relative) and the train-mean floor by about **0.0067** MAE (~**8%** relative), roughly doubling R² versus Marcel-lite. Runner: `models/Strikeout-Model/research/marcel_baseline.py`.

**Table 3c.** Natural MAE variation across pitchers and periods.


| Dimension | Statistic | Value |
| --------- | --------- | ----- |
| Per-pitcher MAE on chronological test (frozen LightGBM; ≥3 starts; n = 188 pitchers) | SD of pitcher-level MAE | 0.0250 |
| 2024 H1 MAE (production LightGBM; train 2023 only; Section 7 bounds) | Point MAE | 0.0776 |
| 2024 H2 MAE (same model / training as H1) | Point MAE | 0.0775 |
| H1–H2 period spread | \|MAE_H1 − MAE_H2\| | 0.0001 |


Relative to pitcher-to-pitcher MAE dispersion (SD ≈ 0.025), the LightGBM–Marcel and LightGBM–mean gaps are small (~⅙–¼ of that SD); relative to the H1–H2 period spread under shared 2023 training (~0.0001), those gaps are large. Runner: `models/Strikeout-Model/research/section61_checks.py`.

A nested LightGBM hyperparameter search did not beat freeze defaults on the held-out evaluation periods; defaults already sit near a local optimum under this protocol.

### 6.2 Projected batters faced (TBF)

Rate alone is not a strikeout count. The second factor is projected batters faced: same-game PA is used only as a historical exposure oracle for training and evaluation, never as a predictor. Predictors include rest, lagged PA / Outs / Pitches, home/park/lineup K context, and thin team bullpen L1–L3d pitch/pitcher-use lookbacks (**24** features).

**Table 4.** Projected-TBF contenders on chronological test (MAE primary).


| Contender                                       | Test MAE  | Test RMSE | R²        |
| ----------------------------------------------- | --------- | --------- | --------- |
| **Ridge + thin bullpen**                        | **2.490** | **3.279** | **0.162** |
| Ridge + context only                            | 2.494     | 3.279     | 0.162     |
| Rich bullpen / Poisson / Elastic Net / LightGBM | ≥ 2.49    | —         | ≤ 0.16    |


**Frozen choice:** Ridge with the thin bullpen feature set (coefficients persisted for reproducible scoring). Moderate R² reflects high starter-PA noise (SD ≈ 3.6), not an empty feature set.

### 6.3 Count layer

The count layer is where rate and exposure become the paper’s target quantities, following the standard mean × exposure construction for count probabilities [3, 4]:

Ê[K] = k̂rate × TBF̂  
P(K ≥ L) via Binomial / Poisson with n = round(TBF̂)

Same-game PA never enters prop probabilities.

**Table 5.** Expected strikeouts vs actual K on chronological test (from 2024-08-06), by exposure choice.


| Exposure               | MAE       | RMSE      | R²        |
| ---------------------- | --------- | --------- | --------- |
| **Projected TBF**      | **1.790** | **2.213** | **0.168** |
| Lagged 5-start mean PA | 1.802     | 2.229     | 0.156     |
| Train-mean PA          | 1.822     | 2.252     | 0.138     |


Projected TBF beats simple exposure baselines. Line Brier scores on the test partition are roughly **0.12–0.22** depending on line (3.5–7.5). Beta-binomial dispersion again collapses to the binomial limit under the frozen mean [4].

---



## 7. Ablations and feature-set freeze

The preceding sections define a candidate stack. Ablation evidence then asks which feature families move held-out rate error for the model that enters E[K] = k̂rate × TBF̂, and which cuts can be made without harming that error—subject to the thin two-fold design in Section 7.1.

### 7.1 Protocol

Held-out evaluation periods are 2024 H1 after training on 2023, and 2024 H2 after training through 2024 H1—**two outer chronological folds**. Inner chronological folds lie wholly inside each training window. Selection minimizes mean inner MAE; the later period is used only for evaluation. Automated tests enforce containment and date disjointness.

Because a confidence interval across two fold means is nearly meaningless, uncertainty is estimated **within** each outer validation set: a paired bootstrap over games (B = 2000) of ΔMAE = MAEdrop − MAEfull, yielding a 95% percentile interval per fold (Table 6b). Runner: `models/Strikeout-Model/research/ablation_bootstrap.py`.

### 7.2 Leave-family-out (248-feature screen)

Held-out ΔMAE vs the full model (positive = dropping the family **hurt**) is shown per outer fold and as a two-fold mean in Table 6 and Figure 3. Fold labels: **H1** = 2024 H1 after 2023 training; **H2** = 2024 H2 after training through 2024 H1.

**Table 6.** Leave-family-out ablation (248-feature screen): ΔMAE by outer fold.


| Configuration                  | LGBM H1  | LGBM H2  | LGBM mean    | Ridge H1 | Ridge H2 | Ridge mean   |
| ------------------------------ | -------- | -------- | ------------ | -------- | -------- | ------------ |
| Drop opponent lineup           | +0.00238 | +0.00270 | **+0.00254** | +0.00212 | +0.00250 | **+0.00231** |
| Drop rolling (keep STD/static) | +0.00298 | −0.00048 | +0.00125     | −0.01171 | −0.00025 | **−0.00598** |
| Drop pitch physics             | +0.00078 | +0.00026 | +0.00052     | −0.00508 | −0.00026 | −0.00267     |
| Drop park                      | +0.00015 | +0.00038 | +0.00027     | +0.00018 | +0.00019 | +0.00018     |
| Drop context                   | +0.00030 | +0.00014 | +0.00022     | +0.00008 | +0.00015 | +0.00012     |
| Drop usage                     | +0.00053 | −0.00002 | +0.00025     | −0.00045 | −0.00062 | −0.00054     |


**Table 6b.** Within-fold paired bootstrap 95% intervals for ΔMAE (B = 2000). ★ = interval excludes zero.


| Configuration                  | LGBM H1 CI          | LGBM H2 CI          | Ridge H1 CI         | Ridge H2 CI         |
| ------------------------------ | ------------------- | ------------------- | ------------------- | ------------------- |
| Drop opponent lineup           | [+0.0013, +0.0034]★ | [+0.0016, +0.0038]★ | [+0.0013, +0.0029]★ | [+0.0018, +0.0032]★ |
| Drop rolling (keep STD/static) | [+0.0014, +0.0045]★ | [−0.0017, +0.0008]  | [−0.0137, −0.0096]★ | [−0.0013, +0.0008]  |
| Drop pitch physics             | [−0.0002, +0.0017]  | [−0.0006, +0.0013]  | [−0.0064, −0.0037]★ | [−0.0011, +0.0005]  |
| Drop park                      | [−0.0005, +0.0008]  | [−0.0002, +0.0010]  | [−0.0002, +0.0005]  | [−0.0001, +0.0005]  |
| Drop context                   | [−0.0003, +0.0009]  | [−0.0004, +0.0007]  | [−0.0003, +0.0004]  | [−0.0002, +0.0005]  |
| Drop usage                     | [−0.0001, +0.0011]  | [−0.0006, +0.0006]  | [−0.0012, +0.0003]  | [−0.0011, −0.0002]★ |


**Figure 3.** Leave-family-out mean ΔMAE for LightGBM and Ridge with whiskers spanning the two outer folds (H1–H2). Table 6 remains authoritative for point estimates; Table 6b for within-fold uncertainty.

**Interpretation.** **Opponent lineup** is the only configuration whose ΔMAE is positive with a bootstrap interval excluding zero on **both** folds for **both** models—sufficient to retain the family. **LightGBM rolling** hurts on H1 (CI excludes zero) but is consistent with zero on H2 (sign flip in the point estimate); the two-fold mean (+0.00125) is therefore not a stable keep signal. **Ridge** benefits from dropping overlapping rolling windows on H1 (large negative ΔMAE, CI excludes zero); H2 is near zero—hence the thinner VIF-reduced Ridge companion. The H1/H2 magnitude gap for Ridge’s rolling-window effect is not yet explained (collinearity shift, a specific game stretch, or a real seasonal pattern are all plausible) and is noted here as unresolved rather than settled by the VIF-reduced companion set. Park / context / usage intervals almost all cover zero. Keep lineup; do not narrate the remaining families as resolved lifts.

### 7.3 Keep/drop on the thinned 185-feature set

After mean-window thinning, a greedy family prune with a strict rule—MAE must improve on **both** held-out periods—dropped **zero** families. A chronological comparison of the “pruned” variant against the 185-feature set was identical. Further surgery on that set was noise-scale under the same two-fold design.

### 7.4 Feature-set timeline

The production path compressed an earlier **248**-feature allow-list to a **185**-feature mean-window thin, then to a **180**-feature P1 physics spine, then to the current **184**-feature set via four opposing-lineup discipline nominees. Comparing the last-start P1 swap against the 185-feature predecessor showed small rate and expected-K improvements (k-rate MAE ≈ 0.07842 vs 0.07863; expected-K MAE ≈ 1.769 vs 1.773). The discipline lift further improved nested and 2025 confirmation k-rate MAE under a LightGBM-primary gate. Named feature-set aliases used in the repository are listed in Appendix A.

**Table 7.** Feature-set timeline (sizes and roles).


| Feature set (description) | Size    | Role                                                  |
| ------------------------- | ------- | ----------------------------------------------------- |
| Pre-thin allow-list       | 248     | Comparison baseline                                   |
| Mean-window thin          | 185     | Intermediate freeze                                   |
| **Production (current)**  | **180** | **Current** (185 + five-stem last-start physics swap) |
| Ridge VIF companion       | 73      | Linear-model research set                             |


---



## 8. Full-stack evaluation

Component metrics are necessary but incomplete. Once rate and TBF are frozen, the object that must be judged is the full composition that the paper claims to deliver:

krate × TBF → E[K] → P(K ≥ L)

**Table 8.** Full-stack evaluation gates and results.


| Evaluation gate             | Result                                                                                                          |
| --------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Estimator tuning            | Keep baseline LightGBM defaults; Ridge α tuned and persisted                                                    |
| Walk-forward stack backtest | Mean expected-K MAE ≈ **1.778** across three expanding 2024 windows (σ ≈ 0.036; chronological reference ≈ 1.79) |
| Calibration                 | Mean ECE ≈ **0.024** pre-recalibration; production now applies a post-hoc **Platt** map on `p_over_*` (chrono walk-forward CV selection vs. isotonic, mean ΔECE ≈ −0.008; raw probabilities retained alongside calibrated). Calibrator is fit on 2024 walk-forward OOS predictions and has not yet been refit on 2026 conditions — see Section 8.5. |


**Table 8a.** Walk-forward expected-K MAE by window with paired bootstrap 95% intervals (B = 2000 games within window).


| Window | Expected-K MAE | 95% CI |
| ------ | -------------- | ------ |
| 2024 Apr–May | 1.738 | [1.672, 1.804] |
| 2024 Jun–Jul | 1.826 | [1.758, 1.888] |
| 2024 Aug–Sep | 1.772 | [1.706, 1.838] |


All three window intervals overlap; the mid-season point estimate is highest, but the bootstrap intervals do not support a clear seasonal drift beyond sampling noise. Runner: `models/Strikeout-Model/research/walkforward_bootstrap.py`.

Calibration is summarized by expected calibration error (ECE) [5, 6]. Figure 4 shows a reliability diagram for the count-layer probabilities: empirical event frequency versus predicted probability. Mean ECE ≈ **0.024** without recalibration under chronological evaluation.

**Figure 4.** Reliability diagram for count-layer line probabilities. Points near the diagonal indicate well-calibrated bins; mean ECE ≈ 0.024 with no post-hoc recalibration.

These checks are confirmatory: they did not uncover large unused gains on the frozen stack’s internal metrics.

---

### 8.5 Live market validation (exploratory pilot, inconclusive)

Sections 6–8 evaluate the stack against historical outcomes only. This subsection reports a secondary, clearly-labeled extension: can the frozen stack's `P(K ≥ L)` generate positive **closing-line value (CLV)** against a live, liquid sportsbook market? This is a harder and different test than chronological backtesting — the closing line is the market's own best available estimate after all information (including late-breaking lineup/weather/bullpen news) is priced in, so beating it consistently is evidence of genuine pricing skill rather than a backtest artifact.

**Mechanics.** Each morning, the frozen stack scores that day's slate; calibrated probabilities are matched against live DraftKings/FanDuel over/under quotes. Bets are logged to a paper ledger only when model edge (`p_model − p_market`, de-vigged) clears a fixed **8% floor**, sized via quarter-Kelly anchored so that a bet exactly at the floor at −110 is defined as 1 unit. Once each book's line closes, closing-line value is recorded as `CLV_pp = p_market(close) − p_market(bet time)` on the bet side; realized outcomes are settled from box-score strikeout totals.

**Pre-registered gate.** Following standard practice for a live pilot that could otherwise be p-hacked by peeking, the acceptance criterion was fixed *before* evaluating results (`docs/reference/market_clv_gates.md`): a minimum of **n ≥ 100** props with recorded CLV, and a bootstrap 95% CI on mean CLV that excludes zero, before any PASS/FAIL judgment is drawn. Below that sample size the result is reported as **building_sample**, not evidence either way.

**Result as of this writing: inconclusive.** At n≈85–90 CLV samples — below the pre-registered n=100 threshold — mean CLV is directionally positive (≈+0.7 percentage points, pooled and BET-only cohorts) but the bootstrap CI still straddles zero. **This is explicitly not a positive result; it is an underpowered one.** The honest reading is "encouraging but undecided," and the gate is designed precisely so that this sample size cannot be reported as a pass. An edge-percentile cut shows a similar pattern — realized ROI is strongest in the highest-edge decile and weak-to-negative in a middle band — but per-bin n is single digits to low teens, too small to separate signal from variance.

**Caveats specific to this pilot.** (1) The Platt calibrator applied to `p_over_*` is fit on 2024 walk-forward out-of-sample predictions (Section 6.3/8) and has not been refit against 2025–2026 conditions; any live-market miscalibration specific to the current season would not yet be corrected. (2) The pilot uses paper money, not real capital, so it cannot speak to execution risk (line movement between decision and bet, book limits, or liquidity). (3) The sample spans a single week of one season — nowhere near enough for a seasonal-drift claim even setting the CLV gate aside.

This subsection will be updated with the gate's resolved verdict (PASS / FAIL / INCONCLUSIVE) once n ≥ 100 is reached; readers consulting an earlier version of this manuscript should treat any live-market claim as provisional until that update.

---



## 9. Limitations

**Population and estimand.** Reported metrics describe conventional-length starts (PA ≥ 9), not all announced starters. Roughly **3.5%** of first-pitcher appearances in 2023–2024 fall below that cutoff.

**Predictive power.** Rate-model test R² ≈ **0.147** and TBF R² ≈ **0.162**: most game-level variance remains unexplained; that ceiling is the binding constraint on how strongly the stack should be sold.

**Ablation design.** Only two outer chronological folds exist. Within-fold paired bootstrap (Table 6b) addresses game-sampling noise inside each fold; it does **not** replace a multi-season outer design. Families other than lineup lack stable both-fold support.

**Park-factor contamination.** Neutral-site and international series are not filtered from team-keyed park factors. Verified special-event games in 2023–2024 are on the order of **~10 games** against **~2,430** regular-season games per year (**~0.2%**). Dilution is small relative to prior-season PA but not zeroed; relocated parks (e.g., Rays 2025 Steinbrenner vs Tropicana, since fixed with an override) can matter more than that sparse share.

**Evaluation risk.** Early baselines consulted 2025, so that season is not a pristine final holdout; post-freeze monitoring is documented separately (`docs/reference/post_freeze_holdout.md`).

**Scope.** Marcel-lite covers the rate component only (no age curve; no Steamer/ZiPS/PECOTA). The count layer uses a point TBF forecast only. Weather, travel, catcher framing, and umpire effects are not integrated. Closing-line evaluation is covered only as the exploratory, statistically inconclusive pilot in Section 8.5, not as a core modeling claim.

---



## 10. Conclusion

This work delivers a leakage-safe pregame strikeout stack: frozen **180**-feature LightGBM krate, thin Ridge TBF, and a projected-exposure count layer (walk-forward expected-K MAE ≈ 1.78; ECE ≈ 0.024 pre-calibration). Nested screens plus within-fold bootstrap retain opponent lineup; other family deltas are small or fold-unstable. The durable claim is leakage discipline and chronological hygiene under a hard pregame constraint. An exploratory closing-line pilot (Section 8.5) is underway under a pre-registered n≥100 gate; as of this writing it is **statistically inconclusive** — directionally positive mean CLV but below the pre-registered sample threshold. Next steps for stronger empirical claims are a longer post-freeze holdout and completing that live-market pilot to a decision-grade sample.

---



## Reproducibility statement

Code for the leakage-safe pipeline, nested selection utilities, trainers, and count layer lives in the accompanying research repository (Python ≥ 3.11; Polars for feature construction; scikit-learn and LightGBM for models; pytest for automated leakage and pipeline checks). Experiments reported here were run on a local Windows workstation with a project-local virtual environment. Primary data are pitch-level Statcast exports accessed via Baseball Savant (commonly retrieved with community tooling such as pybaseball); users should respect Baseball Savant / MLB terms of use for redistribution and commercial use. Generated local artifacts (model binaries, fold CSVs, stabilization curves) are reproducible from the documented runners but are not required to read the manuscript’s tables and figures.

### Data Availability

Statcast data can be retrieved per-user via public tools (e.g., pybaseball) rather than redistributing bulk parquet, which helps sidestep Baseball Savant / MLB terms-of-use concerns around bulk redistribution.

---



## Appendix A. Repository map

Internal repository names, paths, and frozen-artifact identifiers are collected here so the body text can stay narrative. They do not change any metric reported above.

### A.1 Feature-set aliases

**Table A1.** Feature-set aliases used in code.


| Alias                      | Size | Description                                                        |
| -------------------------- | ---- | ------------------------------------------------------------------ |
| `pre_freeze_248`           | 248  | Pre-thin allow-list (comparison)                                   |
| `step7_185`                | 185  | Mean-window thin freeze                                            |
| `step10_180`               | 180  | Prior freeze (185 + five-stem last-start physics swap)             |
| `production`               | 184  | Current LightGBM default (`step10_180` + four discipline nominees) |
| `ridge_vif`                | 73   | Ridge research companion                                           |
| `workload_context_bullpen` | 24   | Frozen TBF feature set (thin bullpen)                              |




### A.2 Frozen model artifacts

**Table A2.** Frozen model artifact stems.


| Role                         | Artifact stem                                           |
| ---------------------------- | ------------------------------------------------------- |
| LightGBM k-rate (production) | `lightgbm_krate_20260803_155401`                        |
| LightGBM k-rate (prior 180)  | `lightgbm_krate_20260728_033241`                        |
| Ridge TBF (thin bullpen)     | `tbf_pa_ridge_workload_context_bullpen_20260728_035607` |


Generated research outputs under `artifacts/` are local/reproducible and typically gitignored; metadata hashes live in the matching model JSON sidecars.

### A.3 Documentation and code map

**Table A3.** Documentation and code map.


| Topic                                        | Location                                                           |
| -------------------------------------------- | ------------------------------------------------------------------ |
| Model card                                   | `docs/reference/model-card.md`                                               |
| Research log                                 | `docs/research/PAPER_NOTES.md`                                              |
| Feature / pipeline reference                 | `docs/reference/dev-notes.md`                                                |
| Registry freeze                              | `docs/research/step10_p1_registry_freeze.md`                                |
| Ablation findings                            | `docs/research/step3_*`, `step4_*`, `step5_*`, `step8_*`, `step9_*`         |
| Ablation bootstrap CIs                       | `models/Strikeout-Model/research/ablation_bootstrap.py`       |
| Marcel-lite rate baseline                    | `models/Strikeout-Model/research/marcel_baseline.py`          |
| Section 6.1 noise-floor / logit-target checks | `models/Strikeout-Model/research/section61_checks.py`         |
| Walk-forward expected-K MAE bootstrap         | `models/Strikeout-Model/research/walkforward_bootstrap.py`    |
| TBF / count layer                            | `docs/research/tbf_first_model_findings.md`, `docs/research/count_layer_findings.md` |
| Stack quality gates                          | `docs/research/phase11_model_quality_gates.md`                              |
| Population policy                            | `docs/research/phase_d_population_findings.md`                              |
| Architecture diagrams                        | `docs/diagrams/`                                                        |
| Canonical package                            | `src/Python/`                                                      |
| Feature safety gate                          | `src/Python/features.py`                                           |
| Rate trainer                                 | `Models/Strikeout-Model/train.py`                                  |
| TBF trainer                                  | `Models/TBF-Model/train.py`                                        |
| Superseded overlapping-date baseline archive | `docs/archive/leaky-baseline-2026-07-23/`                          |


---



## Appendix B. Chronological baseline (248-feature, date-disjoint)

For context against the frozen 184-feature gate, the earlier 2023–2024-only date-disjoint screen on the 248-feature allow-list reported:

**Table B1.** Chronological test metrics on the 248-feature date-disjoint screen.


| Model    | Test MAE | Test RMSE | Test R² |
| -------- | -------- | --------- | ------- |
| Mean     | 0.0854   | 0.1070    | −0.001  |
| Ridge    | 0.0788   | 0.0993    | 0.138   |
| LightGBM | 0.0783   | 0.0983    | 0.155   |


An older overlapping-date Mean/Ridge run is retained only as process history (Appendix A.3) and must not be cited as current performance.

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

