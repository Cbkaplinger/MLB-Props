# Python / notebook / dependency census — 2026-10-16 (Chat 3, read-only)

Census at `origin/main` @ `1927c8c…`. Method: static import scan of all tracked
`.py` files (internal-prefix imports: `src`, `Python`, `production`, `research`,
`models`, `scripts`), `__main__` detection, notebook cross-reference scan, and
`pyproject.toml` dependency reading. Full data: census.json in the Chat 3 session
records. **Unreachable/unstructured findings are candidates for validation, never
for deletion on this evidence.**

## Python entry points and module reachability

- **406 tracked `.py` files**; **294 contain `if __name__ == "__main__"`** — the
  repo is runner-heavy by design (one canonical runner per experiment/ops task).
- **7 `src/Python/` modules show no static importer** anywhere in the tracked
  tree: `ballpark.py`, `batter_features.py`, `batter_rolling.py`, `bullpen.py`,
  `identity.py`, `reliability.py`, `skill_stats.py`.

  **Caveat before anyone acts:** `batter_features` / `batter_rolling` / `ballpark`
  / `bullpen` are listed as canonical pipeline modules in `CONTEXT.md`, so
  zero static imports most likely means **dynamic loading** (importlib/string
  assembly) or invocation paths outside the static scan (notebooks, schedulers,
  subprocess). The only module with independent evidence of staleness is
  `reliability.py` (dead notebook pointer, Issue #9). Proposed next step, if
  approved: a runtime-reachability validation slice (grep scheduling configs,
  notebook kernels, dynamic import sites) before any of the seven is classified.

## Notebooks (22 tracked)

| Group | Count | Callers | Production relevance |
|---|---|---|---|
| `production/notebooks/results_*` + `daily_projections` | 10 | operator flow `.ps1`, runbooks, docs | core ops surfaces (one dead ref: Issue #5) |
| `src/Notebooks/*` | 8 | historical docs only (CLEANUP_LOG-era) | lineage; archival candidates pending caller validation |
| `models/**` (train/stabilization/EDA) | 4 | sparse doc refs | research lineage |

Notebook health checks exist (`scripts/check_notebook_artifacts.py`); executed
output freshness is tracked in `docs/research/notebook_change_log.md`.
Archival/deletion proposals: deferred to backlog ticket T11 with per-file caller
evidence.

## Dependencies (pyproject-driven; no lockfile)

- Runtime extras: `research` (joblib, jupyterlab, lightgbm, matplotlib,
  nbconvert, playwright, pybaseball, plotly, scikit-learn, scipy, seaborn, …)
  and `dev` (pytest, pre-commit, hypothesis per history).
- CI installs `.[dev]` + 5 explicit extras; **no lockfile** — resolution floats.
  Consequences already recorded: CI cache key can't see the extras (backlog T4);
  nondeterministic fresh installs possible. Proposed remedy stays a separate
  approved slice (uv-lock/pip-tools recommendation was already scanned in the
  2026-10-15 backlog restructure; decision is owner's).
- Import/dependency mismatches: none detected — every third-party import seen in
  tracked code maps to a declared dependency or stdlib (spot-check level, not an
  exhaustive audit).
- Deprecated-risk notes (report-only): `playwright` + `pybaseball` are
  research-only extras with network behavior; fine as extras, should never leak
  into production runtime imports (none observed).

## Duplication candidates (code, not docs)

| Pair | Similarity | Verdict needed |
|---|---|---|
| `production/ops/prune_artifacts.py` vs `scripts/prune_artifacts.py` | same purpose, 220 vs 122 lines, different protections | owner canonicality ruling (backlog T7) |
| `production/odds/odds_board.py` vs `src/Python/odds_board.py` | distinct tools, shared name | none (documented naming collision) |
| harness test files named `test_results_index.py` on PR #7 vs #8 | competing implementations | resolved (#7 closed; #8 canonical) |

## Census disposition

Read-only slice per assignment. Actionable outputs feed backlog tickets T4
(lockfile), T7 (prune canonicality), T9 (reliability), T11 (notebook archival).
The 7-module reachability question is the one genuinely new lead; its validation
slice should be approved before anyone treats those modules as dead.
