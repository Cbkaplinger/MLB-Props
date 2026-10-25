# Bloat-removal proposal — 2026-10-21 (Chat 3, one page, for owner approval)

> Scope: the three owner-named items. **No deletions or moves without owner
> approval.** Executor notes included per item. Evidence: the sweep registry
> (982 files classified; 239 fully read), the gc skill tool outputs, and the
> preservation ledger section 17.

## 1. Split the 512 KB `docs/EXECUTION_BACKLOG.md` (Chat 1 sole-writer)

The bulk is dated PRESENT bullets (2026-08 through 2026-10 completed work)
plus three older sections (Strategy Plan 2026-09-01, SSAC27 track, Parking
Lot). Proposal:

| Piece | Action | Destination |
|---|---|---|
| Directive, Standing Rules, Waiting-on-user | **KEEP** (evergreen core) | `EXECUTION_BACKLOG.md` |
| PRESENT bullets older than the current session | **MOVE verbatim** (byte-preserving, no summarizing) | `docs/reference/reports/backlog_archive_2026-10-21.md` |
| Strategy Plan — 2026-09-01 + SSAC27 track sections | **MOVE verbatim** | `docs/reference/reports/backlog_archive_2026-10-21.md` (same file, headed sections) |
| FORWARD / DEFERRED / Parking Lot active items | **KEEP** (still live) | `EXECUTION_BACKLOG.md` |

Every moved section leaves a one-line pointer in place (the established
supersession convention). Executor: **Chat 1** (sole-writer) as a single PR,
Chat 2 exact-head review; Chat 3 verifies byte-preservation of moved text.
Target: backlog ≤ ~60 KB, archive holds the evidence unaltered. The
Session Snapshot gains one PRESENT line recording the split.

## 2. Archive candidates from tooling output

Honest result: the gc tool runs found **0 exact duplicate files** and every
diagram/doc reference resolves (96 links checked, 2 repaired in #26). The
evidence-backed list is therefore short — bloat here is concentration, not
junk:

| Candidate | Evidence | Proposed action |
|---|---|---|
| `report/` top-level dir (1 file) | sole file; referenced by backlog + recency card | **MOVE** to `docs/reference/reports/` + 2 pointer updates (needs Chat 1's backlog line) |
| `analysis/model_results/` (2 files: 1 notebook + README) | zero operational callers found; cited nowhere in production docs | owner picks: archive to `docs/archive/` or KEEP as analysis provenance |
| `docs/research/step7/10/11_*_registry_freeze.md` | superseded by `pipeline_registry.json` (registry is design-canonical) | **LABEL** superseded-for-registry in-file (keep as evidence) |
| 2026-10-16 census/sweep cluster (~20 files) | point-in-time; already labeled by the navigation rule | **KEEP** (no action — the navigation rule covers them) |
| `mlruns/`-class local stores in worktrees | ignored content, removed with worktrees | none (already handled) |

Not proposed for deletion: dated reports (evidence), frozen experiment
packets (registrations), notebooks with operator rulings, all production code.

## 3. Worktree disposition (current; ledger section 17 is the record)

6 worktrees including the primary checkout. **KEEP:** primary (intentional
legacy preservation), `maintenance-dep-declarations` (this lane's active
checkout), `paext-v2` + `repo-review-paext-registration` (Chats 1/2 active).
**Pending, not mine to act on:** `distribution-spec` (owner disposition, 18
dirty/untracked WIP), `main-active` (Chat 1 PUBLISH: 2 local commits + 6
files incl. `run_bf_ab_score.py` v1 — verified archival before any removal).
**0 removals this pass; creation frozen.**

## Execution order if approved

1. Chat 1: backlog split (single PR, byte-preserving moves + pointers).
2. Chat 3: `report/` move + pointer repairs + the two supersession labels
   (one PR; the backlog pointer line lands via Chat 1's split PR).
3. Lane closes: no further read-lane batches; registry handoff recorded.
