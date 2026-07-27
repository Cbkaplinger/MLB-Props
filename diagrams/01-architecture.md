# 01 — Architecture (as-built)

Production research path for pregame pitcher `k_rate = K / PA`. Live inference
is a side branch and does **not** feed Level 3 historical training.

```mermaid
flowchart TB
  classDef built fill:#1b5e20,stroke:#a5d6a7,color:#fff
  classDef partial fill:#e65100,stroke:#ffcc80,color:#fff
  classDef missing fill:#b71c1c,stroke:#ef9a9a,color:#fff
  classDef risk fill:#4a148c,stroke:#ce93d8,color:#fff
  classDef research fill:#0d47a1,stroke:#90caf9,color:#fff

  RAW["Raw Savant parquet<br/>2022 prior-only context<br/>2023–2025 PIPELINE_SEASONS"]:::built

  L1["Level 1 · pipeline/games.py<br/>pitcher_games · batter_games<br/>pitch_type_games · park_factors"]:::built
  L2["Level 2 · pipeline/rolling.py<br/>pitcher_rolling · batter_rolling<br/>leakage-safe prior-game form"]:::built
  L3["Level 3 · pipeline/training.py<br/>pitcher_training · batter_training<br/>lineup from batter_rolling.is_initial_lineup<br/>+ prior-season park_k_factor"]:::built

  FEAT["src/Python/features.py<br/>248-feature production safety gate"]:::built
  TRAIN["Models/Strikeout-Model/train.py<br/>Mean · Ridge · LightGBM"]:::built
  CV["Chronological date-disjoint split<br/>TRAIN_SEASONS = 2023–2024 only<br/>train ends 2024-06-08<br/>val 2024-06-09→08-05 · test from 08-06<br/>2025 = historical holdout, not pristine"]:::built
  ART["Frozen artifact<br/>artifacts/models/lightgbm_krate_YYYYMMDD_HHMMSS.{txt,json}<br/>current: lightgbm_krate_20260724_165215.*"]:::built

  DL["daily_lineups.py<br/>RotoGrinders + MLB Stats API IDs"]:::partial
  LIVE["Live prediction assembly<br/>NOT YET BUILT"]:::missing

  TBF["Projected TBF model<br/>NOT YET BUILT"]:::missing
  EXP["expected_K = pred_k_rate × projected_TBF"]:::missing
  SENS["Research sensitivity<br/>xFIP · batter shrink · park priors"]:::research
  OPEN["Open risk<br/>opener / piggyback population"]:::risk
  REG["Step 7 registry freeze<br/>BLOCKED on Steps 1 / 3 / 4 / 5"]:::missing

  RAW --> L1 --> L2 --> L3 --> FEAT --> TRAIN --> CV --> ART
  DL -.-> LIVE
  ART -.-> TBF --> EXP
  ART -.-> SENS
  ART -.-> OPEN
  ART -.-> REG
```

## Notes

- Historical opposing lineup uses `is_initial_lineup` (first nine distinct
  batters by first PA), not `daily_lineups.py`.
- Level 1 retains workload foundations (`Pitches`, `PA`, `Outs`). Level 2 keeps
  same-game `PA` / `Outs` / `K` / `k_rate` as **labels only** and drops
  `Pitches`. Lagged workload features (`PA_P*`, `Outs_P*`, `Pitches_P*`) are
  **not** produced yet — required before a TBF spine.
- `PROJECTION_SEASON = 2026` exists in config for forward park/projection work.
