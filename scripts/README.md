# Scripts Inventory and Safety Status

This folder contains utility scripts spanning production checks and historical
research helpers. Do not delete scripts solely because they are not called by
`production/` directly.

## Production-adjacent (keep)

- `check_notebook_artifacts.py` — required by notebook refresh flow.
- `export_notebook.py` and `export-notebook.ps1` — notebook export utility.

## Research-maintenance (keep; low-frequency)

- `feature_diagnostics.py`
- `vif_cluster_reduction.py`
- `expanded_feature_registry.py`
- `feature_coverage_matrix.py`
- `finalize_step1_registries.py`
- `window_stabilization_gap.py`
- `window_change_proposals.py`
- `batter_pitch_type_rv_research.py`

These are retained as reproducible scaffolding for feature/reliability work and
future model-family expansion (hits, walks, outs, pitches).

## Current audit result (2026-08-11)

- No script in this folder is a verified safe delete target yet.
- Some scripts have zero in-repo references, but still produce documented
  research artifacts and should be treated as retained until superseded.

## Deletion rule

A script may be deleted only if all are true:

1. No references in `docs/`, `production/`, `src/`, `tests/`, or notebooks.
2. Its outputs are not cited by current research/reference docs.
3. A replacement script/path is documented in this file and in
   `docs/reference/repo_canonical_map.md`.
