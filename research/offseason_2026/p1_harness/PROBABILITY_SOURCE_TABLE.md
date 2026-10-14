# PROBABILITY SOURCE TABLE - P1 harness candidates + ladder / tree arms

Point-in-time acceptance evidence, 2026-10-13. Every row states where the
probability comes from, what it was fit on, its calibration status, and the
evaluation row count. Canonical sources: the executed run dirs under
`<external-lake>\` (see RUN_VERSION_MAP.md in this
directory); hashes pinned in `p1_harness/conftest.py` (EXPECTED_ARTIFACTS)
and in each run's own manifest. No candidate here is a production model.

## p1-harness-v2 (frozen harness; raw uncalibrated probabilities)

Source of truth: `MLB-Props-Research\p1-harness-v2\` (run_version
"p1-harness-v2", 2026-10-13T04:23:45+00:00). PA table 2022-04-07..2025-12-31,
731,347 completed PAs (truncated_pa excluded). Splits: TRAIN
game_date < 2025-01-01 (548,421), DEV_VALIDATION 2025-01-01..2025-06-30
(95,357; development/validation only), EVAL 2025-07-01..2025-12-31
(87,569; 2026 rows reserved retrospectively, none scored).

| Candidate | Probability source (formula / script) | Fit population | Calibration status | Eval rows |
|---|---|---|---|---|
| A shrunk (`A_reference`) | `p_pitcher_prior_w150 = (k_prior + 150*lg_rate) / (n_prior + 150)` - the pitcher's shrunk K rate used directly as the probability; `build_features.py` (`shrunk()`, strict-prior daily cumulatives) + `fit_models.py` (pred alias). No parameters fit. | None (rule-based; features derived from the 2022-2025 PA table, W=150 fixed a priori) | RAW, uncalibrated (v2 owner ruling 4: NO calibration fitted anywhere) | 87,569 (EVAL; Brier 0.17333, log loss 0.53008) |
| LOG5 (`LOG5_reference`) | `q = (p*b/l) / (p*b/l + (1-p)*(1-b)/(1-l))` with p/b = w150 shrunk pitcher/batter rates, l = strict-prior league rate; `fit_models.log5` (clipped to [1e-9, 1-1e-9]). Nothing fit; identity-checked by `test_log5_identities.py`. | None (pure formula from the same w150 priors + lg_rate) | RAW, uncalibrated | 87,569 (EVAL; Brier 0.17055, log loss 0.52182) |
| B logreg (`B_logreg`) | `LogisticRegression(C=1.0, max_iter=1000)` on [p_pitcher_prior_w150, p_batter_prior_w150, lg_rate, n_prior_pitcher, n_prior_batter, cold_start]; `fit_models.py` (lr_b) | TRAIN only: game_date < 2025-01-01, n = 548,421 PAs (2022-04-07..2024-12-31) | RAW, uncalibrated. DEV_VALIDATION used for development/inspection only; no calibrator fitted in v2 | 87,569 (EVAL; Brier 0.17067, log loss 0.52220) |

## overnight-p2 history ladder (block-wise refits; diagnostic, not a deployed model)

Source of truth: `MLB-Props-Research\overnight-p2\` (run_identity_sha256
6a62d8edf60ec0951d30a3114ac3603da7d5296d52a1c1ea800dc1dff7c6def2;
`reports/ladder_results.json`, `reports/fit_ledger.json`). Protocol per
block: base_train (all PAs strictly before the block's calibration window)
-> 60-day calibration sub-block -> assessment (following slate window);
candidate logistics are standardized (StandardScaler fit on base_train
only). Confirm block = 2025H2. Assessment windows and slate-date counts as
recorded in ladder_results.json.

| Candidate | Probability source (formula / script) | Fit population | Calibration status | Eval rows |
|---|---|---|---|---|
| H3 (hazard-free exp-weighted logistic) | `LogisticRegression(C=1.0, max_iter=1000)` on the harness six features + `ew_pitcher` / `ew_batter` (exponentially weighted K rates, 90-day half-life, pooled counts, strictly prior); refit per block by `scripts/run_ladder.py` | Per block, base_train rows: 2024H1 123,081; 2024H2 219,078; 2025H1 306,791; confirm 2025H2 401,590 (cumulative history, 2022 onward) | Both RAW and block-sigmoid-calibrated reported (calibrator fit per block on the calibration sub-block, n = 59,484..61,023); calibration is diagnostic, NOT a promotion step | 87,569 (confirm 2025H2 assessment, 86 slate dates; H3 raw Brier 0.17028, log loss 0.52112 - best of the ladder on the confirm block) |
| LightGBM (equal-information family) | Single tested config (`objective=binary` Logloss, 300 trees, lr 0.05, num_leaves 31, min_child_samples 200, subsample/colsample 0.8, reg_lambda 1.0, seed 20261001) on EXACTLY the H3 feature set, same rows; `scripts/run_lgbm_equal_info.py` | Same base_train rows as the ladder per block (2024H1 123,081 ... confirm 401,590) | RAW only in the equal-info comparison (label: "SINGLE TESTED CONFIG, not a tuned sweep; no calibration stage, no promotion"); the separate 12-feature run also reports a block-sigmoid-calibrated arm | 87,569 (confirm 2025H2 assessment, 86 dates; LGBM_H3features Brier 0.17066, log loss 0.52206 - loses to H3 logistic: paired dLL +0.00094, CI95 [+0.00059, +0.00131]) |

## Reading notes

- EVAL/confirm populations are identical across A / LOG5 / B / H3 /
  LightGBM where paired comparisons are quoted (87,569 rows; key-set
  equality asserted in-run and by `test_d_eval_prediction_key_sets_identical_across_candidates`).
- p1-harness v1 (dir `MLB-Props-Research\p1-harness\`, EVAL n = 87,712)
  is SUPERSEDED: its same-date backward-filled opening-day league prior
  and its "CALIBRATION" labeling were corrected in v2 (owner rulings
  2026-10-13). Do not quote v1 metrics as current.
- No calibration claim: v1/v2/v3 BF A/B scoring reports (pilot chain)
  contain no calibration check (disclosed omission, see
  bf-closure-record-2026-10-13).
