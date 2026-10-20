---
name: repo-garbage-collector
description: Evidence-driven cleanup umbrella for MLB-Props. Routes cleanup tasks to the five specialist skills, owns the global prohibitions, protected classes, deletion standards, rollback rules, and PR sequencing. Use when consolidating docs, removing dead code, reconciling metric populations, auditing entry points or dependencies, or starting any repository cleanup task.
---

# Repo Garbage Collector (umbrella)

Evidence first, deletion second. Every classification needs a trace: references,
execution path, or test. **This skill routes; specialists execute.** The full
11-phase methodology (baseline → evidence graph → docs GC → backlog contract →
Python GC → notebooks → static+deps → artifacts → metrics/populations → batches
→ verify) remains authoritative at
[`.agents/skills/repo-garbage-collector/SKILL.md`](../../../.agents/skills/repo-garbage-collector/SKILL.md)
with its references (`cleanup-policy.md`, `metric-invariants.md`,
`verification-checklist.md`) — point, then read. Glossary: [LANGUAGE.md](LANGUAGE.md).

## Routing table

| Task | Route to |
|---|---|
| Doc sprawl, stale refs, draft/final pairs, supersession, archive routing | `repo-docs-canonicalizer` |
| Dead-module claims, reachability, orphan `.py`, import/caller questions | `repo-dead-code-auditor` |
| Notebooks, generated artifacts, lake/Git boundary, manifests, fixture families | `repo-artifact-lifecycle-auditor` |
| Test-collection gaps, CI coverage doubts, suite inventories | `repo-ci-coverage-auditor` |
| Import/declaration mismatches, extras taxonomy, env/config provenance | `repo-dependency-hygiene` |
| First cleanup run in a fresh clone; missing repo-path context | `repo-setup-onboarding` |
| Cross-cutting batches, population reconciliation, final verification | umbrella retains (phases 7–9) |

## Global prohibitions (override any specialist)

1. Frozen experiment packets: annotate/banners only — never retrospective edits,
   never relabeling failure evidence.
2. `docs/EXECUTION_BACKLOG.md` is other lanes' work-state — read, never rewrite.
3. No deletion without: evidence artifact citation + owner gate + validation
   command + rollback.
4. No direct pushes to main, no force-push, no history rewrites, no edits in
   another chat's worktree.
5. Metric definitions and golden-metric numbers are cited, never recomputed or
   "cleaned".
6. Evidence of failed runs is preserved and clearly labeled.

## Phase → specialist status (migration in progress)

Phases 0 (baseline), 1 (evidence graph), 7 (metrics/populations), 8 (batches),
9 (verify) remain umbrella-owned. Phases 2/3/4/5/6 are now ALSO available as
specialist skills (see routing table); the umbrella body remains authoritative
until each specialist passes review. No phase text is deleted during migration.

## Stop condition

Every finding is routed or dispositioned (merged / superseded / deferred /
rejected / converted-to-issue). An audit that ends in "in progress" has not
ended.
