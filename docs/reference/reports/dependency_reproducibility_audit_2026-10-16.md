# Dependency and reproducibility audit — 2026-10-16 (Chat 3, report-first)

Scope/method: declared dependencies (`pyproject.toml`: base + `research` + `dev`
extras) vs the actual third-party import surface (static scan of all 406 tracked
`.py` files, stdlib-filtered). Base `origin/main` @ `1927c8c…`. Confidence: HIGH
on import facts; declared-set read directly from `pyproject.toml`. No package or
CI files edited.

## Declared vs imported

| Status | Packages (import name: files importing) | Assessment |
|---|---|---|
| Declared & heavily used | `polars` 333, `numpy` 190, `pandas` 126, `sklearn` 102, `lightgbm` 20, `joblib` 18, `scipy` 12, `matplotlib`, `pybaseball`, `playwright`, `seaborn`, `plotly` | healthy core |
| Test-only declared | `pytest`, `hypothesis` | correct placement |
| **Imported but NOT declared (8)** | `requests` 4 (market_research pullers/probes), `xgboost` 3 (model-family ablations), `optuna` 2 (tuning research), `catboost` 1, `modal` 1 (cloud deploy), `pymupdf` 1 + `markdown` 1 (paper render), `sage` 1 (importance screen) | **undeclared-import defect** |
| Declared but import-unseen | `jupyterlab`/`nbconvert` (tooling, not imported — fine) | n/a |

The undeclared eight work today only because the local environment happens to
contain them. Any fresh `pip install ".[research,dev]"` (i.e. CI or a new
machine) **cannot import** `modal`, `pymupdf`, `markdown`, `requests`,
`xgboost`, `optuna`, `catboost`, or `sage` from tracked code. Most sit in
research/one-off lanes; `modal` guards the cloud deploy path;
`requests` sits in the historical-odds pullers. Risk: Medium (reproducibility
and CI-completeness), not security.

## Missing lockfile — implications (verified)

- No lockfile exists; resolution floats per install.
- CI cache key hashes only `pyproject.toml` (`cache-dependency-path`), so the
  five CI-installed extras (`scipy joblib scikit-learn lightgbm statsmodels`)
  are invisible to cache invalidation — recorded as CI backlog T4.
- Two fixes exist and are mutually exclusive: (a) add a lockfile
  (`uv lock` / `pip-tools`), or (b) pin versions in pyproject. The 2026-10-15
  backlog restructure already shortlisted `uv-lock`; the decision is owner's.

## Minimal reproducibility remedy (proposal; no files edited)

1. **Declare the 8 imports** in the correct extras (research: xgboost, optuna,
   catboost, sage; deploy: modal; paper: pymupdf, markdown; base/research:
   requests) — smallest possible change, immediately makes fresh installs
   complete. One-line-per-package PR.
2. **Then** (owner decision) adopt a lockfile so CI installs become
   bit-reproducible; regenerate CI cache key from the lockfile (replaces T4).
3. Keep extras split as-is (research-only heavyweights must not become base deps).

## Platform-specific notes

- Windows cp1252 consoles: ASCII-only research code convention already in
  `AGENTS.md`; no unix-only shebangs observed in production scripts.
- `.ps1` automation is Windows-only by design; CI (ubuntu) does not exercise it —
  acceptable, documented here so nobody mistakes CI green for PowerShell-lane
  validation.

## Smallest safe follow-up

Slice D1: declare the 8 missing packages (owner approval; one commit + fresh-env
smoke install test). Slice D2 (optional, owner): lockfile adoption.
