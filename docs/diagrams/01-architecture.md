# 01 — Architecture (as-built)

Production research path for pregame pitcher `k_rate = K / PA`, plus the frozen
TBF → count-layer spine. Live scoring + paper trading are a **side branch** and
do **not** feed Level 3 historical training.

```mermaid
flowchart TB
  classDef built fill:#1b5e20,stroke:#a5d6a7,color:#fff
  classDef partial fill:#e65100,stroke:#ffcc80,color:#fff
  classDef missing fill:#b71c1c,stroke:#ef9a9a,color:#fff
  classDef risk fill:#4a148c,stroke:#ce93d8,color:#fff
  classDef next fill:#01579b,stroke:#81d4fa,color:#fff

  RAW["Raw Savant parquet<br/>2022 prior-only context<br/>2023–2025 PIPELINE_SEASONS"]:::built

  L1["Level 1 · pipeline/games.py<br/>pitcher_games · batter_games<br/>pitch_type_games · park_factors"]:::built
  L2["Level 2 · pipeline/rolling.py<br/>pitcher_rolling · batter_rolling<br/>+ rest · lagged PA/Outs/Pitches<br/>+ bullpen L1–L3d · P1 means"]:::built
  L3["Level 3 · pipeline/training.py<br/>pitcher_training · batter_training<br/>lineup + prior-season park_k_factor"]:::built

  FEAT["features.py + registries.py<br/>production 184 · Step 11"]:::built
  TRAIN["Models/Strikeout-Model/train.py<br/>Mean · Ridge · LightGBM"]:::built
  CV["Chronological date-disjoint split<br/>TRAIN_SEASONS = 2023–2024 only<br/>train ≤ 2024-06-08<br/>val → 2024-08-05 · test from 08-06<br/>2025 = historical, not pristine"]:::built
  ART["Frozen k-rate artifact<br/>lightgbm_krate_20260803_155401 · 184"]:::built

  TBF["Projected TBF · Models/TBF-Model<br/>Ridge + workload_context_bullpen"]:::built
  EXP["count_layer.py<br/>expected_K + P(K≥line)<br/>chrono eval DONE"]:::built

  P11["Phase 11 · model quality<br/>tune · walk-forward · calibrate DONE"]:::built
  DL["daily_lineups.py<br/>RotoGrinders + MLB IDs"]:::built
  LIVE["Live assembly + production ops<br/>log · grade · odds · CLV"]:::built
  MKT["Paper trading product<br/>SharpAPI DK/FD · tip closes"]:::partial

  OPEN["Open risk<br/>opener / piggyback population"]:::risk
  REG["Step 11 registry freeze<br/>RESOLVED · production 184"]:::built

  RAW --> L1 --> L2 --> L3 --> FEAT --> TRAIN --> CV --> ART
  L2 --> TBF --> EXP
  ART --> EXP
  ART --> P11
  TBF --> P11
  EXP --> P11
  P11 --> LIVE
  DL --> LIVE
  LIVE --> MKT
  ART -.-> OPEN
  ART --> REG
```

## Notes

- Historical opposing lineup uses `is_initial_lineup` (first nine distinct
  batters by first PA), not `daily_lineups.py`.
- Level 1 retains workload foundations (`Pitches`, `PA`, `Outs`). Level 2 emits
  lagged `PA_P*` / `Outs_P*` / `Pitches_P*`, rest flags, bullpen lookbacks, and
  mean windows including **P1** for physics stems used in Step 10.
- Workload / rest / bullpen columns are **experimental** for the k-rate gate;
  frozen LightGBM production does not consume them (they feed TBF).
- Companion feature set `step7_185` retains the pre-P1 freeze for bake-offs.
- Phase 11 gates: `docs/research/phase11_model_quality_gates.md` (done).
- Live ops: `production/README.md`; market protocol: `docs/reference/market_clv_gates.md`.
- `PROJECTION_SEASON = 2026` exists in config for forward park/projection work.
