## Deviations (all caught by gates before results were reported)
- Assembly bug: 2023 rows initially leaked into the 2024 evaluation frame (mixed-season frame made E1 contain all
  of 2023). Caught by the official-BF reconciliation assertion (null official_BF); fixed by splitting the 2024
  frame before any predictions. Classification: NON-SUBSTANTIVE (execution error, never reported as a result).
- Row-alignment risk: a post-prediction join could reorder rows and misalign numpy prediction arrays (first E1
  aggregation MAE 3.05 vs Phase 6 verified 1.735 exposed it). Fixed by moving all joins before prediction
  computation; final L0 E1 MAE 1.7352 matches Phase 6 independent build (1.7347). Classification: NON-SUBSTANTIVE.
- Bootstrap normalization: cluster-count vs PA-count normalization checked against raw deltas in every bootstrap
  before reporting (bug class previously caught in Phases 5/6; no recurrence here).
