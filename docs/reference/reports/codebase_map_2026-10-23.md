# Codebase map — entry points, module calls, unscoped areas

> Read from code at `origin/main` (`bfd7dba`). 397 non-test .py files scanned.
> 315 entry points (have `if __name__ == '__main__'`). 82 non-entry-point
> modules. 55 potentially unscoped modules (no inbound imports, not entry
> points — see §3).

## 1. Entry points by directory

| Directory | Count | What they are |
|---|---|---|
| `production/ops/` | 57 | Operational scripts (refresh, score, grade, report) |
| `production/ops/market_research/` | 82 | Dated market-research runners (one report each) |
| `production/odds/` | 6 | Odds polling, board, grading |
| `production/projections/` | 3 | Projection logging |
| `src/Python/pipeline/` | 3 | L1-L3 pipeline stages |
| `src/Python/` | 1 | `daily_lineups.py` |
| `models/Strikeout-Model/` | 3 | Trainers + predict |
| `models/Strikeout-Model/research/` | 64 | Dated ablation/feature-screen scripts |
| `models/TBF-Model/` | 1 | TBF trainer |
| `scripts/` | 21 | Utility + maintenance scripts |
| `scripts/agent/` | 3 | Skill validation scripts |
| `research/offseason_2026/` | 33+ | Dated research runners (frozen) |
| `docs/paper/` | 4 | Paper figure/render scripts |
| `playground/` | 2 | Demo scripts |
| `.agents/skills/` | 4 | Cleanup skill scripts |

## 2. Shared infrastructure modules (imported by 3+ files)

| Module | Files importing | Role |
|---|---|---|
| `polars` | 284 | Primary dataframe library |
| `numpy` | 181 | Numerical computation |
| `pandas` | 106 | Legacy dataframe compatibility |
| `nested_cv` | 31 | Chronological CV module |
| `join_keys` | 29 | Join-key helper |
| `kcount_combiner` | 26 | Count PMF combiner |
| `run_corrected_history_2023` | 20 | Corrected-history runner |
| `bf_distribution` | 10 | BF distribution module |
| `comparison` | 9 | Harness comparison interface |
| `track_and_verify` | 7 | D-1 tracking wrapper |

## 3. Potentially unscoped modules (55)

These have no inbound imports and no `__main__` entry point. They may be
test helpers, conftest fixtures, or genuinely dead code. Each needs a
consumer-evidence check before any deletion proposal.

| Directory | Count | Notes |
|---|---|---|
| `research/offseason_2026/` | 30 | Dated experiment scripts, frozen |
| `models/Strikeout-Model/research/` | 8 | Dated research scripts |
| `production/` | 4 | `modal_app.py`, `dashboard_streamlit.py`, market_research helpers |
| `src/Python/` | 5 | Includes `whatif.py`, `tbf.py`, `bullpen.py` |
| `research/` other | 8 | Including conftest fixtures |

## 4. What is NOT unscoped

- `src/Python/market.py`, `count_layer.py`, `live_assembly.py`, `odds_ledger.py` — protected production paths
- `production/odds/` board/poll/grading — live operational entry points
- `tests/` — CI-discovered, not classified here (101 files)
- All files under open review (PR #34) — deferred


## 5. Module disposition reconciliation

The 55 potentially unscoped modules were checked for tracked inbound references
(docs, configs, code imports). Results:

| Disposition | Count | Detail |
|---|---|---|
| KEEP — frozen/dated research evidence | ~30 | `research/offseason_2026/` experiment scripts and conftest fixtures; preserved frozen evidence |
| KEEP — production/operational | 4 | `modal_app.py` (live cloud), `dashboard_streamlit.py` (parked but referenced), 2 market_research helpers |
| KEEP — utility | 5 | `src/Python/whatif.py`, `tbf.py`, `bullpen.py`, `eval_package.py`, `pa_contracts.py` — documented tools with README/model-card references |
| KEEP — test helpers | ~8 | `conftest.py`, `test_feature_contract.py`, etc. — CI-discovered |
| Unresolved | ~8 | Require per-file consumer-evidence review before classification |

**No deletion proposals from static import absence alone.** Per-file
consumer-evidence review is required before any deletion proposal.

## 6. Diagram 18 status

Diagram 18 is labeled **UNDER AUDIT** at the source SHA. It shows both:
- The **historical broken flow** at `6bee3f7` (identity lost at dedup/consensus/join)
- The **repaired required flow** (identity carried through every transformation)

Independent verification of the repaired implementation: **NOT YET VERIFIED**.
