---
name: archive-research-memory
description: Index research history without rewriting it. Use when consolidating reports, onboarding to a research thread, or finding contradictions; trigger phrases include "index the research", "what did we learn", "research summary". May write an index file only; never edits or deletes original evidence.
disable-model-invocation: true
---

# Archive Research Memory

## Purpose

Extract hypotheses, methods, populations, results, decisions, and open questions from dated reports and cards into a navigable index -- while leaving every original file untouched.

## Preconditions

- Read `AGENTS.md` and `CONTEXT.md`.
- Know the thread (e.g. PA overhaul, TBF spine, calibration) and the report/card set to index.
- Index output path agreed (dated file under `docs/reference/reports/` or a thread note that links to the backlog).

## Allowed

- Read reports, cards, manifests, deviations, choice logs, and ADRs.
- Write exactly one new index file (or update a prior index from the same thread with dated append-only entries).
- Link experiments to decisions; mark superseded claims with pointers.

## Prohibited

- Never edit, rewrite, or delete original reports, cards, or manifests. Index, do not rewrite history.
- Never auto-delete evidence, even when superseded.
- No production writes; no 2026 retuning; no new scientific claims beyond what the sources state.

## Required inputs

- Thread name and the source file list (or directory + date range).
- Index destination path.
- Supersede policy: mark, link, keep (default; no deletions).

## Workflow

1. Extract per source: hypothesis, method, population (n, dates, grain), results with metrics, decision taken, open questions.
2. Build the index: chronological entries with file links, metric lanes labeled (fair vs juiced, next-book vs DK+FD, selection vs confirmatory).
3. Detect contradictions: same question, different answers -- record both with dates and populations, do not resolve by fiat.
4. Link experiments to decisions (choice log, ADRs, backlog entries).
5. Mark superseded claims as SUPERSEDED with a pointer to the replacing source; keep the original listed.

## Validation gates

- Every indexed claim links to its source file; no orphan conclusions.
- Metric lanes labeled on every number; golden metrics cited, not recomputed.
- Contradictions listed explicitly, not smoothed over.

## Required outputs

- Index file: thread summary, per-source extracts, contradiction register, decision links, superseded map, open questions.
- List of sources indexed vs skipped (with why).

## Stop conditions

- Stop if the thread scope or destination is unclear (ask).
- Stop if indexing would require altering a source file (report, do not edit).
- Stop before deleting anything; deletions need a separate explicit owner order.

## Repository evidence

Read when relevant:

1. `docs/reference/reports/README.md` -- dated-report index and SUPERSEDED convention.
2. `docs/reference/repo_canonical_map.md` -- canonical vs archive classification for supersede decisions.

If canonical sources disagree, stop and report the conflict. Do not silently choose the newest file.
