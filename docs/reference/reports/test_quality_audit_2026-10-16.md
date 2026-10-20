# Test-quality audit — 2026-10-16 (Chat 3, report-first)

Scope/method: mapping of the **84 test files** (`tests/` + harness test dirs) to
production/research modules via the static import graph; name-normalized second
pass; suite-configuration review (`pyproject.toml`, pre-commit hook). Base
`origin/main` @ `1927c8c…`. Report-only; data in `deep_audit_final.json`.
Confidence: HIGH on import-based facts, MEDIUM on coverage conclusions
(CLI/subprocess-tested code is invisible to import analysis).

## Coverage shape

- **171 `src/Python/` + `production/` modules have NO direct test import.**
  This is a heuristic upper bound on untested surface — several of these are
  known to be exercised differently (e.g. `production/odds/grade_odds_ledger.py`
  sits atop `src/Python/odds_ledger.py`, which IS directly tested and
  pre-commit-pinned; runners are validated end-to-end by ops runs, not unit
  imports). The number is a *prioritization input*, not an indictment list.
- **Strongly anchored cores** (direct test imports + pre-commit fast trio):
  odds ledger, real bets, registries, live-stack pin, pipeline modules,
  research harnesses (scaffold/combiner/bf_distribution/eval_package),
  market research utilities, count-eval-v2 + market_eval suites (PR #3).

## Findings

| # | Finding | Evidence | Risk | Suggested follow-up |
|---|---|---|---|---|
| 1 | **Production runners with no test anchor**: 149 production entry points, most untested by import (watchers, backfills, builders) | import graph | Medium | Not unit-testable wholesale; add smoke/`--help` exit-0 tests for the daily-chain scripts first (cheap, catches import rot — the Issue #5 class) |
| 2 | **`execution_receipt.json` directory-assumption defect** (independently observed by Chat 2 during B1 reconciliation) | Chat 2 review record, PR #3 lane | Medium | Separately scoped candidate owned by Chat 1; recorded here for the test-gap ledger; NOT edited from this lane |
| 3 | **Fragile path assumptions (historical)**: 61 hardcoded user-path hits, concentrated in notebooks + `models/Strikeout-Model/research/` (portability pass fixed 5 staged files on 2026-10-13; remainder are historical surfaces) | pattern scan | Low-Med | Cover opportunistically; production code shows near-zero hits (good) |
| 4 | **Tests depending on local lake state**: by design, the `integration` marker lane skips with named reasons when artifacts are absent, and fails loudly on hash mismatch — correct pattern, already documented | `pyproject.toml` markers, harness conftest | Low | Keep the pattern; any new artifact-pinned test must copy it |
| 5 | **Ops `.ps1` chains untested** (the operator flow executes notebooks by path) | Issue #5 evidence | Medium | A dry-run/dry-chain test (notebook existence check per step) would have caught Issue #5; propose as small slice |
| 6 | **Research suites not in default CI lane?** CI runs full `pytest -q` from repo root — `research/offseason_2026/**/tests/` are collected only if rootdir config includes them; verified `testpaths = ["tests"]` in pyproject → **research/harness tests under `research/` are NOT in the default run**; CI covers them only when a PR's workflow changes or via manual runs | `pyproject.toml` testpaths | Medium (hidden) | Proposal: either add explicit `--addopts`-free second pytest invocation for research suites in CI (owner-approved), or document the manual-lane expectation. Report-only here |

Finding 6 is the audit's most actionable discovery: the repo's most active test
surface (count-eval-v2/market-eval suites, 50+ tests) lives under
`research/offseason_2026/` while `testpaths` pins default collection to
`tests/` — meaning CI's green badge does not exercise those suites unless their
paths are inside `tests/` (PR #8's test is; PR #3's harness tests are not).

## Smallest safe follow-ups

1. (Owner approval) CI slice: run research-lane suites explicitly (still no path
   filtering of the main suite).
2. (Chat 2/Chat 1) Track finding 2 in the B1 closeout lane as already reported.
3. (Chat 3) Smoke-existence test for the operator notebook chain — pairs with
   Issue #5's fix slice.
