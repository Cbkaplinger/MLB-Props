# RECENCY BATCH REGISTRATION — freeze_recency_batch_v1 (development-only)

Registered 2026-10-15. This file is the repo mirror of the registration
section (section 9) appended to the count-eval-v2 card
(`C:\Users\ckaplinger\MLB-Props-Research\count-eval-v2-spec\COMPARISON_INTERFACE_SPEC.md`);
the frozen config is `freeze_recency_batch_v1.json` in this directory
(config sha256 `4b11e4b71cec3ab6c68235ea8966cf0f3f02f9a81cfc7d7bd209c6236c1af810`).

## What is registered

A DEVELOPMENT-ONLY EW-recency ablation on the three existing dev folds
(2024H1 / 2024H2 / 2025H1). No confirm claim, no adoption claim, no
production promotion. 2026 rows remain CLOSED. Execution requires owner
authorization (spec section 8); nothing here authorizes a run.

## Registered candidates (4)

| Role | ID | Features |
| --- | --- | --- |
| REFERENCE | `P1_B_logreg` | 6 frozen B features (no EW column) |
| TREATMENT 1 | `P1_H3_pitcher_ew_only` | 6 B features + exactly one EW-90d column (`ew_pitcher`) |
| TREATMENT 2 | `P1_H3_batter_ew_only` | 6 B features + exactly one EW-90d column (`ew_batter`) |
| INCUMBENT REFIT | `P1_H3_incumbent_refit` | 8 H3 features (both EW columns) |

All four share the UNCHANGED fitting/calibration procedure:
LogisticRegression(C=1.0, max_iter=1000); StandardScaler fit on base_train
ONLY (one scaler per fold); sigmoid calibrator (1-D unpenalized logistic of
y on logit(p)) fit on the 60-PA-bearing-day calibration sub-block ONLY
(cal_last = max game_date <= train_end; cal_first = cal_last - 59 days);
RAW + CAL lanes both output and kept separate.

## Fixed / unchanged

- **EW half-life: 90 days, FIXED.** No half-life search (no sweep, no
  tuning, no sensitivity lane) is permitted in this batch.
- Fitting settings, calibration partitions, shared populations (identical
  rows/labels across candidates, eval-identity-hash equality asserted),
  seed 20261001, n_boot 2000 block-stratified slate-date bootstrap: all
  unchanged from the executed first-run-v1 procedure.
- Inputs: identical canonical pair as first-run packet v1
  (pa_table `e30d8561...a85f0`, features_v3 `163ad433...b7e8f8`).

## Metrics and lanes

- **Primary: Brier. Secondary: log loss.**
- **RAW lane is principal** (all intervals, contrasts, family claims).
- **CAL lane reported separately** as derived point estimates (no CIs, no
  contrast claims); never merged with RAW.

## Predeclared contrasts (exactly 4)

| ID | Contrast |
| --- | --- |
| C1_pitcher_ew_vs_B | `P1_H3_pitcher_ew_only` minus `P1_B_logreg` |
| C2_batter_ew_vs_B | `P1_H3_batter_ew_only` minus `P1_B_logreg` |
| C3_both_vs_pitcher_only | `P1_H3_incumbent_refit` minus `P1_H3_pitcher_ew_only` |
| C4_both_vs_batter_only | `P1_H3_incumbent_refit` minus `P1_H3_batter_ew_only` |

**Multiplicity:** family of 4 contrasts. Registered reporting rule: report
each contrast's ORDINARY (unadjusted) 95% percentile interval AND the
Holm-adjusted family result SEPARATELY. Any family-level claim across the 4
contrasts must come from the Holm-adjusted result, never from the ordinary
intervals.

## 2025H2 exclusion (explicit)

`confirm_2025H2` is EXCLUDED and NOT SCORED in this batch. The exclusion is
enforced by `RunConfig.include_confirm=False` in the frozen execution
command, implemented and synthetic-tested BEFORE registration:

- `test_confirm_exclusion_control_proves_no_confirm_rows_in_fits_or_bootstrap`
  — differential proof: flipping every confirm-window label leaves
  metrics.json BYTE-IDENTICAL (no confirm row reaches any base_train fit,
  scaler, calibration sub-block or the pooled-dev bootstrap), and no
  `preds_confirm_2025H2__*` file is written.
- `test_confirm_scored_by_default_and_excluded_only_when_configured` —
  control: the default config still scores confirm LAST and never pools it.

## Outputs and status

- Output destination: `C:\Users\ckaplinger\MLB-Props-Research\recency-batch-v1`
  (confirmed nonexistent 2026-10-15; write-once via `WriteOnceError`).
- Batch status: **FROZEN - NOT EXECUTED.**
