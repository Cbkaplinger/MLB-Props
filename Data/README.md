# Local data layout

Generated parquet artifacts under `Data/processed/` and the player-ID
dimension under `Data/dimensions/` are excluded from Git. Raw source-data
versioning is handled separately.

```text
Data/
├─ Savant-Data/
│  └─ regular/
│     ├─ 2022/statcast_2022_regular.parquet
│     ├─ 2023/statcast_2023_regular.parquet
│     ├─ 2024/statcast_2024_regular.parquet
│     └─ 2025/statcast_2025_regular.parquet
└─ processed/
   ├─ pitcher_games.parquet
   ├─ pitch_type_games.parquet
   ├─ batter_games.parquet
   ├─ park_factors.parquet
   ├─ pitcher_rolling.parquet
   ├─ batter_rolling.parquet
   ├─ pitcher_training.parquet
   ├─ batter_training.parquet
   ├─ daily_lineups_YYYY-MM-DD.parquet
   └─ daily_starters_YYYY-MM-DD.parquet
```

The live eight Level 1-3 parquet files are canonical generated outputs and may
be rebuilt in dependency order. `processed/_baseline_2026-07-23/` is a
provenance snapshot whose exact historical frames cannot currently be
byte-reproduced; it is intentionally retained and must not be mixed with live
pipeline inputs.

Set `MLB_PROPS_DATA_DIR` to relocate the whole data root or
`MLB_PROPS_SAVANT_DATA_DIR` to point directly at the regular-season source
folders. All processed paths derive from `MLB_PROPS_DATA_DIR`.

Level 1 writes game tables and the park dimension, Level 2 writes player-form
tables, and Level 3 writes model-ready tables. Do not manually copy or rename
artifacts between levels.

`python -m Python.daily_lineups` writes the dated daily files after combining
RotoGrinders batting orders with official MLB game, roster, and person IDs.
These are live projection inputs rather than a fourth historical pipeline
level.

The 2022 file is prior-only context: it supplies the exact-definition league
HR/FB and K-rate priors plus park history for 2023. Model rows still begin in
2023.

Older regular seasons, postseason Savant files,
`Pitcher-Starts-2023-2025-Data/`, and
`DailyPitcherModelTrainingData.csv` are not consumed by the current K/PA
pipeline. They are preserved source data—not stale generated output—because
their outcomes and longer history may support future hits, outs, walks,
pitches, earned-runs, and batters-faced models.
