# MLB Props

Research pipeline for pregame MLB pitcher strikeout-rate projections from
Baseball Savant data. Feature engineering is Polars-first; the training script
consumes a model-ready parquet rather than rebuilding features.

See `docs/model-card.md` for intended use and leakage rules and
`docs/dev-notes.md` for the current feature reference.

## Pipeline

```text
raw Savant parquet
  │
  ├─ Level 1: pipeline/games.py
  │    ├─ pitcher_games.parquet
  │    ├─ batter_games.parquet
  │    └─ park_factors.parquet
  │
  ├─ Level 2: pipeline/rolling.py
  │    ├─ pitcher_rolling.parquet
  │    └─ batter_rolling.parquet
  │
  └─ Level 3: pipeline/training.py
       ├─ pitcher_training.parquet
       └─ batter_training.parquet
```

Level 1 groups pitch-level data into auditable game records. Level 2 produces
pregame rolling/season-to-date player form and retains static game context.
Level 3 joins opponent-lineup and prior-season park context.
`Models/Strikeout-Model/train.py` reads `pitcher_training.parquet`.

Key modules:

```text
src/mlb_props/
├─ statcast.py            shared Savant loading, event, wOBA, discipline logic
├─ pitcher_features.py    pitch-level -> pitcher start
├─ batter_features.py     pitch-level -> batter game
├─ pitcher_rolling.py     leakage-safe pitcher form
├─ batter_rolling.py      leakage-safe batter form and hand splits
├─ ballpark.py            prior-season park-factor dimension
├─ reliability.py         stabilization and reliability analysis
├─ features.py            pregame feature safety
└─ pipeline/
   ├─ games.py            Level 1 orchestration
   ├─ rolling.py          Level 2 orchestration
   └─ training.py         Level 3 joins/orchestration
```

## Setup

Python 3.11 or newer:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[research,dev]"
```

Set the raw Savant location if it is not under the repository's `Data/`
directory:

```powershell
$env:MLB_PROPS_SAVANT_DATA_DIR = "D:\MLB-Data\Savant-Data\regular"
$env:MLB_PROPS_DATA_DIR = "D:\MLB-Data"
```

Expected source layout:

```text
regular/
├─ 2023/statcast_2023_regular.parquet
├─ 2024/statcast_2024_regular.parquet
└─ 2025/statcast_2025_regular.parquet
```

## Build data

Run the entire pipeline:

```powershell
python -c "from mlb_props.pipeline import run_all; run_all()"
```

Or inspect/rebuild one level at a time:

```powershell
python -m mlb_props.pipeline.games
python -m mlb_props.pipeline.rolling
python -m mlb_props.pipeline.training
```

Artifacts default to `Data/processed/`. Override the data root with
`MLB_PROPS_DATA_DIR`.

## Research workflow

1. Build Level 1 and run the EDA/stabilization notebook.
2. Update rolling-window constants from denominator-aware stabilization.
3. Build Levels 2 and 3.
4. Train chronologically with
   `python Models/Strikeout-Model/train.py --model lightgbm`.
5. Use SHAP/CV to remove redundant windows and features.
6. Record a frozen leakage-free baseline before developing a TBF/prop layer.

## Tests

```powershell
python -m pytest
```

Data and generated artifacts are local-only and must not be committed.
