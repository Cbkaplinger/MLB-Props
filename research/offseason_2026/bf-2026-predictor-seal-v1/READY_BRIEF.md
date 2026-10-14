# READY_BRIEF - registered-fit feasibility (single fit through 2025-12-31)

**Date:** 2026-10-14. **Scope:** bounded feasibility brief only. NO fit
has been executed here; NO 2026 outcomes were read; the seal payload is
untouched (see CLASSIFICATION.md). Executing the fit is a NEW FIT and
remains forbidden inside seal prep - it is the registered execution
itself (PREREGISTRATION_2026.md section 3), gated on owner approval.

## Verdict (read this first)

**The registered fit is a DETERMINISTIC EXECUTION of the frozen recipe.
Every parameter, window, and machinery element is already frozen and
gate-verified; no tuning choices exist.** A short list of decisions must
still be pinned BEFORE execution - not because the recipe is ambiguous
about the fit itself, but because the fit's outputs create downstream
commitments (which probability column becomes the registered arm
output, and whether/how the seal payload is rebuilt). Those are listed
under "Unresolved decisions" below; none of them is a modeling choice.

## Exact frozen procedure to execute (all values verbatim)

1. **Feature/frame settings (DEV_STANDARD_RECIPE.md section 1, FROZEN):**
   H3 8-feature vector `[p_pitcher_prior_w150, p_batter_prior_w150,
   lg_rate, n_prior_pitcher, n_prior_batter, cold_start, ew_pitcher,
   ew_batter]`; w = 150 cumulative shrinkage vs contemporaneous league
   mean; EW 90-day half-life with lg_rate fallback; StandardScaler fit
   on base_train only; LogisticRegression(C=1.0, max_iter=1000); block
   sigmoid calibrator (logistic on logit(p_raw)); raw and calibrated
   columns kept separate; no pooled constant. Comparator arm: cumulative
   log5 (3-param, identity-gated, EPS=1e-9) on the same priors, same
   calibrator rule.
2. **Base-fit window (registration section 3):** PA rows
   2023-01-01..2025-12-31. **2022 (182,051 PAs) is warm-up ONLY** -
   feeds strictly-prior feature state and league history; never fitted,
   never scored.
3. **Calibration sub-block (registration section 3 + recipe section 2):**
   the calibrator is fit on the final 60 CALENDAR DAYS ending at the
   last PA-bearing date of the train window. For this fit that date is
   **2025-09-28** (registration-pinned; verified against the 2025
   regular parquet: max PA-bearing date = 2025-09-28). Window =
   2025-07-31..2025-09-28 inclusive = 60,056 completed PAs over exactly
   60 PA-bearing days (measured, metadata only). **The < 5,000-row
   gate PASSES by a wide margin; the calibrator will be AVAILABLE.**
   Note: the registration addendum's section-2 wording ("final 60
   PA-bearing days") and the recipe's section-2 wording ("final 60
   calendar days ending at the last PA-bearing date") resolve to the
   IDENTICAL 60 dates for this window - measured, so the discrepancy is
   defused (still recorded under decisions D1 for the transcript).
4. **Arm outputs:** per the recipe, raw (`pred_H3_raw` /
   `pred_LOG5_raw`) and calibrated (`pred_H3_cal` / `pred_LOG5_cal`)
   columns are both produced and kept separate.
5. **Determinism:** the ladder precedent (run_ladder.py) is
   deterministic; reproduction gates require state machinery vs
   features_v3 exact, and any reuse must verify against stored
   checkpoints before new rows are scored (recipe sections 2/6).
   Library pins: python 3.11.9, polars 1.43.0, numpy 2.4.6,
   scikit-learn 1.9.0 (overnight-p2 run_identity).

## Inputs needed (all verified present)

| Input | Status |
| --- | --- |
| Extended PA table 2022-2026 | exists; 2022-2025 portion == frozen overnight-p2 pa_table (731,347 rows bitwise, seal-prep gate V1) |
| Feature state machinery | verified: daily states == frozen features_v3 (gate V2, diffs 0.0) |
| Ladder refit machinery | verified: checkpoint-verified deterministic refits (gate V3, max abs diff <= 1e-8) |
| Calibration window rows | 60,056 completed PAs in 2025-07-31..2025-09-28 (>= 5,000 gate) |
| Scoring path for any 2026 payload | cohort-aware scorer committed (run_bf_ab_score_cohort.py; manifest-pinned, metric-verbatim, demos PASS) |

## How the windows are implemented without leakage

- **Feature state strictly prior:** day-d state is built only from PAs
  strictly before d; same-date information never enters a prior; state
  and pools update only AFTER all starts of a date are forecast
  (recipe section 2; machinery gate-verified at 0.0 against
  features_v3).
- **Base fit excludes cal:** base_train = the train window MINUS the
  calibration sub-block ("base model on base_train (earlier data
  only)", recipe section 2). StandardScaler and the logistic are fit on
  base_train only; the sigmoid calibrator is fit on the calibration
  sub-block only.
- **Cal precedes assess:** the calibration sub-block ends 2025-09-28,
  strictly before the 2026 assessment window. Both 2026 reporting
  blocks (block_2026H1 / block_2026H2) are scored with this SINGLE fit;
  there is NO in-2026 model or calibration refit (registration
  section 3). During assessment only historical feature state accrues
  strictly-prior as 2026 dates pass.
- **2026 never enters the fit:** fit cutoff 2025-12-31; 2026 excluded
  from all fitting/choice (registration section 3; standing
  no-2026-tuning rule).

## Unresolved decisions (must be pinned by the owner BEFORE execution)

- **D1 - calibration window wording (transcript only):** section-2
  addendum says "final 60 PA-bearing days"; section 3 + recipe section 2
  say "60 calendar days ending at the last PA-bearing date". For THIS
  fit both resolve to the same 60 dates (2025-07-31..2025-09-28,
  verified). Pin the recipe/section-3 wording for the report.
- **D2 - registered arm column:** the preregistration records the block
  sigmoid calibrators as "diagnostic, NOT a promotion step" and keeps
  raw/calibrated separate, while the seal prep used CAL columns (recipe
  section 5). Which column (raw vs cal) is THE registered arm output
  for the 2026 assessment must be pinned before any scoring; both will
  be produced regardless.
- **D3 - payload consequence:** executing this fit produces a new
  single-fit model that supersedes the confirm_2025H2 checkpoint
  currently used by the seal payload. Decide: (a) rebuild the seal
  payload under the new fit (a new seal version; the current 134-row
  payload stays frozen as PILOT-REPRODUCTION per CLASSIFICATION.md), or
  (b) keep the pilot-reproduction payload on confirm_2025H2 and use the
  new fit only for the full-season lane.
- **D4 - cohort scope:** the registered evaluation names two cohorts
  (captured + full-season). Enumeration (experiments/
  bf-2026-cohort-enumeration-2026-10-14) shows 4,858 eligible
  full-season rows but only 134 have captured pregame cutoffs; the
  full-season lane needs a registered cutoff rule (reconstructed
  scheduled first pitch, raw-hash-unverified captures) or stays
  blocked. The 134 pilot rows remain excluded from confirmation and
  pooling per sections 8-9 regardless.
- **D5 - execution authorization:** this fit is a NEW FIT; it is the
  registered execution and must be run ONCE, post-authorization, with
  deviations logged before results are read (registration section 10).
  It must never run inside seal prep.
- **D6 - reporting preconditions:** chat 2 items 9.1 (paired slate-date
  uncertainty in P1, opening-day prior relabel/leakage rule over the
  506 rows, durable provenance) must be evidenced before results are
  treated as confirmatory (registration section 10; recipe section 9.1).

## Reproduction pointers

- Registration: `pregame-state-v1/PREREGISTRATION_2026.md` (sections 2,
  3, 10); frozen recipe: `pregame-state-v1/DEV_STANDARD_RECIPE.md`
  (sections 1, 2, 8, 9); seal prep gates + lineage:
  `seal_prep_report.json` in this directory; cohort enumeration card:
  repo `research/offseason_2026/experiments/bf-2026-cohort-enumeration-2026-10-14/`;
  scorer generalization card: repo
  `research/offseason_2026/experiments/bf-cohort-scorer-mode-2026-10-14/`.
