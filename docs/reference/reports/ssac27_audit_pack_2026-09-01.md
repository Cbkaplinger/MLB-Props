# Merged evidence pack (consolidated 2026-09-17)

> Content-intact merge of `ssac27_audit_pack_2026-09-01.md`, `ssac27_audit_pack_2026-09-01.md`, `ssac27_audit_pack_2026-09-01.md`, `ssac27_audit_pack_2026-09-01.md`, `ssac27_audit_pack_2026-09-01.md`. Newest first. Originals survive in git history; update citations to this file.

---

<!-- section 1/5 from ssac27_policy_freeze_audit_2026-09-01.md (merged 2026-09-17, content intact) -->

# SSAC27 Item 4 — Policy-Freeze vs Evaluation-Window Audit

**Date:** 2026-09-01  
**Verdict:** **FAIL — cannot draw an honest post-freeze evaluation line.**  
**Required action:** Reclassify the audited `n=26` ROI/Sharpe lane as **policy-search evidence**. Do not treat it as post-freeze out-of-sample deployment performance in headlines, abstracts, or resume claims.

---

## Question

Is the 26-bet lane's ROI/Sharpe valid as post-freeze evaluation? That requires:

1. deployment blend `0.60 sparse72_monotone / 0.40 final58`,
2. edge floor `0.12`,
3. isotonic transfer-calibration,

to be **frozen on a strict date**, with **all 26 bets posterior** to that freeze.

---

## Timeline (artifact + git backed)

| Event | Timestamp / span | Evidence |
| --- | --- | --- |
| 26-bet slate dates | **2026-07-30 → 2026-08-17** | `open_top3_transfer_bestfloor_picks_aug21_deduped_top3_from_dedupedsweep.csv` filtered `config=top3`, `best_floor=0.12` (`n=26`) |
| Manual replay generated | **2026-08-21T05:37:07Z** | `open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.json` `generated_utc` |
| Model stems used by live blend | **2026-08-21 ~05:41** | `live_krate_ensemble.json` stems `..._20260821_0541*` |
| Live blend file committed | **2026-08-21 01:49:35 -0400** | git `8ad4681` — creates `production/ops/live_krate_ensemble.json` |
| Selection rule (explicit) | same commit | `"best_manual_roi_after_open_calibration_transfer_deduped"` |
| Isotonic calibrator | **2026-08-21_160723** | `artifacts/models/prob_calibration_isotonic_20260821_160723.*` |
| Declared freeze stamp | **2026-08-21T16:10:00Z** | `production/ops/kpi_policy.json` → `king_profile_freeze.frozen_utc` |
| Freeze block landed in git | **2026-08-27** | git `de942c3` adds `king_profile_freeze` to `kpi_policy.json` (stamp claims Aug 21; commit is Aug 27) |
| Edge floor `0.12` reaffirmed | **2026-08-06** (pre-lane end) | `docs/research/floor_freeze_log.md` — floor alone is earlier; blend+isotonic are not |

---

## Finding

**Every one of the 26 graded bets is dated before the declared freeze.**

- Last bet date: `2026-08-17`
- Freeze stamp: `2026-08-21T16:10:00Z`
- Gap: freeze is **4+ days after** the evaluation window ends

Worse than a simple timing miss: the live blend was **selected on** this lane's ROI. `live_krate_ensemble.json` records:

```text
selection_rule: best_manual_roi_after_open_calibration_transfer_deduped
```

So the 26-bet ROI/Sharpe is the **objective that chose the policy**, not an evaluation after the policy was locked.

Floor `0.12` was reaffirmed earlier (2026-08-06), but that does not rescue the lane: blend weights and isotonic transfer were chosen/fit on 2026-08-21 against this same search window.

---

## What this does *not* imply

- It does **not** invalidate leakage-safe modeling, chronological MAE lanes, or governance engineering.
- It does **not** say the 26-bet numbers are fabricated — they are real replay metrics on a real window.
- It **does** say they are the wrong *epistemic* class for “deployed post-freeze performance.”

---

## Required manuscript / messaging changes

1. Label the 26-bet ROI/Sharpe/PnL lane as **policy-search / pre-freeze selection evidence** everywhere it appears.
2. Strip ROI/Sharpe from abstract/resume *headline claims* of deployment success (numbers may remain only as search-window diagnostics with the FAIL label).
3. Keep DSR/PSR power discussion — it still correctly warns the sample is underpowered.
4. True post-freeze performance = bets with `game_date > 2026-08-21` (or strictly after `frozen_utc`) under the locked blend/floor/isotonic pointer. That lane is not yet the paper's audited 26.

---

## Resume-ready one-liner

Frozen production profile `KING_PROFILE_AUG2026` (2026-08-21): blend `0.60/0.40`, floor `0.12`, isotonic pointer locked. The previously cited 26-bet ROI/Sharpe window (2026-07-30–08-17) is **pre-freeze policy-search evidence**, not post-freeze OOS validation.

---

<!-- section 2/5 from ssac27_n5161_enumeration_2026-09-01.md (merged 2026-09-17, content intact) -->

# SSAC27 Item 5 — N=5161 enumeration

**Date:** 2026-09-01  
**Pinned count:** `artifacts/odds_log/quant_honesty_aug21_summary.json` → `n_trials = 5161`  
**Exact enumeration source:** `artifacts/odds_log/ensemble_sweep_ranked_ensemble_full_aug21_deduped.csv` (**5161 rows**)

## What 5161 is (and is not)

**Is:** the number of **eligible blend × edge-floor configurations** evaluated in the Aug-21 deduped open-universe ensemble sweep after the `min_bets ≥ 25` gate.

**Is not:** Optuna hyperparameter trials, model-family architecture search counts, or feature-subset enumerations. Earlier manuscript wording that implied “feature-set × model-family × hyperparameter draws” was imprecise and is corrected below.

## Regenerable arithmetic

Producer: `production/ops/run_model_ensemble_sweep.py`  
Metadata: `artifacts/odds_log/ensemble_sweep_ensemble_full_aug21_deduped.json`

| Factor | Value |
| --- | --- |
| Feature-set lanes in the blend simplex | 3 — `production_sparse72`, `production_sparse72_monotone`, `production_final58_consensus` |
| Calibration mode | isotonic (fixed) |
| Weight grid | step `0.05` on the 3-simplex → **231** blends |
| Edge floors | `0.005` … `0.12` step `0.005` → **24** floors |
| Full Cartesian grid | **231 × 24 = 5544** (`rows_total` in metadata; full CSV) |
| Eligibility gate | `n_bets ≥ 25` on deduped manual tickets |
| Dropped ineligible | **383** |
| **Eligible / ranked (= N)** | **5544 − 383 = 5161** |

Verification (2026-09-01):

```text
len(ranked CSV) == 5161
len(full CSV filtered n_bets >= 25) == 5161
```

## Implication for DSR

The Deflated Sharpe Ratio in `quant_honesty_aug21_summary.json` deflates the audited lane’s Sharpe using **this policy-search breadth** (blend×floor configs), not a model-training trial count. That is the correct object for a *decision-policy* DSR, but it must be stated explicitly so readers do not confuse it with Optuna `n_trials`.

## Manuscript action

Update §8.2 DSR provenance to this enumeration and cite the ranked CSV + sweep metadata as the auditable source.

---

<!-- section 3/5 from ssac27_honesty_slippage_lineage_2026-09-01.md (merged 2026-09-17, content intact) -->

# Artifact lineage — quant_honesty / slippage vs authoritative replay (SSAC27 item 7)

**Date:** 2026-09-01  
**Status:** Documented intentional freeze (no silent rewrite of bootstrap/DSR artifacts)

## Authoritative point estimates (use in manuscript headlines)

Source: `artifacts/odds_log/open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.json`

| Metric | Value |
| --- | ---: |
| ROI | 0.4363 |
| Sharpe | **0.4438** |
| max drawdown | **0.1905** |
| Calmar | **2.2903** |
| PnL (u, 1u=50) | +24.17 |

These are the **policy-search** n=26 lane numbers (pre-freeze; demoted from deployment claims per SSAC #4).

## Frozen diagnostic artifacts (do not treat as conflicting headlines)

| Artifact | Sharpe | maxDD | Calmar | Role |
| --- | ---: | ---: | ---: | --- |
| `quant_honesty_aug21_summary.json` `baseline_metrics` | 0.4352 | 0.3685 | 1.1841 | PSR/DSR/bootstrap CIs / power plan; Sharpe used in DSR pipeline at freeze |
| `slippage_sensitivity_top3_floor12_aug21.csv` | 0.4352 @ 0pp | — | — | Haircut sensitivity on same 26-bet set |

**Why not rewrite:** Re-running Bailey–LdP DSR/bootstrap from a different Sharpe definition would change `dsr`/`psr`/CIs without a pinned regeneration script in-repo. The manuscript already cites **replay** for profile points and **honesty JSON** for DSR/CIs; §8.3 cites the slippage CSV Sharpe column as-is.

**Rule going forward:** Headline ROI/Sharpe/DD/Calmar → replay JSON. Trial-adjusted stats → honesty JSON. Slippage table → slippage CSV. Never mix without a lane tag.

## Equity curve regeneration

Figure 3 is now regenerable via `docs/paper/make_figures.py` → `fig_equity_top3_vs_top1()` from  
`artifacts/odds_log/open_top3_transfer_bestfloor_picks_aug21_deduped_top3_from_dedupedsweep.csv`  
(`config` ∈ {top1,top3}, `best_floor=0.12`; PnL_u = stake × rpd / 50).

---

<!-- section 4/5 from ssac27_naive_mae_baseline_2026-09-01.md (merged 2026-09-17, content intact) -->

# SSAC27 Item 6 — Chronological naive `k_rate` baselines (2026-09-01)

**Producer:** `models/Strikeout-Model/research/marcel_baseline.py`  
**Outputs:** `artifacts/feature_research/marcel_baseline/`

## Chronological game-level lane (same split as registry freeze test start)

| Partition | Baseline | MAE | RMSE | R² | n |
| --- | --- | ---: | ---: | ---: | ---: |
| test | marcel (3/2/1 + EB regress, no age) | **0.08257** | 0.10340 | 0.0644 | 1413 |
| test | prior_season_only | 0.08301 | 0.10384 | 0.0564 | 1413 |
| test | train_mean | 0.08538 | 0.10696 | −0.0010 | 1413 |
| validation | marcel | 0.08209 | 0.10260 | 0.0428 | 1404 |
| validation | train_mean | 0.08374 | 0.10497 | −0.0018 | 1404 |

Frozen LightGBM **reference** on the same test window (not re-fit here): MAE ≈ **0.0787** (`docs/research/step10_p1_registry_freeze.md`).

Same-lane train_mean on `pitcher_training.parquet` chronological test: `k_rate` MAE ≈ **0.08538**; `expected_K` (= `k_rate × PA`) MAE ≈ **1.92** (train-mean rate × observed PA vs realized K).

## Relation to Table 2a (sparse72 model-family)

Table 2a ridge sparse72 MAE **0.07668** is a **different protocol** (outer-fold sparse-set family ablation), not the Marcel chronological split. Do **not** subtract Table 2a − Marcel as a single delta without fold-aligned predictions.

Manuscript treatment: keep Table 2a as challenger screen; add **Table 2b** chronological naive baselines so readers see delta-over-naive on an auditable lane (LGBM freeze 0.0787 vs Marcel 0.08257 ≈ **−0.0039** absolute MAE).

---

<!-- section 5/5 from ssac27_null_decision_lane_2026-09-01.md (merged 2026-09-17, content intact) -->

# SSAC27 Item 8 — Null / placebo decision lanes (2026-09-01)

Post-freeze matched nulls vs locked KING floor gate.

| Lane | n | ROI | Win rate | CLV mean | CLV>0 |
| --- | ---: | ---: | ---: | ---: | ---: |
| king_passes_floor_postfreeze | 74 | -0.0155 | 0.4865 | 0.0159 | 0.5862 |
| random_prob_matched_n_floor | 74 | -0.0917 | 0.4595 | 0.0108 | 0.4643 |
| naive_prior_matched_n_floor | 74 | -0.0562 | 0.473 | 0.0112 | 0.4737 |
| shuffle_edge_on_king_set | 56 | -0.0256 | 0.4821 | 0.0203 | 0.6 |

Source JSON: `artifacts/odds_log/null_decision_lane_20260901.json`.

## Read carefully

- KING lane uses real stakes (`passes_floor`).
- Random/naive may impute stake for logged non-bet candidates; they are **null references**, not production policies.
- If KING does not beat these nulls on ROI *and* CLV with margin, do not claim decision-layer edge.

