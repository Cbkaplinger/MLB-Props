# Python architecture and dead-code audit — 2026-10-16 (Chat 3, report-first)

Scope/method: static import/caller map over all **406 tracked `.py` files**
(294 with `__main__`) at `origin/main` @ `1927c8c…`. Resolution covers bare-stem
imports, repo-dotted paths, AND the `Python.*` internal convention (sys.path=src;
125 such imports resolved — this **corrects my 2026-10-15 census**, which missed
bare/dotted forms and wrongly flagged `bullpen.py`). Reachability = import graph
from all 294 entry points. Evidence: reverse-import lists, `git grep` CLI/doc
references, dynamic-import site scan (58 files use `importlib`/`__import__`).
Confidence: HIGH for import facts; MEDIUM for "dead" conclusions (dynamic
loading invisible to static analysis). Data: `deep_audit_final.json` in session
records. Nothing deleted; report-only.

## Corrected headline finding — five documented-canonical modules are statically dead

| Module | Importers | Test refs | Doc refs | Static-reachable | Classification | Risk tier |
|---|---|---|---|---|---|---|
| `src/Python/bullpen.py` | 4 (`live_assembly`, `tbf`, 2 tests) | 2 | 33 | YES | **proven active** | — (prior census corrected) |
| `src/Python/skill_stats.py` | 1 (test only) | 1 | 7 | no | **test-only** | Low |
| `src/Python/ballpark.py` | 0 | 0 | 10 | no | uncertain-dead | **High (doc-canonical)** |
| `src/Python/batter_features.py` | 0 | 0 | 8 | no | uncertain-dead | **High** |
| `src/Python/batter_rolling.py` | 0 | 0 | 22 | no | uncertain-dead | **High** |
| `src/Python/identity.py` | 0 | 0 | 64 | no | uncertain-dead | **High** |
| `src/Python/reliability.py` | 0 | 0 | 52 | no | uncertain-dead + independent staleness evidence (Issue #9) | High |

`CONTEXT.md` lists `ballpark`, `batter_features`, `batter_rolling`, `bullpen`,
`pitcher_features`, `pitcher_rolling` as canonical pipeline modules — but four of
them plus `identity`/`reliability` have **zero importers, zero test references,
and zero CLI/script callers in the tracked tree**. Either the docs are stale, or
invocation is invisible to static analysis (58 dynamic-import sites exist; lake
runners may vendor their own copies). **Disposition: owner-decision (runtime
trace / deployment-reference check) before ANY is touched.** This is the
audit's most consequential hidden-bug lead: canonical documentation describes a
call structure the code no longer has.

## Static orphan census (36 -> 23 after corrected resolution)

23 non-test, non-entry-point, never-imported files. 22 have at least one repo
reference (subprocess/doc/manifest) — typical patterns: research runners called
via `subprocess`/`runpy` (e.g. experiment `run_*.py` helpers), build scripts,
`production/app/dashboard_streamlit.py` (launched by `streamlit run`),
`production/cloud/modal_app.py` (deployed, not imported). **1 file has zero
references of any kind** — the single true delete-candidate; identity recorded in
`deep_audit_final.json` (`orphans` + `orphan_cli`), gated behind owner approval
per the standing rules.

## Research lane reachability

Research runners on main (43 entry points) are import-islands by design:
executed once, then preserved as frozen evidence (lake is authoritative). Their
"unreachability" is expected and NOT a cleanup target. PR #3's harness/test
files follow the same pattern.

## Classification summary (all 406 files)

| Class | Count (approx) | Rule |
|---|---|---|
| production active (reachable from entry points) | ~180 | in `reach` set |
| entry points (CLI/manual/scientific) | 294 (overlapping) | `__main__` |
| tests | 84 | `tests/` + harness test dirs |
| research frozen runners/helpers | ~90 | `research/**` |
| static orphans with references | 22 | subprocess/doc-called |
| true zero-reference orphans | 1 | delete-candidate (owner) |
| uncertain-dead documented modules | 5 (+1 test-only) | table above |

## Smallest safe follow-up

One owner question — "are ballpark/batter_features/batter_rolling/identity /
reliability invoked outside the tracked tree?" — then either (a) a
dead-code quarantine slice (move to `docs/archive/`-style retention or delete
with full reference list), or (b) a docs-truth slice updating `CONTEXT.md` if
the modules are genuinely retired. No PR until answered.
