# MLB Props

Production-first MLB pitcher strikeout props stack with a frozen operating
profile (`KING_PROFILE_AUG2026`), execution/research gate split, and board to
ledger parity lock.

## Current source of truth

- **Work queue / agent plan:** [`docs/EXECUTION_BACKLOG.md`](docs/EXECUTION_BACKLOG.md) (holy file — open first; see also [`AGENTS.md`](AGENTS.md))
- Code repository: [github.com/Cbkaplinger/MLB-Props](https://github.com/Cbkaplinger/MLB-Props)
- Paper: [Technical manuscript (`docs/paper/manuscript.md`)](docs/paper/manuscript.md)
- Daily operations: `production/README.md`
- Command routing: `production/INDEX.md`, `production/RUNBOOK.md`
- Governance policy: `production/ops/kpi_policy.json`
- Model card: `docs/reference/model-card.md`

## Active architecture

- `src/Python/`: canonical pipeline and model assembly modules (Polars-first)
- `production/`: live scoring, recommendation board, polling, grading, governance
- `models/`: trainers and model research notebooks
- `production/notebooks/`: operator-facing notebook surfaces
- `docs/reference/`: living operational standards
- `docs/research/`: supporting evidence and historical rationale

## Active vs legacy (quick split)

- Active production path (use this): `production/`, `src/Python/`, `production/ops/kpi_policy.json`, `production/ops/live_krate_ensemble.json`.
- Active publication path (use this): `docs/paper/manuscript.md`, `docs/paper/resume-summary.md`, `docs/reference/`.
- Legacy/historical context (reference only): older freeze snapshots, archived comparisons, and superseded research notes in `docs/research/` and `docs/archive/`.
- Rule: if a file is not used by a scheduled task, `production/INDEX.md`, or `production/RUNBOOK.md`, treat it as non-operational.

## Next prop expansion: pitcher outs

- Keep strikeouts as the golden production lane; do not change strikeout governance to prototype outs.
- Reuse existing stack components:
  - data contracts (`game_date`, `player_name`, `book`, `line`, `event_start_time`)
  - watcher open/close capture loop
  - ledger settle pipeline and daily KPI automation
  - dashboard/runtime monitoring and alerting
- Current shadow artifacts for non-K props:
  - `artifacts/odds_log/watcher_aux_quotes.parquet`
  - `artifacts/odds_log/aux_market_shadow_prop_level.parquet`
  - `artifacts/odds_log/aux_market_shadow_summary.json`
- Promotion sequence for outs: collect -> shadow score/CLV diagnostics -> build leakage-safe model -> run governance lane in shadow -> consider production profile only after sample and risk gates pass.

## Daily operator loop

1. Refresh data and features.
2. Build recommendations with current production policy.
3. Poll open odds from recommendations (`--from-recommendations` parity lock).
4. Generate governance and reconciliation artifacts.
5. Settle and monitor ledger health.

## Legacy / deprecated guidance

- `src/Notebooks/` and research notebooks remain available for inspection, but
  they are not the canonical daily execution path.
- Historical strategy writeups are retained for provenance; active decisions
  should follow `production/` and `docs/reference/`.

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
`models/Strikeout-Model/train.py` reads `pitcher_training.parquet`.

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

Current production scoring posture:

- Live k-rate scoring uses ensemble config:
  `production/ops/live_krate_ensemble.json`
- Recommendation generation defaults to conservative policy mode:
  `production/odds/odds_board.py --roi-mode conservative`

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
   `python models/Strikeout-Model/train.py --model lightgbm --feature-set production`.
3. Train the frozen TBF spine:
   `python models/TBF-Model/train.py --model ridge --feature-set workload_context_bullpen`.
4. Score the count layer (expected_K + line probs):
   `python models/Strikeout-Model/score_count_layer.py`.
5. Compare builds on nested chronological outer folds only; do not reuse scored
   2025 for selection. Pristine final eval = future post-freeze games.

Feature-research Steps 1–9 are closed for LightGBM; see
`docs/research/historical-step-findings-summary.md` and
`docs/research/step7_registry_freeze.md`.
The current expanded freeze decision and consensus-search evidence are documented in
`docs/research/snapshots/2026-08-20/final58_consensus_freeze.md`.

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

Current production k-rate path is an **ensemble** selected from deduped manual
replay after open-data calibration transfer:

- `0.00 production_sparse72 + 0.60 production_sparse72_monotone + 0.40 production_final58_consensus`
- config: `production/ops/live_krate_ensemble.json`
- runtime scorer: `src/Python/live_assembly.py` (single-model fallback retained)

Ridge TBF (`docs/research/tbf_first_model_findings.md`) and count-layer stack
(`docs/research/count_layer_findings.md`) remain unchanged.

## Current baseline and research surface

The active governance surface includes single-model and ensemble lanes. Current
manual-lane winner uses the live ensemble config above; open-universe skill lane
still tracks `production_sparse72 + isotonic` for market-skill monitoring.
Prior freeze registries (`production`, `step10_180`, `step7_185`) remain
available for backtests and comparisons.

### Metric lane definitions (important)

- **Single-model MAE lane:** accuracy-first lane tracked in model-family ablation
  outputs. Current best observed `mean_expected_k_mae` is about **1.7621**.
- **Ensemble deployment lane:** active king selected from deduped/manual transfer
  governance on decision metrics (ROI, risk-adjusted path, market-skill deltas),
  not by expected-K MAE rank in the ensemble sweep artifact.
- **Legacy baselines:** historical freeze-era benchmark metrics are archived for
  auditability and are not used as current production claims.

Companion sets and legacy registries are retained for provenance and backtests
only (`step7_185`, `pre_freeze_248`, `ridge_vif`), while production promotion
follows the metric lanes above.

### Current winners (artifact-backed)

- **Single-model MAE lane winner:** `mean_expected_k_mae=1.7621`
  (Ridge on `production_sparse72`, tied by lane with
  `production_sparse72_monotone` in current governance notes).
- **Active deployment king (deduped transfer lane):**
  `0.00 sparse72 / 0.60 sparse72_monotone / 0.40 final58`,
  `isotonic`, `edge_floor=0.12`, with current replay metrics:
  `ROI=0.4363`, `PnL=1208.55`, `Sharpe=0.4438`, `Sortino=0.4277`,
  `Brier skill=+0.2069`, `LogLoss skill=+0.1551`.
- **Open-universe deduped sweep top profile:** `0.05 sparse72 / 0.45 sparse72_monotone / 0.50 final58`,
  `ROI=0.6612`, `Sharpe=0.9468`, `Sortino=0.6954`,
  `Brier skill=+0.0825`, `LogLoss skill=+0.0645`.

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
