---
name: document-architecture
description: Verify diagrams and architecture docs against code. Use when docs drift from the build, onboarding, or auditing the pipeline map; trigger phrases include "update the diagram", "architecture doc", "is this diagram current". May write docs only; never changes code.
disable-model-invocation: true
---

# Document Architecture

## Purpose

Keep architecture docs truthful: verify every box and arrow against the code, fix the prose or diagram, and stamp what was verified and when.

## Preconditions

- Read `AGENTS.md`, `CONTEXT.md`, and `docs/reference/repo_canonical_map.md`.
- Know which surface is under review (`docs/diagrams/`, `docs/reference/`, or a named doc).

## Allowed

- Read code (`src/Python/`, `production/`), configs, registries, and existing diagrams.
- Write or edit architecture docs and diagrams (C4-style: context, container, component where cheap).
- Add last-verified dates and current-vs-proposed markers.

## Prohibited

- No code, config, policy, schedule, or ledger changes.
- No duplicated config values in prose (link the canonical file instead).
- No inventing planned work as current; proposals are labeled proposed with an owner.
- No new top-level folders or second sources of truth.

## Required inputs

- Doc or diagram scope (file path or subsystem).
- Verification depth: link-check, path-check, or full code walk.

## Workflow

1. Inventory the doc's claims: modules, paths, data flows, schedules, owners.
2. Verify each against the tree: file exists, name current, flow matches call order, schedule matches cron/registry.
3. Classify each claim: current (verified, stamp date), stale (fix with evidence), proposed (label + link to backlog/ADR).
4. Fix stale claims minimally; link canonical paths instead of copying values.
5. Record last-verified date and commit in the doc.

## Validation gates

- Every module path in the doc resolves in the tree.
- No config value quoted in prose that could drift (link the JSON instead).
- Current vs proposed is unambiguous on every diagram.

## Required outputs

- Updated doc/diagram with verification stamps.
- Change table: claim | was | now | evidence (file:line or commit).

## Stop conditions

- Stop if the subsystem boundary is unclear (ask).
- Stop if verification needs running pipelines or reading generated parquet (report unverified).
- Stop before any code change; docs only.

## Repository evidence

Read when relevant:

1. `docs/reference/offseason_architecture_audit_2026-09-28.md` -- census precedent: inventory, docs, arch, and git pass structure.
2. `docs/diagrams/00-index.md` -- diagram index and status snapshot.

If canonical sources disagree, stop and report the conflict. Do not silently choose the newest file.
