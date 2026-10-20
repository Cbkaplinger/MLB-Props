# Dependency closure proposal — 2026-10-16 (Chat 3, PROPOSED taxonomy)

Completes the dependency audit ([`dependency_reproducibility_audit_2026-10-16.md`](dependency_reproducibility_audit_2026-10-16.md))
with the full taxonomy. Base `origin/main` @ `1927c8c…`. **No package/CI files
edited.** Confidence: HIGH (pyproject read + import scan).

## Proposed dependency taxonomy (target state)

| Tier | Contents | Declaration home | Rationale |
|---|---|---|---|
| T0 base runtime | polars, numpy, pandas, scikit-learn, joblib, scipy, lightgbm, statsmodels, requests | `[project].dependencies` | imported by production/`src/Python` daily-chain code |
| T1 research extras | matplotlib, seaborn, plotly, pybaseball, playwright, jupyterlab, nbconvert, hypothesis + **xgboost, optuna, catboost, sage** (currently undeclared) | `[project.optional-dependencies].research` | research runners/notebooks only |
| T2 paper extras | **pymupdf, markdown** (currently undeclared) | new `.paper` extra (or research) | `docs/paper/render_pdf.py`, `validate_pdf.py` |
| T3 deploy extras | **modal** (currently undeclared) | new `.deploy` extra | `production/cloud/modal_app.py` — must NOT land in base |
| T4 dev/test | pytest, pre-commit, (+ existing dev set) | `[project.optional-dependencies].dev` | CI + local dev |
| T5 streamlit | declared today; imported only by `production/app/dashboard_streamlit.py` | keep, or move to a `.dashboard` extra if the dashboard is optional | one importer |

## The 8 undeclared imports → homes

| Import | Files | Proposed tier | Why it works today |
|---|---|---|---|
| `requests` | 4 (odds/lake pullers, Kalshi probe) | T0 (or research if pullers are research-only — owner call) | present in local env |
| `xgboost` | 3 (model-family ablations) | T1 | research env has it |
| `optuna` | 2 (LightGBM tuners) | T1 | same |
| `catboost` | 1 (ablation) | T1 | same |
| `sage` | 1 (importance screen) | T1 | same |
| `modal` | 1 (cloud deploy) | T3 | deploy env |
| `pymupdf` | 1 (PDF validation) | T2 | paper env |
| `markdown` | 1 (PDF render) | T2 | paper env |

## Python version / OS constraints

- Python `>=3.11` pinned in pyproject; CI runs 3.11; local 3.11.9 — no matrix
  needed (single-runtime policy is deliberate).
- OS: Windows for the `.ps1` automation lane; ubuntu for CI; Polars/pandas/
  LightGBM are cross-platform. No platform-conditional dependencies observed.
- `PYTHONIOENCODING` set in 10 `.ps1` files = the cp1252-console mitigation —
  an OS constraint expressed in config, not packages.

## Lockfile options (owner decision)

| Option | Pros | Cons |
|---|---|---|
| `uv lock` + `uv export` for CI | fast, modern, single source | new tool adoption |
| `pip-tools` (`requirements.lock` from pyproject) | minimal change, CI-friendly | extra step to maintain |
| Hand-pinned pyproject | zero new tooling | drift risk returns |
Recommendation: `pip-tools`-style lock as the smallest honest fix; cache key
then hashes the lockfile (replaces CI T4). Whichever is chosen, the 8
declarations (slice D1) come first — they are correct under every option.
