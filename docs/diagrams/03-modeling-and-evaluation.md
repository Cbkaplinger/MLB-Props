# 03 — Modeling and evaluation status

Chronological evaluation of the strikeout-rate model, research gates through
the Step 10 feature freeze, and **Phase 11** model-quality work that comes next.

```mermaid
flowchart TB
  classDef built fill:#1b5e20,stroke:#a5d6a7,color:#fff
  classDef partial fill:#e65100,stroke:#ffcc80,color:#fff
  classDef missing fill:#b71c1c,stroke:#ef9a9a,color:#fff
  classDef risk fill:#4a148c,stroke:#ce93d8,color:#fff
  classDef next fill:#01579b,stroke:#81d4fa,color:#fff

  SEAS["TRAIN_SEASONS = (2023, 2024)<br/>filtered before any split / fit"]:::built
  SPLIT["Chrono date-disjoint ≈ 70/15/15<br/>train ≤ 2024-06-08<br/>val → 2024-08-05<br/>test ≥ 2024-08-06"]:::built
  NEST["Nested research folds<br/>outer 2024 h1/h2 · inner ⊂ train"]:::built

  LGBM["LightGBM production 180<br/>Step 10 P1 · test MAE≈0.079"]:::built
  TBF["TBF Ridge thin bullpen<br/>test MAE≈2.49"]:::built
  CNT["Count layer<br/>expected_K MAE≈1.79"]:::built
  HOLD["2025 = historical only<br/>already consulted · not pristine"]:::risk

  S1["Steps 1–5: dict · LFO · windows · likelihoods"]:::built
  S7["Step 7: freeze 185"]:::built
  S89["Steps 8–9c: keep/drop · windows · P1"]:::built
  S10["Step 10: lock production 180"]:::built

  TUNE["11.A Tune LGBM + Ridge α"]:::next
  WF["11.B Walk-forward stack backtest"]:::next
  CAL["11.C Calibration / ECE"]:::next
  NEXT["Pristine test =<br/>future post-freeze games"]:::missing

  SEAS --> SPLIT
  SPLIT --> LGBM
  SPLIT --> TBF
  SPLIT --> HOLD
  NEST --> S1
  S1 --> S7 --> S89 --> S10
  S10 --> LGBM
  LGBM --> TBF --> CNT
  S10 --> TUNE --> WF --> CAL
  CNT --> WF
  CAL --> NEXT
```

## Notes

- Nested folds: `models/Strikeout-Model/research/nested_cv.py`.
- Production chrono split: `Python.training.chronological_split`.
- Keep **unweighted** LightGBM (`--sample-weight none`); PA-weight is diagnostic.
- Count metrics: prefer **Brier / log loss** over accuracy
  (`Python.count_layer.line_market_metrics`).
- Phase 11 plan: `docs/research/phase11_model_quality_gates.md`.
- Freeze record: `docs/research/step10_p1_registry_freeze.md`.
- Archived leaky baselines: `docs/archive/leaky-baseline-2026-07-23/`.
