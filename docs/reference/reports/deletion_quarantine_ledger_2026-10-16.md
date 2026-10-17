# Deletion / quarantine ledger — 2026-10-16 (Chat 3, report-first)

Complete ledger of every deletion/archive/quarantine candidate, consolidating
the dead-code audit, dynamic-import resolution, notebook review, register, and
staleness audit. **No item may be actioned without its owner decision; nothing
has been deleted.** Post-change validation is specified per item.

## A. Proven-dead Python modules (owner ruling outstanding: out-of-tree invocation yes/no)

| Item | Evidence | Last known reference | Proposed action | Reversibility | Post-change validation |
|---|---|---|---|---|---|
| `src/Python/ballpark.py` | 0 imports (all forms), 0 string refs, 0 CLI callers, not reachable | doc mentions only (CONTEXT/README, 10 files) | **delete** (S-C1) + docs-truth fix | `git revert` | full pytest; `git grep ballpark` zero code matches |
| `src/Python/batter_features.py` | same (8 doc files) | CONTEXT/README | delete (S-C1) + docs fix | revert | same pattern |
| `src/Python/batter_rolling.py` | same (22 doc files); only "reference" is a parquet-name docstring in `pipeline/rolling.py` | CONTEXT/README | delete (S-C1) + docs fix | revert | same |
| `src/Python/identity.py` | same (64 doc files) | CONTEXT/README + skills | delete (S-C1) + docs fix | revert | same |
| `src/Python/reliability.py` | same (52 doc files) + Issue #9 stale pointer | README + roadmap | delete (S-C1) + docs fix + close Issue #9 | revert | same |
| `src/Python/skill_stats.py` | test-only (1 importer: its test) | `docs/reference/dev-notes.md` et al. | delete module + its test (S-C1) | revert | pytest (test count drops by design, noted) |
| `tests/test_skill_stats.py` | tests the test-only module | none | delete with module | revert | pytest |

## B. Orphans and duplicates

| Item | Evidence | Last known reference | Proposed action | Reversibility | Post-change validation |
|---|---|---|---|---|---|
| `models/Strikeout-Model/research/print_step9_inventory.py` | **zero references of any kind** (only true orphan in 809 files) | none found | delete (S-C1 scope, owner) | revert | orphan re-scan returns empty |
| `research/offseason_2026/pa-k-baseline-prereg-draft.md` | blob-identical to final prereg | prereg lineage docs | archive-with-pointer (S-D-style) or keep-as-lineage — **owner pick** | revert | link check |
| `research/offseason_2026/expanding-training-prereg-draft.md` | blob-identical to final | same | same | revert | link check |
| `pitcher_prior/calibration.json` == `metrics.json` | identical blobs within one experiment | experiment packet | **owner ruling**: copy-error fix would edit frozen packet → likely keep + annotate | revert | results-index unchanged |
| `.cursorignore` == `.clineignore` | intentional mirror (documented) | AGENTS.md | keep; document convention in canonical map | n/a | none |
| 2 intentional rerun copies (bf demo dirs) | preserved enforcement-rerun evidence | experiment lineage | keep; results index covers | n/a | none |

## C. Archive candidates (move, not delete)

| Item | Evidence | Last known reference | Proposed action | Reversibility | Post-change validation |
|---|---|---|---|---|---|
| `src/Notebooks/*` (10 notebooks, 2026-07/08 vintage, no outputs, no operational callers) | notebook deep review | `dev-notes.md` (training), `CLEANUP_LOG.md` (several) | S-D: `git mv` to `docs/archive/legacy-notebooks/` + manifest + 2 pointer updates | git history; revert | link check; zero `src/Notebooks` refs in production |

## D. Superseded/dead references (pointer fixes, not deletions)

| Item | Evidence | Held by | Proposed action | Reversibility | Post-change validation |
|---|---|---|---|---|---|
| `results_gate_policy.ipynb` (deleted notebook) | basename absent; Issue #5 | `production/RUNBOOK.md`, `docs/diagrams/01+03`, backlog, operator `.ps1` | T5 pointer pass + T8 script fix (separate) | revert | link check; dry chain |
| `Strikeouts.ipynb` (deleted notebook) | Issue #9 | `src/Python/reliability.py` | resolves via S-C (module deleted) or pointer fix | revert | `git grep` zero-match |
| 34 self-marked SUPERSEDED docs | banner convention | themselves | keep as-is (already correct) | n/a | none |
| `feature-understanding.ipynb` (historical) | CLEANUP_LOG historical entry | log only | none (historical record) | n/a | none |

## Ledger rules

- Every action above is **owner-gated**; Chat 3 executes only the approved slice,
  one PR per item, exact-head CI, Chat 2 verdict, merge receipt.
- Deletion items carry their full inbound-reference list in the PR body at
  execution time (re-verified same-day — references may have moved).
- Nothing here overrides the frozen-evidence rule: experiment packets are
  annotated, never rewritten; the two draft==final prereg pairs require the
  owner to choose between archive and retain-as-lineage before anything moves.
