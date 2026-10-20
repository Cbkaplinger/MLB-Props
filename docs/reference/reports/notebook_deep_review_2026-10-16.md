# Notebook deep review — 2026-10-16 (Chat 3, report-first)

Per-notebook classification of all **22 tracked notebooks** at `origin/main` @
`1927c8c…`. Fields: last content touch, size, executed-outputs presence (heuristic:
non-empty `outputs` cells), caller evidence (`git grep` over tracked
md/ps1/py/json), input-data references, and disposition. Confidence: HIGH on
inventory, MEDIUM on "reproducible" (not re-executed). Data mirrors
`deep_audit_v3.json`.

## Production notebooks (10) — operational, keep

| Notebook | Last touch | Outputs | Callers | Inputs referenced | Disposition |
|---|---|---|---|---|---|
| `daily_projections.ipynb` | 2026-08-27 | no | 3 (operator flow, INDEX, README) | projections/ledger paths | keep — operator step [3/7] |
| `results_kpi_monitor.ipynb` | 2026-09-11 | yes | 3 | ledger | keep — step [4/7] |
| `results_pnl_clv.ipynb` | 2026-09-15 | yes | 3 | ledger, CLV sources | keep — step [5/7] |
| `results_bettable_cohort.ipynb` | 2026-09-11 | yes | 3 | cohort/ledger | keep — step [6/7]; hosts retired gate-policy audit |
| `results_recommendation_audit.ipynb` | 2026-08-27 | no | 3 | board/ledger | keep — step [7/7] |
| `results_calibration_lab.ipynb` | 2026-09-11 | yes | 3 | calibration artifacts | keep — optional `-IncludeCalibration` |
| `results_dashboard.ipynb` | 2026-08-20 | yes | 3 | full deep-dive inputs | keep — optional deep dive |
| `model_governance.ipynb` | 2026-09-11 | yes | 1 | governance artifacts | keep — governance surface |
| `results_gate_policy.ipynb` | — | — | — | — | **deleted**; live references tracked as Issue #5 |
| `results_dashboard` deep-dive helpers | — | — | — | — | n/a |

## `src/Notebooks/` (10) — lineage archive candidates (T11)

All last touched **2026-07-23** (except `features.ipynb` 2026-08-27), **none have
executed outputs**, callers are historical docs only. They predate the
`src/Python` pipeline they document and duplicate its narrative. Disposition:
**archive-with-manifest after caller validation** — no deletion, moves preserve
history. One nuance: `pipeline/training.ipynb` (3 doc callers) and
`pipeline/rolling.ipynb` (2) are referenced by living docs
(`dev-notes.md`, `CLEANUP_LOG.md`) — their archival must update those pointers
in the same slice.

## Models research notebooks (4) — provenance, keep

`train.ipynb` (2026-08-27), `stabilization.ipynb` (2026-08-27), 
`strikeout-eda.ipynb` (2026-08-20, outputs present, 61 hardcoded-path hits live
here — clean opportunistically), `analysis/model_results/model_results_story.ipynb`
(2026-08-15). All part of frozen model provenance; keep.

## Cross-cutting observations

1. **Freshness split is clean**: production surfaces touched through
   2026-09-11..15; research/lineage surfaces frozen at 2026-07/08 — matching the
   retrain-closed era. No notebook claims to be current that isn't.
2. **Executed-output hygiene**: production results notebooks carry outputs
   (operator-visible artifacts) — correct for this repo's convention;
   `src/Notebooks` carry none (consistent with lineage status).
3. **Input dependencies** are ledger/artifact paths under `data/`+`artifacts/`
   (ignored dirs) — notebooks therefore depend on local runtime state, which is
   why the `check_notebook_artifacts.py` + operator-flow pattern exists. No
   notebook writes outside its lane was observed in the scan.
