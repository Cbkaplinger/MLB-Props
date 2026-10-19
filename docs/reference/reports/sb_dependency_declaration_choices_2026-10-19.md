# S-B dependency declaration choices — 2026-10-19 (Chat 3, patch presented for owner approval)

The exact seven declarations in this branch's `pyproject.toml`, with the
import-to-package mapping and validation. **Patch is unmerged; merge requires
the owner's tier approval.** `sage` is deliberately NOT declared (see bottom).

## The seven choices

| # | Package (PyPI) | Tier | Import sites (tracked consumers) | Why this tier |
|---|---|---|---|---|
| 1 | `requests` | `research` | `production/ops/market_research/probe_2023_2024.py`, `pull_featured_totals.py`, `pull_kalshi_k_history.py`, `pull_oddsapi_historical.py` | all four consumers are research-lake pullers; the daily chain does not import it |
| 2 | `xgboost` | `research` | `models/Strikeout-Model/research/ablate_sparse72_model_families.py`, `final_feature_set_ablation.py`; `production/ops/compare_model_family_governance.py` | model-family ablation/governance comparisons |
| 3 | `optuna` | `research` | `models/Strikeout-Model/research/tune_lightgbm_feature_set_optuna.py`, `tune_lightgbm_final58_optuna.py` | frozen-era tuning runners |
| 4 | `catboost` | `research` | `models/Strikeout-Model/research/final_feature_set_ablation.py` | same ablation family |
| 5 | `pymupdf` | new `paper` | `docs/paper/validate_pdf.py` | paper artifact validation |
| 6 | `markdown` | new `paper` | `docs/paper/render_pdf.py` | paper rendering |
| 7 | `modal` | new `deploy` | `production/cloud/modal_app.py` | cloud deployment; must never land in base/runtime installs |

## Validation (included in the patch)

- `tests/test_sb_dependency_declarations.py`:
  - asserts all seven names are present in `pyproject.toml`, with the exact
    `paper`/`deploy` extra lines;
  - asserts `"sage"` is absent (deliberate exclusion);
  - asserts the mapping doc names every package and the `sage` consumer;
  - runs the merged hygiene checker (`scripts/repo_hygiene_check.py --json`) on
    the patched tree and asserts **none of the seven packages is still flagged
    as undeclared**.
- No package was installed; no environment changed; `sage` untouched.

## The deliberately excluded eighth import

`models/Strikeout-Model/research/full_feature_importance_screen.py` imports
`sage` (1 consumer, legacy-era research surface). Recommendation: **do not
declare it** — either the owner confirms the screen is still live (then declare
in `research`) or the file is retired like the other legacy-era research
surfaces. The hygiene checker will keep flagging it until resolved — that is
the intended signal.

## Non-actions

No version pins, no lockfile (T4 remains separate), no CI change, no
installation, no `sage` decision.
