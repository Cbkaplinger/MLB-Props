# Final58 consensus freeze (2026-08-20)

## Why this document exists

This records the end-to-end feature search completion where the objective was:

1. maximize walk-forward `expected_K` MAE performance, and
2. avoid chunk-local bias by combining winners across all chunk screens.

It is the canonical note for the `production_final58_consensus` feature freeze
candidate.

## What was run

- Full feature-universe chunk screens (`full_feature_importance_screen/chunk_*`)
  were treated as source evidence.
- Winner extraction from each chunk was assembled into one ranked pool:
  `artifacts/model_quality/chunk_winner_pool/winner_pool_ranked.csv`.
- A consensus pool was created by merging:
  - `refine_top220` ranking,
  - chunk-winner ranking,
  - best-feature finalists from prior fast/deep sweeps.
- Multi-pass LGBM-only dataset search re-optimized feature size, windows, and
  monotone mode on nested walk-forward folds.

Artifacts:

- `artifacts/model_quality/final_feature_dataset_search/leaderboard_across_runs.csv`
- `artifacts/model_quality/final_feature_dataset_search/consensus_v1_phase2_deep/summary.json`
- `artifacts/model_quality/final_feature_dataset_search/consensus_v1_phase2_deep/best_features.csv`

## Final MAE winner

- Feature set name: `production_final58_consensus`
- Feature count: `58`
- Best sweep tag: `consensus_v1_phase2_deep`
- Best config:
  - `k_seed=90`
  - `monotone_mode=coarse_positive`
  - LGBM params: `learning_rate=0.03`, `num_leaves=31`, `min_child_samples=50`,
    `subsample=0.8`, `colsample_bytree=0.7`, `reg_alpha=0.1`, `reg_lambda=2.0`
- Walk-forward metrics:
  - `expected_k_mae_mean = 1.766938`
  - `k_rate_mae_mean = 0.076695`

This improved the previous best (`production_final42_fast`, expected_K MAE
~`1.772601`).

## Requested family ablation on finalized set

Runner:

- `models/Strikeout-Model/research/final_feature_set_ablation.py`

Output:

- `artifacts/model_quality/final_feature_set_ablation/freeze_final58_v1/ablation_summary.csv`

Results (outer-fold mean):

- `lgbm_base`: expected_K MAE `1.768178` (best in family ablation)
- `ridge`: expected_K MAE `1.771217`
- `linear`: expected_K MAE `1.774505`

Interpretation:

- The finalized dataset still favors nonlinear modeling.
- Ridge and linear remain useful baselines and drift sentinels.

## Governance replay note (important)

Even after MAE improvement, historical replay and open-skill governance still
favor sparse72-family challengers over both final58 and frontier42 variants.
Keep this
split explicit:

- **MAE winner:** `production_final58_consensus`
- **current governance incumbent:** `production_sparse72` / `production_sparse72_monotone` (window-dependent)

## Calibration parity note

`compare_feature_set_governance.py` now supports apples-to-apples replay across
`raw` / `platt` / `isotonic` modes under shared policy and ledger slices.
`compare_feature_set_market_skill.py` extends this to larger open-opportunity
universes and supports date-bounded holdout windows.

## Next steps after this freeze

1. Tune LightGBM on `production_final58_consensus` only (feature set fixed).
2. Re-run governance + uncertainty sweep with risk-adjusted metrics
   (Sortino, max drawdown, Calmar, CVaR) alongside ROI/CLV.
3. Add optional replay mode that applies the same chosen probability calibration
   policy (Platt/isotonic/identity) to all candidates before edge gating.
4. If weather features are introduced later, reopen feature search as a new
   versioned freeze cycle instead of mutating this baseline silently.
