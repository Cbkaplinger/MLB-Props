# Repository cleanup log

> **Not an instruction file.** Historical cleanup checkpoints only. For what to do next, use [`docs/EXECUTION_BACKLOG.md`](../EXECUTION_BACKLOG.md).
>
> Metric lane note: this log preserves historical checkpoints and may include
> legacy freeze values. Use `docs/reference/governance_metric_stack.md` for
> current winners and active deployment champions.

## Repo-quality passthrough â€” 2026-09-11

Low-risk hygiene only (no production deletes).

- Ignored `tmp_nb_figs/` (769 KB session PNG dump from notebook extract; regenerable).
- Removed the local `tmp_nb_figs/` files after ignore coverage.
- Retargeted SOP competing â€œnext buildâ€ line to the backlog (`go step 3`).
- Canonical map gained OpenCode handoff + golden-metrics pointers.
- Hold ledger: `docs/reference/reports/repo_quality_hold_inventory_2026-09-11.md`.
- Left protected: `src/Python/`, `production/ops|odds|projections|notebooks`, untracked research/ops scripts from pack #113, local `artifacts/**`.

---

## Repo-quality passthrough â€” 2026-09-01

Low-risk hygiene + doc consistency pass (no production deletes).

- Expanded `.gitignore` for portable `artifacts/`, caches, coverage, local MLflow dirs.
- Aligned `.cursor/skills/repo-quality-passthrough/{SKILL,reference}.md` to backlog-as-master + real smoke commands.
- Retargeted `production/{INDEX,RUNBOOK,README,notebooks/README}.md`, `docs/diagrams/*`, reports README to `docs/EXECUTION_BACKLOG.md`.
- Hold ledger: `docs/reference/reports/repo_quality_hold_inventory_2026-09-01.md`.
- Left protected: `src/Python/`, `production/ops|odds|projections|notebooks`, local `artifacts/**`, freeze-lineage research notes.

---

## Docs folder families â€” 2026-07-28 (late afternoon)

Grouped documentation into clear folder families and renamed the strikeout
research runners directory. No metrics or code logic changed; paths and
cross-references were updated.

### Moves

- Closed research write-ups â†’ `docs/research/` (`PAPER_NOTES.md`,
  `statistical_audit_and_sequencing_report.md`, `step*`, `tbf_*`,
  `count_layer_findings.md`, `phase*`)
- Living reference docs â†’ `docs/reference/` (`model-card.md`, `dev-notes.md`,
  `lineup_train_serve.md`, `live_assembly_plan.md`, `post_freeze_holdout.md`)
- `diagrams/` â†’ `docs/diagrams/`
- `models/Strikeout-Model/Strikeout-EDA/` â†’ `models/Strikeout-Model/research/`
- `docs/README.md` rewritten as the documentation family index
- Root `README.md` gained a repository-layout table

### Left in place (intentional)

- `docs/paper/`, `docs/archive/`, `docs/CLEANUP_LOG.md`
- `src/`, `production/`, `playground/`, `scripts/`, `tests/`

Runners: `scripts/reorganize_docs_families.py`,
`scripts/rename_strikeout_eda.py` (one-shot; safe to delete later).

---

Cleanup completed on 2026-07-23. The canonical package remains at
`src/Python`, the three pipeline levels and `models/Strikeout-Model/train.py`
are intact. A follow-up audit removed only redundant/generated files from
`data/` and `artifacts/`; current data, research evidence, and the frozen model
remain intact.

## Root hygiene â€” 2026-07-28 (afternoon)

No `misc/` folder. Root keeps only entry points and project metadata;
helpers and long-form notes moved into existing homes.

### Moves

- `PAPER_NOTES.md` â†’ `docs/research/PAPER_NOTES.md`
- `CLEANUP_LOG.md` â†’ `docs/CLEANUP_LOG.md` (this file)
- `export_notebook.py` â†’ `scripts/export_notebook.py`
- `export-notebook.ps1` â†’ `scripts/export-notebook.ps1`
  (script now resolves repo root as parent of `scripts/`)

### Left at repository root (intentional)

- `README.md`, `pyproject.toml`, `activate.ps1`
- `.gitignore`, `.env.example`, `.cursorindexingignore`

### Doc link updates

- `README.md`, `docs/reference/dev-notes.md`, `docs/research/statistical_audit_and_sequencing_report.md`,
  `docs/archive/leaky-baseline-2026-07-23/README.md`, and
  `models/Strikeout-Model/results/README.md` point at the new paths.

## Conservative consolidation sweep â€” 2026-07-28

Read-only audit first; then executed only approved bucket-2 and bucket-4
removals. Watch-list items (feature-importance PNG, `feature-understanding.ipynb`,
baseline snapshot, Phase 11 run logs, stabilization tree, research scripts)
were **left in place**. No changes to `src/Python` or
`models/Strikeout-Model/train.py` logic.

### Folded into documentation, then removed

- `artifacts/feature_research/step1_registries/SUMMARY.md` â€” transient runner
  summary; conclusions already in `docs/research/historical-step-findings-summary.md`
  (and Step 10 freeze size update). Added an artifact-consolidation note there.
- `artifacts/feature_research/step4_physics_windows/SUMMARY.md` â€” duplicated
  the `mean_P3_P5` verdict now in `docs/research/historical-step-findings-summary.md`.
- `artifacts/feature_research/step5_binomial/SUMMARY.md` â€” pointer-only wrapper;
  note added to `docs/research/historical-step-findings-summary.md`.
- `artifacts/feature_research/step5_beta_binomial/SUMMARY.md` â€” redundant with
  `docs/research/historical-step-findings-summary.md`.
- `artifacts/feature_research/step5_pa_weight/SUMMARY.md` â€” duplicated protocol
  and metrics already in `docs/research/historical-step-findings-summary.md`.

### Documentation sync (no unique findings lost)

- `artifacts/README.md` â€” refreshed to current freeze language (180-feature
  Step 10 LightGBM, frozen TBF Ridge, Phase 11 / Phase D / live ops paths).
- `docs/reference/dev-notes.md` â€” noted that generated `SUMMARY.md` wrappers are retired.

### Deleted outright (mechanical / byte-identical)

- All project `__pycache__/` bytecode and `.pytest_cache/` (outside `.venv`).
- `artifacts/feature_research/step9_metric_windows/production_185_frozen.csv`
  â€” byte-identical to `production_185.csv` (SHA-256
  `6bce58680a477907a81890e5a29891a685fd5d91fca56e289c1c3582ea30b8d0`).
- `artifacts/models/tbf_pa_lightgbm_workload_20260727_205600.txt` â€”
  byte-identical to `â€¦_205509.txt` (SHA-256
  `78492a5b47269e19dc12a6da3a3e468117a5004d699f763ba14b6f46cfc31552`).
- `artifacts/models/tbf_pa_lightgbm_workload_context_20260727_205556.txt` â€”
  byte-identical to `â€¦_205505.txt` (SHA-256
  `8e7e79832447f5bcd38875be4fb357f2e148a3c771f36830c89d4aba1808cedd`).

Companion JSON sidecars for the near-duplicate TBF LightGBM runs were **not**
deleted (hashes differed).

## Documentation sync â€” 2026-07-27 (evening)

Brought active docs in line with frozen k-rate (185), frozen TBF spine, and
count-layer v1. No code or artifact deletion.

Updated: `README.md`, `PAPER_NOTES.md` Â§12â€“13, `docs/reference/model-card.md`,
`docs/reference/dev-notes.md`, `docs/research/statistical_audit_and_sequencing_report.md` Part 2â€“3,
`docs/research/step5_*` / `step7` / `tbf_*` / `count_layer` next-steps,
`models/Strikeout-Model/README.md`, and `docs/diagrams/00`â€“`04` + `docs/diagrams/README.md`.

Remaining product gaps called out consistently: **Phase 11 model quality**
(tune / walk-forward / calibrate), Phase D opener, pristine post-freeze eval;
live assembly is deferred until Phase 11.
pristine post-freeze holdout, optional market/Kelly.

## Conservative consolidation sweep â€” 2026-07-27

Read-only audit first; then a conservative fold-then-remove pass. No pipeline
redesign. Watch-list items (feature-research dual checkpoints, pitch_type
near-dupes, `Model-Graphs/lgb_feature_importance.png`,
`feature-understanding.ipynb`, Step 5 run CSVs, paw diagnostic model) were
**left in place**.

### Folded into documentation, then removed

- `rules/use-polars.mdc` â€” stale always-apply Polars rule still pointing at
  retired `src/mlb_props/`. Guidance migrated to
  `.cursor/rules/use-polars.mdc` with corrected `src/Python/` paths; empty
  `rules/` directory removed.
- `src/Notebooks/pipeline/training.pdf` â€” regenerable PDF export of
  `training.ipynb` with no unique content beyond the notebook. Noted in
  `docs/reference/dev-notes.md`; recreate via `export-notebook.ps1` /
  `export_notebook.py` if needed.
- `models/Strikeout-Model/Saved-models/Model-Weights/optuna_v9.db` â€” leftover
  Optuna study DB from the pre-purge tuning era (SHA-256
  `EF5C22773235804F43B53D291073C371DC215F0677DA47F1A1425C2990775CD4`).
  Optuna workflow was already retired in the 2026-07-23 cleanup; Step 5 and
  current training do not use this file. Recorded here before removal rather
  than deleting without provenance.

### Documentation sync (no file deletion)

- `PAPER_NOTES.md` Â§12 item 5 marked done with links to
  `docs/research/step5_*_findings.md`; Â§13 clarified that projected-TBF count-layer
  beta-binomial remains future work distinct from the closed Step 5
  rate-likelihood diagnostic.

### Mechanical caches cleared (no unique content)

- `.pycache/`, `.pytest_cache/`, empty `src/mlb_props.egg-info/`, and project
  `__pycache__/` directories outside `.venv`.

## Follow-up refresh â€” 2026-07-24

- Rebuilt Levels 2-3 after adding research-only batter Z-Swing%, Swing%,
  Z-Contact%, and BB% histories.
- Regenerated the current 317-feature dictionary, missingness, correlation,
  VIF, VIF-reduction, and registry artifacts. At that checkpoint, the production gate remained 248
  features; 69 candidates require explicit research opt-in. The refreshed
  Ridge interpretation proposal contains 90 features.
- Corrected the safety/registry lifecycle so all 16 new batter-lineup columns
  remain research-only rather than silently entering the default trainer.
- Added `artifacts/README.md` to distinguish canonical current output,
  historical evidence, safe regeneration, and disposable files.
- Deleted the older `lightgbm_krate_20260724_142209.*` rerun after confirming
  its metadata was byte-identical to the retained, later
  `lightgbm_krate_20260724_165215.json`.
- Removed regenerated editable-install metadata and known test/interpreter
  cache files. The local environment and ignored cache directories remain
  disposable and are not provenance artifacts.
- Preserved all raw Savant seasons, postseason files, legacy unique source
  datasets, the unreproducible baseline snapshot, fold-level research results,
  stabilization uncertainty output, and the historical 227-feature model.
- Verification after the refresh: `python -m pytest` â€” **129 passed**; edited
  Python files have no IDE lint errors.

## Hitter expansion follow-up â€” 2026-07-24

- Rebuilt Levels 1-3 with denominator-paired batter expected stats, contact
  quality, batted-ball outcomes, and P5/P10/P20 histories.
- Added leakage-safe prior-date batting-order PA weights and lineup weighted
  standard deviations; current-game realized opportunity is never used.
- Expanded the research surface from 317 to 563 features while retaining the
  248-feature production gate. The registry now contains 315 research-only
  candidates and the refreshed Ridge proposal contains 165 features.
- Added focused batter-quality stabilization and nested family artifacts.
  Weighted plus dispersion helped LightGBM in both outer folds but hurt Ridge
  MAE in both, so no feature was promoted.
- Enriched the preserved batter-by-pitch-type research parquet to 37 columns
  without joining its unreliable run-value signals into production.
- Verification: `python -m pytest` â€” **132 passed**; edited Python files have no
  IDE lint errors.

## Files deleted

- `RosterScraper/RosterScraper.py` â€” orphaned 40-man-roster scraper; it was not
  imported, tested, documented, or suitable for the still-planned announced
  lineup workflow.
- `models/Strikeout-Model/sample_3pct.csv` â€” unreferenced model-development
  sample with no pipeline, notebook, test, or documentation consumer.
- `models/Strikeout-Model/Saved-models/Test-Predictions/test_predictions_v6_lgb.csv`
  â€” byte-for-byte duplicate of the invalid pre-pipeline v6 prediction export;
  one provenance copy was archived.
- `src/mlb_props.egg-info/PKG-INFO` â€” generated editable-install metadata,
  superseded by `pyproject.toml`.
- `src/mlb_props.egg-info/SOURCES.txt` â€” generated editable-install file list.
- `src/mlb_props.egg-info/dependency_links.txt` â€” generated editable-install
  metadata.
- `src/mlb_props.egg-info/requires.txt` â€” stale generated dependency metadata;
  the cleaned dependency list is in `pyproject.toml`.
- `src/mlb_props.egg-info/top_level.txt` â€” generated editable-install metadata.
- `artifacts/models/lightgbm_krate_20260723_194325.json` â€” metadata for a
  superseded 221-feature run.
- `artifacts/models/lightgbm_krate_20260723_194325.txt` â€” superseded
  221-feature model.
- `artifacts/models/lightgbm_krate_20260723_200557.json` â€” intermediate
  227-feature run with worse held-out performance than the frozen model.
- `artifacts/models/lightgbm_krate_20260723_200557.txt` â€” corresponding
  intermediate model.
- `artifacts/models/lightgbm_krate_20260723_201418.json` â€” intermediate
  227-feature run with worse held-out performance than the frozen model.
- `artifacts/models/lightgbm_krate_20260723_201418.txt` â€” corresponding
  intermediate model.
- `artifacts/level3-audit/mean.json` â€” byte-identical duplicate of the archived
  invalid overlapping-split Mean result.
- `artifacts/level3-audit/ridge.json` â€” byte-identical duplicate of the
  archived invalid overlapping-split Ridge result.
- `artifacts/level3-audit/lightgbm_final.txt` â€” console log for the superseded
  `194325` model, with no unique findings.
- `artifacts/notebook-exports/games.pdf` â€” unreferenced, reproducible notebook
  export.
- `data/processed/_baseline_2026-07-23/code/Python/pipeline/__pycache__/games.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/pipeline/__pycache__/rolling.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/pipeline/__pycache__/training.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/pipeline/__pycache__/__init__.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/__pycache__/ballpark.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/__pycache__/batter_features.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/__pycache__/batter_rolling.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/__pycache__/config.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/__pycache__/features.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/__pycache__/identity.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/__pycache__/pitcher_features.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/__pycache__/pitcher_rolling.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/__pycache__/reliability.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/__pycache__/statcast.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.
- `data/processed/_baseline_2026-07-23/code/Python/__pycache__/__init__.cpython-311.pyc`
  â€” generated bytecode inside the source snapshot.

Empty directories removed after their contents were cleaned:
`artifacts/optuna/`, `artifacts/predictions/`, `artifacts/shap/`,
`artifacts/notebook-exports/`, and the two snapshot `__pycache__/`
directories.

No notebook was deleted. All 13 notebooks have distinct audit, reasoning, or
integration value, including the 11 previously verified notebooks and the
newer `train.ipynb` and `stabilization.ipynb`.

## Files moved, archived, or consolidated

- `models/Strikeout-Model/results/_baseline_2026-07-23/mean.json` ->
  `docs/archive/leaky-baseline-2026-07-23/mean.json`
- `models/Strikeout-Model/results/_baseline_2026-07-23/ridge.json` ->
  `docs/archive/leaky-baseline-2026-07-23/ridge.json`
- `models/Strikeout-Model/results/_baseline_2026-07-23/GIT_STATE.txt` ->
  `docs/archive/leaky-baseline-2026-07-23/GIT_STATE.txt`
- `models/Strikeout-Model/Shap-Tables/shap_table_v6_lgb.csv` ->
  `docs/archive/pre-pipeline-v6/shap_table_v6_lgb.csv`
- `models/Strikeout-Model/results/Test-Predictions/test_predictions_v6_lgb.csv`
  -> `docs/archive/pre-pipeline-v6/test_predictions_v6_lgb.csv`
- Environment specifications remain consolidated in `pyproject.toml`;
  `activate.ps1` remains the activation helper. Removed unused dependencies:
  `requests`, `optuna`, `shap`, `tqdm`, and `xgboost`. Added the directly
  imported `nbconvert` dependency; `beautifulsoup4` is now a core dependency
  for the replacement ID-safe daily lineup adapter.
- `src/Python/config.py` was consolidated around current outputs by removing
  the orphan roster path and unused prediction/SHAP/Optuna output constants.

Each archive directory now has a README explaining what the files were, why
they were superseded, and what replaced them.

## Data and artifact follow-up audit

- Kept `data/Savant-data/regular/2022` through `2025` as the current pipeline
  inputs, including prior-only 2022 context.
- Kept regular 2015-2021, all postseason inputs, and the legacy
  `Pitcher-Starts-2023-2025-data/` and
  `DailyPitcherModelTrainingData.csv`. They are unreferenced by the current
  K/PA pipeline, but they are unique source data rather than generated output
  and may support preserved future targets; deleting them would sacrifice
  historical coverage.
- Kept every live Level 1-3 parquet and the full
  `data/processed/_baseline_2026-07-23/` evidence snapshot except accidental
  bytecode. Current code cannot byte-reproduce that snapshot.
- Kept all 331 stabilization outputs and all feature-research outputs because
  they support findings in `PAPER_NOTES.md`.
- Kept `artifacts/models/lightgbm_krate_20260723_202255.{json,txt}` as the
  current frozen 227-feature model.
- Kept the remaining four Level 3 audit JSONs because they are the only local
  copies of their date-disjoint/interim Mean and Ridge evaluations.
- Provenance warning: neither the live nor local baseline pitcher/batter
  training parquet matches the training SHA-256 values recorded in
  `PAPER_NOTES.md`. The frozen model's ordered-feature hash remains
  recoverable from its JSON, but the exact hashed training frames are not
  currently present. The baseline snapshot was therefore preserved.

## Documentation contradictions resolved

- **Overlapping vs date-disjoint baseline:** The old Mean/Ridge run used
  overlapping boundary dates (train through 2025-04-15; validation and test
  both included 2025-07-06). It is now explicitly archived as invalid process
  history. All active docs use the corrected split: train through 2025-04-14,
  validation 2025-04-15 through 2025-07-05, test from 2025-07-06.
- **Baseline metrics:** Active docs now consistently report test RMSE / RÂ² of
  0.1076 / -0.0001 (Mean), 0.1003 / 0.1313 (Ridge), and 0.0994 / 0.1459
  (LightGBM).
- **Feature counts:** The frozen production-evidence baseline is identified as
  227 features. The 214 core, 219 compact, 227 preferred-raw, and 232
  all-candidate research frames are labeled as later development screens, not
  replacements for the frozen baseline.
- **Lineup Whiff% vs SwStr%:** Docs now distinguish Whiff% =
  `Whiffs/Swings` from SwStr% = `Whiffs/Pitches`. The frozen 227-feature
  baseline contains `opp_lineup_whiff`; `opp_lineup_swstr` is a later research
  candidate.
- **Stabilization status:** Statements saying stabilization had not run were
  replaced. The study is complete, but it did not alone justify changing the
  current 5/10/20 rate and 3/5/10 physics windows.
- **Ablation freshness:** The protected family/window results are retained as
  development evidence but now carry a clear warning that they predate
  denominator-weighted expected-stat corrections and splitter propagation.
- **Prior constants:** The docs consistently retain the current
  1,000-fly-ball xFIP regression prior and sourced 2022 HR/FB/K-rate boundary
  context; no stale alternate strength remains.
- **Test counts:** The live verification section reports the current 108-test
  suite. Older 89-test counts remain only inside dated bug-log entries, and
  the former stale 96-test inventory was replaced with a complete
  coverage-based description including `tests/test_train.py`.
- **Level 1 inventory:** `pitch_type_games.parquet` and the prior-only 2022
  Savant input are now included in pipeline/data documentation.
- **Stale result paths:** Model-result docs now point to `docs/archive/` and
  the corrected frozen LightGBM artifact. The unsupported claim that a v6
  prediction CSV represented current holdout evidence was removed.
- **EDA inventory:** The EDA README now lists both notebooks, both
  stabilization runners, and the feature/window ablation scripts.
- **Current limitations:** Removed the stale working-tree-state limitation and
  aligned active limitations around incomplete TBF/prop modeling, announced
  lineups, interactions, external context, neutral-site park contamination,
  and the required rebuilt-frame ablation rerun.
- **Data versioning wording:** README files now distinguish generated
  `data/processed/` outputs from raw source-data versioning instead of claiming
  that every file under `data/` is ignored.
- **Future targets:** `docs/reference/dev-notes.md` now explains why Level 1 outcomes and
  reliability denominator plans for hits, walks, runs allowed, pitches, outs,
  and batters faced are intentionally preserved.

## `.gitignore` rules added

- `venv/`
- `**/venv/`
- `env/`
- `**/env/`
- `.env`
- `.vscode/`
- `.idea/`

Existing rules already covered `data/processed/`, `artifacts/`, `.venv/`,
`.ipynb_checkpoints/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, and
`.DS_Store`. No blanket `data/`, CSV, parquet, source, test, notebook, or
documentation ignore was added.

## Verification

- `python -m pytest`: **108 passed**.
- IDE lint check for `src/Python/config.py`: no errors.
- Reference searches found no remaining uses of removed config constants,
  scraper paths, sample data, stale active baseline paths, or the removed
  SHAP/XGBoost workflow wording.
- The two v6 prediction exports had the same SHA-256
  (`E18DC197B250CAA7A592F4A4D1C0FD52A2ACD5500CC346E729B45B58D7E4292A`)
  before duplicate removal.
- Follow-up data/artifact audit preserved all current pipeline outputs, regular
  2022-2025 Savant inputs, historical source data, stabilization outputs,
  feature-research evidence, the baseline data snapshot, and
  `lightgbm_krate_20260723_202255.*`. Only compiled bytecode, duplicate audit
  JSONs, superseded model runs, an orphan export, and empty artifact
  directories were removed.

## Historical post-cleanup directory tree (2026-07-23)

This tree records the first cleanup checkpoint and is not maintained as a live
inventory. See the active root/data/model READMEs and `artifacts/README.md` for
the current layout and lifecycle. Generated caches and the local `.venv/` are
shown as local-only entries; large untouched data/artifact subtrees are
summarized.

```text
MLB-Props/
â”œâ”€â”€ .cursorindexingignore
â”œâ”€â”€ .env.example
â”œâ”€â”€ .gitignore
â”œâ”€â”€ CLEANUP_LOG.md
â”œâ”€â”€ PAPER_NOTES.md
â”œâ”€â”€ README.md
â”œâ”€â”€ activate.ps1
â”œâ”€â”€ export-notebook.ps1
â”œâ”€â”€ export_notebook.py
â”œâ”€â”€ pyproject.toml
â”œâ”€â”€ data/
â”‚   â”œâ”€â”€ README.md
â”‚   â”œâ”€â”€ Savant-data/
â”‚   â”‚   â”œâ”€â”€ regular/                   [season parquet sources]
â”‚   â”‚   â””â”€â”€ postseason/                [season parquet sources]
â”‚   â”œâ”€â”€ dimensions/                    [local generated dimension]
â”‚   â”œâ”€â”€ processed/                     [local Level 1-3 outputs]
â”‚   â”œâ”€â”€ Pitcher-Starts-2023-2025-data/ [legacy source data preserved]
â”‚   â””â”€â”€ DailyPitcherModelTrainingData.csv
â”œâ”€â”€ models/
â”‚   â””â”€â”€ Strikeout-Model/
â”‚       â”œâ”€â”€ README.md
â”‚       â”œâ”€â”€ train.py
â”‚       â”œâ”€â”€ train.ipynb
â”‚       â”œâ”€â”€ Strikeout-EDA/
â”‚       â”‚   â”œâ”€â”€ README.md
â”‚       â”‚   â”œâ”€â”€ strikeout-eda.ipynb
â”‚       â”‚   â”œâ”€â”€ stabilization.ipynb
â”‚       â”‚   â”œâ”€â”€ run_stabilization.py
â”‚       â”‚   â”œâ”€â”€ run_pitch_type_stabilization.py
â”‚       â”‚   â”œâ”€â”€ feature_ablation.py
â”‚       â”‚   â””â”€â”€ window_ablation.py
â”‚       â”œâ”€â”€ Model-Graphs/               [ignored generated output]
â”‚       â”œâ”€â”€ Saved-models/               [ignored generated output]
â”‚       â””â”€â”€ results/
â”‚           â”œâ”€â”€ README.md
â”‚           â””â”€â”€ Test-Predictions/       [ignored generated output]
â”œâ”€â”€ artifacts/
â”‚   â”œâ”€â”€ feature_research/
â”‚   â”œâ”€â”€ level3-audit/
â”‚   â”œâ”€â”€ models/
â”‚   â””â”€â”€ stabilization/
â”œâ”€â”€ docs/
â”‚   â”œâ”€â”€ dev-notes.md
â”‚   â”œâ”€â”€ model-card.md
â”‚   â””â”€â”€ archive/
â”‚       â”œâ”€â”€ leaky-baseline-2026-07-23/
â”‚       â”‚   â”œâ”€â”€ README.md
â”‚       â”‚   â”œâ”€â”€ GIT_STATE.txt
â”‚       â”‚   â”œâ”€â”€ mean.json
â”‚       â”‚   â””â”€â”€ ridge.json
â”‚       â””â”€â”€ pre-pipeline-v6/
â”‚           â”œâ”€â”€ README.md
â”‚           â”œâ”€â”€ shap_table_v6_lgb.csv
â”‚           â””â”€â”€ test_predictions_v6_lgb.csv
â”œâ”€â”€ rules/
â”‚   â””â”€â”€ use-polars.mdc
â”œâ”€â”€ src/
â”‚   â”œâ”€â”€ Python/
â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”œâ”€â”€ ballpark.py
â”‚   â”‚   â”œâ”€â”€ batter_features.py
â”‚   â”‚   â”œâ”€â”€ batter_rolling.py
â”‚   â”‚   â”œâ”€â”€ config.py
â”‚   â”‚   â”œâ”€â”€ daily_lineups.py
â”‚   â”‚   â”œâ”€â”€ features.py
â”‚   â”‚   â”œâ”€â”€ identity.py
â”‚   â”‚   â”œâ”€â”€ pitcher_features.py
â”‚   â”‚   â”œâ”€â”€ pitcher_rolling.py
â”‚   â”‚   â”œâ”€â”€ reliability.py
â”‚   â”‚   â”œâ”€â”€ statcast.py
â”‚   â”‚   â””â”€â”€ pipeline/
â”‚   â”‚       â”œâ”€â”€ __init__.py
â”‚   â”‚       â”œâ”€â”€ games.py
â”‚   â”‚       â”œâ”€â”€ rolling.py
â”‚   â”‚       â””â”€â”€ training.py
â”‚   â””â”€â”€ Notebooks/
â”‚       â”œâ”€â”€ ballpark.ipynb
â”‚       â”œâ”€â”€ batter-features.ipynb
â”‚       â”œâ”€â”€ batter_rolling.ipynb
â”‚       â”œâ”€â”€ features.ipynb
â”‚       â”œâ”€â”€ pitcher-features.ipynb
â”‚       â”œâ”€â”€ pitcher-rolling.ipynb
â”‚       â”œâ”€â”€ statcast.ipynb
â”‚       â””â”€â”€ pipeline/
â”‚           â”œâ”€â”€ games.ipynb
â”‚           â”œâ”€â”€ rolling.ipynb
â”‚           â”œâ”€â”€ training.ipynb
â”‚           â””â”€â”€ training.pdf
â”œâ”€â”€ tests/
â”‚   â”œâ”€â”€ test_ballpark.py
â”‚   â”œâ”€â”€ test_batter_features.py
â”‚   â”œâ”€â”€ test_batter_rolling.py
â”‚   â”œâ”€â”€ test_daily_lineups.py
â”‚   â”œâ”€â”€ test_feature_safety.py
â”‚   â”œâ”€â”€ test_identity.py
â”‚   â”œâ”€â”€ test_pipeline.py
â”‚   â”œâ”€â”€ test_pitcher_features.py
â”‚   â”œâ”€â”€ test_pitcher_rolling.py
â”‚   â”œâ”€â”€ test_reliability.py
â”‚   â”œâ”€â”€ test_stabilization.py
â”‚   â”œâ”€â”€ test_statcast.py
â”‚   â””â”€â”€ test_train.py
â”œâ”€â”€ .pycache/                           [ignored local cache]
â”œâ”€â”€ .pytest_cache/                      [ignored local cache]
â””â”€â”€ .venv/                              [ignored local environment]
```

## Documentation sync â€” 2026-07-31

Brought living docs in line with shipped live ops + paper-trading / CLV
(SharpAPI DK/FD, tip-window closes, morning board). No code changes in this
pass.

Updated: root `README.md`, `production/README.md`, `docs/README.md`,
`docs/reference/{market_clv_gates,live_assembly_plan,model-card,dev-notes,
lineup_train_serve,research_assistant_instructions}.md`,
`docs/diagrams/{00-index,01-architecture,04-roadmap,README}.md`,
`playground/README.md`, `models/{Strikeout-Model,TBF-Model}/README.md`.

Left as historical: closed `docs/research/step*` / phase write-ups and the
modeling manuscript (product-layer non-goals remain intentional for the paper).
