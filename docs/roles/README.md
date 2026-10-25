# ROLES — read this first, then your own card (ROLES_REV 2026-10-22-r2)

**Precedence:** `docs/roles/*` + `docs/NEXT.md` override `docs/AGENTS_ROLES.md`, `AGENTS.md`, and `.cursor/rules` wherever they conflict, until Chat 3's reconciliation PR merges. Frozen registrations, pins, hashes and protocols outrank everything.

**Changing roles:** only the architect edits `docs/roles/*`, bumps ROLES_REV, and says so in NEXT.md. Agents propose role changes to the architect in one line; they never self-edit roles. Every report starts with `ROLES_REV=<value you read>`.

## Git rule (all chats)

No chat pushes to `main`. Every change goes branch -> PR -> reviewed -> merged by the architect (or by Chat 2 only when the architect says so on the PR). Max 3 open PRs. Only the architect may push to `main`.

## Report format (all chats, every turn)

`ROLES_REV | task | HEAD sha | command + result | next step | blocker (or none)`. No project history, no option lists to the owner, no restating this file. Scientific decisions belong to the architect; the owner is asked only about spending, deletions and production changes.

## Document budget (anti-bloat)

- NEXT.md <= 4 KB. Any file an agent must read to start work <= 12 KB. Any other living doc <= 40 KB.
- Past a limit, the owning role splits it (index + parts) or archives the finished part with a pointer. Chat 3 enforces this by PR until its lane ends; afterwards Chat 2 flags breaches in review.
- New docs need a named consumer. Reports are append-only evidence, not queues. One work queue only: `docs/EXECUTION_BACKLOG.md` (to be split by Chat 3).

## Cards

[architect](architect.md) · [chat1-builder](chat1-builder.md) · [chat2-reviewer](chat2-reviewer.md) · [chat3-cleaner](chat3-cleaner.md)
