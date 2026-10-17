# lgbm-equal-info-v2 CLOSEOUT — 2026-10-16

**Equal-information LightGBM closeout (docs-only).** The corrected run
executed exactly once under explicit owner authorization; matched exposure
verified; the registered paired contrast finds **NO detectable development
advantage**. Equal-information nonlinear PA challengers are RETIRED pending a
new registered reason.

## The corrected run executed once

- Receipt: `execution_receipt.json`, sha256
  `0d2f8ba492cc9afb66d293ec384786c9d0a01da77252f15a54fa11823e06c2bf`, at
  `C:\Users\ckaplinger\MLB-Props-Research\lgbm-equal-info-v2\execution_receipt.json`.
- Run ID: `f5564ee643de19ec0e9d7e93ce12dd42f11b3a40881285d768c9da197d52f554`;
  output dir
  `MLB-Props-Research\lgbm-equal-info-v2\f5564ee643de19ec0e9d7e93ce12dd42f11b3a40881285d768c9da197d52f554\`
  (write-once, untouched).
- Executed 2026-10-16T18:33:50Z, `executed_exactly_once: true`, no silent
  retry/overwrite, at git head `1ca413dbc9f3abc739f4accf0c9a15a62141ab29`
  (the frozen v2 packet; preflight hashes all matched, destination confirmed
  absent before the run).
- MLflow: experiment `pa-k-probability-v1`, parent `c2ad6145...e93ec`, status
  FINISHED, tracking VERIFIED (22/22 inventory entries hash-matched
  byte-exact against the artifact store in a fresh process).
- Dev folds executed: block_2024H1 / block_2024H2 / block_2025H1;
  confirm_2025H2 EXCLUDED — NOT SCORED; 2026 CLOSED.

## Matched exposure verified

The v1 defect (LightGBM fitting on ~20% fewer rows than the logistic because
selection carved out an inner set) is fixed and asserted: STAGE 1 selects the
iteration on the training-only inner carve-out, STAGE 2 refits FRESH on the
FULL base_train; the logistic reference fits the same rows. Per-fold fit rows
equal (LightGBM refit == logistic, asserted and persisted per arm):

| Fold | LightGBM refit rows | Logistic rows | Equal |
| --- | --- | --- | --- |
| block_2024H1 | 123,081 | 123,081 | yes |
| block_2024H2 | 219,078 | 219,078 | yes |
| block_2025H1 | 306,791 | 306,791 | yes |

Real iteration selection now works: chosen iterations 51 / 46 / 63 trees
(inner eval history recorded per round; v1's best_iteration=1 stubs are
resolved), with fresh-refit `num_trees == chosen` asserted.

## Registered result (paired contrast, C_lgbm_v2_vs_both_EW_logistic)

- Pooled dev eval: 277,623 PA rows, 281 slate dates.
- Pooled RAW Brier (primary): LightGBM 0.16975817 vs logistic 0.16974394.
- **Paired contrast (LightGBM − logistic): +1.42e-05, 95% CI
  [−4.30e-05, +6.93e-05], null-centered p = 0.6157 (p_holm = 0.6157)**
  (2000 resamples, seed 20261001, block-stratified slate-date bootstrap,
  shared draw stream). CI straddles zero; effect size ~2e-05 Brier.
- Log loss secondary +3.81e-05; CAL +3.54e-05 (descriptive only).
- Per-fold direction flips (logistic better 2024H1; LightGBM better 2024H2
  and 2025H1); all differences tiny.

## Honest conclusion

**No detectable development advantage.** With matched exposure and real
iteration selection, the equal-information LightGBM is statistically
indistinguishable from the both-EW logistic on this registered dev estimand.

This is deliberately NOT the claim "boosting cannot help." What was tested is
one challenger configuration at the registered equal-information contract
(same 8 both-EW features, same folds, matched rows, fixed hyperparameters, no
search). A future architecture could still help; detecting that would require
a NEW registered reason and a NEW pre-registered challenger — not a retune of
this one.

## Decision

- **Equal-information nonlinear PA challengers RETIRED** pending a new
  registered reason. No promotion, no production change, no further
  LightGBM PA work under this contract.
- The PA lane's provisional development leader remains
  P1_H3_incumbent_refit (both-EW logistic), unchanged by this closeout.
- The market-eval / log5 findings' identities and statuses are UNCHANGED.
- No retraining path is reopened; 2026 remains locked retrospective /
  confirmatory only.

## Evidence pointers

- Run metrics: `metrics.json` in the run dir (22-file sha256 inventory;
  per-fold + pooled metrics; bootstrap draws/contrasts persisted).
- Execution receipt: `execution_receipt.json` (hash above) — authorization,
  preflight, matched-exposure block, contrast block, interpretation string.
- MLflow run `c2ad6145c4734a7a9a585daad90e93ec` in
  `sqlite:///C:/Users/ckaplinger/MLB-Props-Research/mlflow.db`, tracking
  status VERIFIED via `tracking_status.json`.
- Prior state: `experiments/lgbm-equal-info-v1-prep-2026-10-15/card.md` and
  the backlog Session Snapshot entries for 1ca413d / 64692c7 / 2ee272f.
