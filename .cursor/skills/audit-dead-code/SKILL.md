---
name: audit-dead-code
description: Classify dead or orphaned code by confidence without deleting it. Use when pruning scripts, notebooks, or modules; trigger phrases include "dead code", "unused module", "can we delete this". Read-only classification; never auto-deletes.
disable-model-invocation: true
---

# Audit Dead Code

## Purpose

Find code that looks dead and classify it by confidence -- so the owner can delete with evidence instead of guessing.

## Preconditions

- Read `AGENTS.md`, `CONTEXT.md`, and `docs/reference/repo_canonical_map.md`.
- Scope is set (directory, family, or named module). Generated paths (`data/`, `artifacts/`, `.venv/`) are out of scope.

## Allowed

- Read code and search static imports, dynamic imports, CLI entry points, schedulers, notebook references, and config-selected modules.
- Check git history for recent use.

## Prohibited

- Never delete, move, or edit code from this skill. Classification only.
- No touching production paths, notebooks on the daily path, or policy configs.
- No case-only rename suggestions on Windows (git/cross-platform risk).

## Required inputs

- Audit scope (paths or family).
- Liveness definition: what counts as "used" (imported, scheduled, referenced by docs/INDEX/RUNBOOK).

## Workflow

1. Static pass: imports, qualified names, string references, `__main__` guards, CLI wiring.
2. Dynamic pass: config-selected modules, plugin/entry-point loading, notebook `import` cells, scheduler wrappers (Modal, ps1, tasks).
3. History pass: last commit touching the file, linked backlog or report rationale.
4. Classify each candidate: dead-high (no references anywhere), dead-medium (only stale/historical references), hold (unclear, config-gated, or provenance value), alive (referenced by live path, tests, INDEX/RUNBOOK, or canonical docs).
5. Note the deletion evidence each high-confidence item still needs (smoke command that would prove safety).

## Validation gates

- Every dead-high claim lists the searches run (import grep, scheduler grep, notebook grep, history).
- Protected families (`src/Python/` core, `production/odds/`, `production/projections/`, current `production/notebooks/`, `production/ops/` configs) default to hold, never dead-high, without an owner order.
- Provenance value (paper citations, freeze lineage) forces hold, not delete.

## Required outputs

- Classification table: path | verdict | confidence | evidence | owner action.
- Deletion candidates grouped by confidence with the smoke check for each.
- Explicit non-targets encountered and left alone.

## Stop conditions

- Stop if scope is the whole repo with no family (ask for a bounded scope).
- Stop before any deletion or edit; hand the table to the owner.
