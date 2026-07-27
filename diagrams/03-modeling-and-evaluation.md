# 03 — Modeling and evaluation status

Chronological evaluation of the strikeout-rate model, plus research-step gates
before registry freeze.

```mermaid
flowchart TB
  classDef built fill:#1b5e20,stroke:#a5d6a7,color:#fff
  classDef partial fill:#e65100,stroke:#ffcc80,color:#fff
  classDef missing fill:#b71c1c,stroke:#ef9a9a,color:#fff
  classDef risk fill:#4a148c,stroke:#ce93d8,color:#fff
  classDef research fill:#0d47a1,stroke:#90caf9,color:#fff

  SEAS["TRAIN_SEASONS = (2023, 2024)<br/>filtered in train.py before any split / fit"]:::built
  SPLIT["Chrono date-disjoint split ≈ 70/15/15<br/>train ends 2024-06-08<br/>val 2024-06-09 → 2024-08-05<br/>test from 2024-08-06"]:::built

  MEAN["Mean<br/>RMSE 0.1070 · R² −0.0010"]:::built
  RIDGE["Ridge<br/>RMSE 0.0993 · R² 0.1378"]:::built
  LGBM["LightGBM<br/>RMSE 0.0983 · R² 0.1546"]:::built
  HOLD["2025 = historical holdout<br/>already consulted · not pristine"]:::risk

  S1["Step 1: feature dict / VIF<br/>IN PROGRESS"]:::partial
  S3["Step 3: grouped ablations<br/>most families untested"]:::partial
  S4["Step 4: windows provisional<br/>BABIP / arm-angle / Ridge RV"]:::partial
  S5["Step 5: unweighted vs PA-weighted<br/>vs binomial / beta-binomial<br/>NOT STARTED"]:::missing

  S7["Step 7: registry freeze<br/>BLOCKED until Steps 1 / 3 / 4 / 5 resolve"]:::missing
  NEXT["Next pristine test =<br/>future post-freeze games only"]:::missing

  SEAS --> SPLIT
  SPLIT --> MEAN
  SPLIT --> RIDGE
  SPLIT --> LGBM
  SPLIT --> HOLD

  S1 --> S7
  S3 --> S7
  S4 --> S7
  S5 --> S7
  S7 --> NEXT
```

## Notes

- Nested selection/confirmation folds live in
  `Models/Strikeout-Model/Strikeout-EDA/nested_cv.py`
  (`nested_research_folds`).
- Current `train.py` fits **unweighted** game-level `k_rate`. `PA` is retained
  as a label and can become `sample_weight` without a Level 1/2 rebuild.
- Older overlapping-date / 2025-consulting baselines are archived under
  `docs/archive/leaky-baseline-2026-07-23/`.
