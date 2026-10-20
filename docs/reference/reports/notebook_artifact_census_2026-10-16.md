# Notebook and artifact census — 2026-10-16 (Chat 3, report-first)

Scope: all 22 tracked notebooks + every tracked generated/binary artifact at
`origin/main` @ `1927c8c…` (809 files, 27.4 MB total). Method: path/extension
classification over the tracked tree + caller cross-reference + size ranking.
Confidence: HIGH on inventory facts, MEDIUM on "reproducible" judgments (not
re-executed). **Nothing moved or deleted.**

## Notebooks (22)

| Group | Files | Callers (evidence) | Class | Disposition |
|---|---|---|---|---|
| `production/notebooks/daily_projections + results_{kpi_monitor,pnl_clv,bettable_cohort,calibration_lab,recommendation_audit,dashboard}` | 7 | operator flow `.ps1`, RUNBOOK, canonical map | canonical operational (with executed outputs committed) | keep; outputs refreshed per ops runs |
| `production/notebooks/_notebook_score.py` companion + remaining `production/notebooks` helpers | 3 | ops tooling | operational | keep |
| `src/Notebooks/*` (ballpark, batter-features, batter_rolling, features, games, pitcher-features, pitcher-rolling, rolling, statcast, pipeline/training) | ~10 | historical docs only (CLEANUP_LOG era) | **lineage/reproducibility archive** | candidate group for archive-with-manifest (backlog T11); caller-validate first |
| `models/**` (train, stabilization, strikeout-eda, ablation notebooks) | 4 | sparse doc refs | research lineage | keep; part of model provenance |

## Generated/binary artifacts (tracked)

| Group | Count | Class | Disposition |
|---|---|---|---|
| `models/**` boosters/sidecars/jobs | 79 | immutable evidence (frozen model provenance; hashes recorded in audits) | keep in Git; never regenerate silently |
| `research/offseason_2026/datasets/*.parquet` + manifests | ~10 | canonical evidence (sha256-pinned inputs to experiments) | keep; already manifest-linked |
| `research/**/experiments/**` JSON/MD cards | ~100 | frozen evidence | keep; results index (PR #8) is their front door |
| `docs/paper/figures/*.png` + `manuscript.{pdf,html}` | ~15 | reproducible generated outputs (from `make_figures.py` / render scripts) | keep tracked for paper provenance; regenerate-on-demand documented |
| `production/notebooks/*.ipynb` executed outputs | embedded | reproducible operational outputs | keep; `check_notebook_artifacts.py` guards |
| `report/`, `analysis/` CSV/HTML | few | mixed reproducible/unknown | classify per-file in a future slice if consolidation is approved |

## Large files (top by bytes)

Largest tracked files are paper PDFs/HTML and figure PNGs (hundreds of KB each)
plus the dataset parquets — **nothing approaches a size problem** (27.4 MB total).
No tracked artifact needs lake migration on size grounds; the lake/Git boundary
is already correctly drawn (outputs + forecasts in lake; manifests/hashes in
Git — verified working in the B1 closeout pattern).

## Findings

1. **No cache/temp junk tracked** — `.venv`, `data/`, `artifacts/`, `.hypothesis`,
   `.pytest_cache` are ignored; the single ignored-but-tracked file
   (`data/Pitcher-Starts-2023-2025-Data/README.md`) is an intentional negation.
2. **`src/Notebooks/` group is the only genuine archival candidate** — zero
   operational callers, superseded by the `src/Python` pipeline they predate.
   Evidence attached in the dead-code audit; action deferred to backlog T11.
3. **Every tracked artifact class has a clear provenance home** — the
   canonical/source vs generated vs evidence split already holds; this census
   found no violations, only the archival candidate above.
