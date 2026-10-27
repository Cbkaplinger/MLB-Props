# ROLES — read this first, then your own card (ROLES_REV 2026-10-27-r1)

**Precedence:** `docs/roles/*` + `docs/NEXT.md` override `docs/AGENTS_ROLES.md`, `AGENTS.md`, and `.cursor/rules` wherever they conflict, until Chat 3's reconciliation PR merges. Frozen registrations, pins, hashes and protocols outrank everything.

**Changing roles:** only the architect edits `docs/roles/*`, bumps ROLES_REV, and says so in NEXT.md. Agents propose role changes to the architect in one line; they never self-edit roles. Every report starts with `ROLES_REV=<value you read>`.

## Git rule (all chats)

No chat pushes to `main`. Every change goes branch -> PR -> reviewed -> merged by the architect (or by Chat 2 only when the architect says so on the PR). Max 3 open PRs. Only the architect may push to `main`.

## Connector confirmation and delegation (2026-10-27)

- Repository delegation and tool permission are separate. Standing authorization does not bypass a connector's mandatory confirmation or approval gate. This section does not add per-action approval to local OpenCode/Cursor work already permitted by repository rules.
- Before a side-effecting GitHub connector action, the orchestrator must request confirmation showing the resolved repository, branch/PR/file target, and complete exact tool arguments, including content. Approval is bound to one matching write; changed targets or content require fresh confirmation. Separate workspace approval prompts must also be satisfied when required.
- Read-only inspection does not require this write confirmation. When a write is needed, ask the owner directly through the confirmation prompt; do not repeatedly relay the same task between agents.
- Approval to create a branch is not approval to edit files, open or merge a PR, or execute an experiment. Tool confirmation is not scientific acceptance or experiment authorization. Real-outcome execution still requires the registered gate and explicit owner authorization; protected-data and production restrictions remain unchanged.
- Every handoff states what was actually read or changed, its branch and SHA, and any pending approval. Proposed, committed, pushed, reviewed, merged, executed, and promoted are distinct states. Do not claim a rule is adopted on main before its documentation PR merges.
- Keep one writer per branch/path. The orchestrator must not modify a frozen reviewed scientific branch merely to add governance text. These rules do not grant new direct-to-main permissions or change the canonical work queue.

## Report format (all chats, every turn)

`ROLES_REV | task | HEAD sha | command + result | next step | blocker (or none)`. No project history, no option lists to the owner, no restating this file. Scientific decisions follow repository delegation; owner escalation and connector writes follow the confirmation and authorization boundaries above.

## Document budget (anti-bloat)

- NEXT.md <= 4 KB. Any file an agent must read to start work <= 12 KB. Any other living doc <= 40 KB.
- Past a limit, the owning role splits it (index + parts) or archives the finished part with a pointer. Chat 3 enforces this by PR until its lane ends; afterwards Chat 2 flags breaches in review.
- New docs need a named consumer. Reports are append-only evidence, not queues. One work queue only: `docs/EXECUTION_BACKLOG.md` (to be split by Chat 3).

## Cards

[architect](architect.md) · [chat1-builder](chat1-builder.md) · [chat2-reviewer](chat2-reviewer.md) · [chat3-cleaner](chat3-cleaner.md)
