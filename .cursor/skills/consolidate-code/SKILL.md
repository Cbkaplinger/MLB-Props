---
name: consolidate-code
description: Plan duplicate-behavior consolidation with characterization tests first. Use when two modules do the same thing, wrappers overlap, or a seam needs one owner; trigger phrases include "dedupe this", "merge these modules", "who owns this logic". Plans first; broad writes only with explicit user approval.
disable-model-invocation: true
---

# Consolidate Code

## Purpose

Merge duplicate behavior (not merely similar names) under one canonical owner with callers migrated, compatibility preserved, and rollback possible.

## Preconditions

- Read `AGENTS.md`, `CONTEXT.md`, and the candidate modules plus all their callers.
- Duplication is behavioral (same inputs, same outputs), not cosmetic.
- Characterization tests exist or are written first to pin current behavior.

## Allowed

- Read code, tests, callers, schedules, and notebooks that reference the candidates.
- With explicit user approval only: make the scoped consolidation edits + caller updates + tests.

## Prohibited

- No broad writes without explicit user approval; default is plan-only.
- No merging research and production paths blindly (research stays shadow until gated promotion).
- No touching protected production paths (`market.py`, `count_layer.py`, `live_assembly.py`, `odds_ledger.py`, board/poll, policy JSONs) without an explicit owner order naming the file and value.
- No behavior change disguised as cleanup; pin first, then move.

## Required inputs

- Candidate modules (paths) and the behavior they share.
- Caller list (who imports or invokes each).
- Compatibility constraint (exact-match vs documented difference).

## Workflow

1. Prove duplication: same behavior on shared inputs (tests or traced calls), not just similar names.
2. Map all callers, schedules, and notebook references for each candidate.
3. Choose the canonical owner (prefer the tested, documented, production-pinned home); name what gets deprecated.
4. Write characterization tests first that pin current outputs on real-shaped inputs.
5. Plan the move: new home, caller migration order, compatibility shim or flag, rollback (prior files restorable via git, no history rewrite).
6. Only with user approval: execute the plan in small steps with tests green between steps.

## Validation gates

- Characterization tests green before and after.
- Full suite (`python -m pytest -q`) green after; pre-commit fast tests green for ledger/registry touchers.
- No caller left on the deprecated path; no silent behavior delta.

## Required outputs

- Plan: owner, deprecations, caller migration list, shim/rollback, test list.
- If executed: files changed, test results, residual risks.

## Stop conditions

- Stop if duplication is unproven (similar names only) -- report, do not merge.
- Stop if a caller or schedule cannot be mapped (ask).
- Stop before broad edits without explicit approval; plan and wait.
