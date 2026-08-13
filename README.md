# MLB Props

Research pipeline for pregame MLB pitcher strikeout-rate projections from
Baseball Savant data, plus a frozen projected-TBF spine and count-layer props
research. Feature engineering is Polars-first; trainers consume model-ready
parquet rather than rebuilding features.

## Repository layout

| Family | Path | Role |
|---|---|---|
| Package | `src/Python/` | Shared library (Statcast, features, pipeline L1–L3, count layer) |
| Pipeline notebooks | `src/Notebooks/` | Level inspection notebooks |
| Models | `models/` | Strikeout + TBF trainers (`train.py`), research runners (`Strikeout-Model/research/`), local results |
| Production | `production/` | Daily ops CLIs (refresh → log → grade) |
| Playground | `playground/` | Ad-hoc what-if experiments (not production) |
| Scripts | `scripts/` | One-off research/tooling CLIs |
| Tests | `tests/` | Pytest suite |
| Docs — paper | `docs/paper/` | Manuscript + figures + PDF |
| Docs — research | `docs/research/` | Step findings, experiment log, audits, phase gates |
| Docs — reference | `docs/reference/` | Model card, dev notes, lineup/live/holdout |
| Docs — diagrams | `docs/diagrams/` | Mermaid architecture / leakage / modeling / roadmap |
| Docs — archive | `docs/archive/` | Superseded process evidence |
| Data | `data/` | Savant cache + processed parquet (often local/large) |
| Artifacts | `artifacts/` | Generated models, fold CSVs, research outputs (gitignored) |

See `docs/reference/model-card.md` for intended use and leakage rules,
`docs/reference/dev-notes.md` for the current feature reference,
`docs/research/PAPER_NOTES.md` for the experiment log, and
`docs/diagrams/` for phase-colored architecture / leakage / modeling / roadmap
charts (Mermaid). Status snapshot: `docs/diagrams/00-index.md`.
Cleanup history: `docs/CLEANUP_LOG.md`.

## Pipeline

```text
raw Savant parquet
  │
  ├─ Level 1: pipeline/games.py
  │    ├─ pitcher_games.parquet
  │    ├─ pitch_type_games.parquet
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
src/Python/
├─ statcast.py            shared Savant loading, event, wOBA, discipline logic
├─ pitcher_features.py    pitch-level -> pitcher start
├─ batter_features.py     pitch-level -> batter game
├─ pitcher_rolling.py     leakage-safe pitcher form (+ rest / lagged workload)
├─ batter_rolling.py      leakage-safe batter form and hand splits
├─ ballpark.py            prior-season park-factor dimension
├─ bullpen.py             team bullpen L1–L3d lookbacks (TBF spine)
├─ tbf.py                 projected-TBF feature sets / helpers
├─ count_layer.py         expected_K + P(K ≥ line) on projected TBF
├─ reliability.py         stabilization and reliability analysis
├─ daily_lineups.py       daily predicted/confirmed lineup ingestion
├─ features.py            pregame feature safety + registries
└─ pipeline/
   ├─ games.py            Level 1 orchestration
   ├─ rolling.py          Level 2 orchestration
   └─ training.py         Level 3 joins/orchestration
```

## Setup

Python 3.11 or newer:

```powershell
py -3.11 -m venv .venv
.\activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[research,dev]"
```

The activation helper keeps project bytecode under the root `.pycache/`
instead of creating `__pycache__` folders throughout the source tree.

Set the raw Savant location if it is not under the repository's `data/`
directory:

```powershell
$env:MLB_PROPS_SAVANT_DATA_DIR = "D:\MLB-Data\Savant-Data\regular"
$env:MLB_PROPS_DATA_DIR = "D:\MLB-Data"
```

Expected source layout:

```text
regular/
├─ 2022/statcast_2022_regular.parquet  (prior-only context)
├─ 2023/statcast_2023_regular.parquet
├─ 2024/statcast_2024_regular.parquet
├─ 2025/statcast_2025_regular.parquet
└─ 2026/statcast_2026_regular.parquet  (current projection season)
```

Download and validate a season against MLB's official schedule:

```powershell
python -c "from Python.statcast import download_statcast_season; download_statcast_season(2025)"
```

Daily / in-season refresh (reuse cache; only fetch new days through yesterday ET):

```powershell
python production/ops/refresh_statcast.py
# or: python -c "from Python.statcast import update_statcast_season; print(update_statcast_season(2026))"
```

Ops CLIs for the live stack live under `production/` (not a web backend) —
see `production/README.md`.

Daily analysis loop:

1. Settle and refresh ledger: `python production/odds/grade_odds_ledger.py --auto-settle-api --void-scratches --status --curve`
2. Refresh analysis notebooks: `powershell -ExecutionPolicy Bypass -File production/ops/run_analysis_notebooks.ps1`
3. Read decision order:
   - `analysis/model_results/model_results_story.ipynb` (fast action queue)
   - `production/notebooks/results_kpi_monitor.ipynb` (fast health gate)
   - `production/notebooks/results_calibration_lab.ipynb` (matchup/rest pockets)
   - `production/notebooks/results_gate_policy.ipynb` (edge-floor simulations)
   - `production/notebooks/results_pnl_clv.ipynb` (bankroll + CLV trend)
   - `production/notebooks/results_dashboard.ipynb` (deep-dive verification)
4. Chrono recalibration winner selection is only promoted when Section 19 has
   at least `15` distinct dates.

## Build data

Run the entire pipeline:

```powershell
python -c "from Python.pipeline import run_all; run_all()"
```

Or inspect/rebuild one level at a time:

```powershell
python -m Python.pipeline.games
python -m Python.pipeline.rolling
python -m Python.pipeline.training
```

Artifacts default to `data/processed/`. Override the data root with
`MLB_PROPS_DATA_DIR`.

## Build daily projection inputs

`daily_lineups.py` combines RotoGrinders projected/confirmed batting orders
with official MLB Stats API schedule, roster, probable-pitcher, and person IDs.
Scraped names are resolved only within the corresponding official team roster;
model-facing joins use numeric MLB IDs.

```powershell
# Accept projected or confirmed lineups
python -m Python.daily_lineups

# Fail until every lineup is marked confirmed
python -m Python.daily_lineups --require-confirmed
```

The command writes dated `daily_lineups_YYYY-MM-DD.parquet` and
`daily_starters_YYYY-MM-DD.parquet` files under `data/processed/`. Every team
must have nine unique batting-order positions and resolved MLB IDs or the run
fails. RotoGrinders is an external HTML source whose markup and permitted use
must be monitored; MLB IDs remain the durable identity contract.

## Research workflow

1. Build Level 1–3 when inputs change (`python -c "from Python.pipeline import run_all; run_all()"`).
2. Train the frozen k-rate model:
   `python Models/Strikeout-Model/train.py --model lightgbm --feature-set production`.
3. Train the frozen TBF spine:
   `python Models/TBF-Model/train.py --model ridge --feature-set workload_context_bullpen`.
4. Score the count layer (expected_K + line probs):
   `python Models/Strikeout-Model/score_count_layer.py`.
5. Compare builds on nested chronological outer folds only; do not reuse scored
   2025 for selection. Pristine final eval = future post-freeze games.

Feature-research Steps 1–9 are closed for LightGBM; see `docs/research/step7_registry_freeze.md`
and `docs/research/step8_feature_keep_drop_findings.md` / `docs/research/step9_metric_window_findings.md`.

## Remaining gaps (see `docs/diagrams/04-roadmap.md`)

- **Phase 11.A–C:** done as verification (HPO flat; WF expected_K ≈ 1.78; ECE ≈
  0.024) — `docs/research/phase11_model_quality_gates.md`.
- **Phase D:** interim policy frozen (~3.5% excluded by `PA≥9`) —
  `docs/research/phase_d_population_findings.md`. Pregame role labels still open for
  pristine v1.
- **Live prediction assembly:** v1 wired (`docs/reference/live_assembly_plan.md`);
  daily ops in `production/` (incremental Statcast → features → score).
- **Pristine post-freeze holdout:** future games + role labels (not recycled 2025).
- **Exit-anomaly governance:** shipped override/mask/report loop, confidence-aware
  rolling contamination policy, and walk-forward A/B + sensitivity runners;
  current historical-tag density implies neutral aggregate deltas so far.
- **Optional later:** NB count challenger; market de-vig / Kelly; park cleanup.

Frozen and done for research: **184-feature** LightGBM production k-rate
(Step 10 P1 spine + Step 11 discipline lift), Ridge TBF
(`docs/research/tbf_first_model_findings.md`), count-layer + walk-forward stack
(`docs/research/count_layer_findings.md`). Rest/bullpen spine:
`docs/research/workload_rest_bullpen_feature_plan.md`.

## Current baseline and research surface

The production LightGBM gate is the **frozen 184-feature** registry
(`feature_set=production`; see `docs/research/step11_discipline_registry_freeze.md`).
Companion `step10_180` retains the prior 180-feature freeze and `step7_185`
retains the prior 185-feature freeze for bake-offs. Chrono test MAE / RMSE / R²
for the current production freeze ≈ 0.0780 / 0.0982 / 0.156
(`docs/research/step11_discipline_registry_freeze.md`). This is development
evidence, not an untouched final test. Next work is calibration/workload
stability and post-freeze monitoring — not more feature hunting.

Companion sets: `step7_185`, `pre_freeze_248` (comparison) and `ridge_vif`
(73-feature Ridge research). Expanded research candidates remain outside
production unless `include_experimental=True`. Generated diagnostics live under
`artifacts/feature_research/` and `artifacts/stabilization/`.

Count-layer chrono test (projected TBF): expected_K MAE ≈ **1.79**; line Briers
≈ 0.12–0.22 depending on line (`docs/research/count_layer_findings.md`).

The older date-disjoint 227-feature evaluation that consulted 2025 remains
historical benchmark evidence. The invalid overlapping-date run is retained
only under `docs/archive/leaky-baseline-2026-07-23/`.

Export a notebook to PDF through Chromium:

```powershell
.\scripts\export-notebook.ps1 "src\Notebooks\pipeline\rolling.ipynb"
```

## Tests

```powershell
python -m pytest
```

Generated files under `data/processed/` and `artifacts/` are local-only and
must not be committed. Raw source-data versioning is handled separately from
those generated-output rules.
