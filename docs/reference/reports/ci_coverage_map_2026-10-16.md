# Default-CI test-collection coverage map — 2026-10-16 (Chat 3, report-first)

Exact enumeration replacing the T14 hypothesis. Base `origin/main` @ `1927c8c…`;
collection rule = `testpaths = ["tests"]` in `pyproject.toml` + pytest default
discovery. Confidence: HIGH (file-list facts).

## Collected by default CI (83 test files under `tests/`)

All `tests/test_*.py` — including the pre-commit fast trio
(`test_odds_ledger`, `test_real_bets`, `test_registries`), the live-stack pin,
pipeline/research-utility tests, and (once PR #8 lands)
`tests/test_results_index.py`. Full list = `tests/` tree; no exclusions inside it.

## NOT collected (5 files on main)

| Excluded test file | Suite it guards |
|---|---|
| `research/offseason_2026/p1_harness/test_feature_contract.py` | v2 production-schema feature contract (21-column mirror, source semantics) |
| `research/offseason_2026/p1_harness/test_harness_guards.py` | artifact-root declaration, sha256 manifest, import-resolution guards |
| `research/offseason_2026/p1_harness/test_log5_identities.py` | log5 identity proofs |
| `research/offseason_2026/bf_workload_v1/tests/test_milestone_correction.py` | milestone-correction regression |
| `research/offseason_2026/prospective_logging/test_logger.py` | prospective logging |

## Consequence and minimal remedy

CI's green badge does not exercise these 5 files; they run only when their lane
owner invokes pytest manually (as recorded in past checkpoint evidence, e.g. the
p1-harness "72 passed" runs). After PR #3 merges, its suites
(`market_eval/tests/`, `count-eval-v2` harness tests) will join the excluded set
unless collection changes — that is the moment this becomes high-impact.

**Minimal separate check (proposal, no files edited):** a second CI step —
`python -m pytest research/offseason_2026 -q -rs -p no:cacheprovider --continue-on-collection-errors`
— or cleaner: move the 5 (soon ~15) harness test files under `tests/` (or
declare them via `python_files`/`addopts` in pyproject). The research-suite
runner must stay non-blocking for docs-only PRs **without** path-filtering the
main suite: a status-weakening tolerance (`--continue-on-collection-errors`)
plus a required step keeps main-suite coverage intact while adding the lane.
Owner picks the mechanism; T14 stays sequenced after T3.
