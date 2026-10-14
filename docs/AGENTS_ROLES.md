# AGENTS_ROLES — who does what (chat agents + owner)

**Date:** 2026-10-14. Authoritative role map for the market-eval v2 review
workflow and general repo work. When a chat agent is unsure whether it may
do something, it may NOT — ask the owner.

## Roles

| Role | Who | Scope |
| --- | --- | --- |
| Builder | Chat 1 (opencode agent) | Implements in the local worktree. Writes code/docs/tests, runs synthetic tests, prepares commits. No pushes, no PRs, no merges unless the owner explicitly orders it for a named branch. |
| Reviewer + GitHub steward | Chat 2 | Independent review of pinned commits/PRs; owns GitHub-side actions (PR checks, comments, merges) when the owner authorizes. Does not modify pinned implementation bytes. |
| Coordinator | Owner (human) | Authorizes scoring runs, pushes, merges, and any change to protected production paths. Sole holder of the blinding question (INCIDENT.md) and of the private research lake. |

## Worktree ownership

- `MLB-Props-worktrees\main-active` — builder worktree (Chat 1). Chat 2
  works from remote branches / fresh checkouts, never in the builder's
  working tree.
- Private research lake (`<private research lake>\...`, e.g.
  `market-eval-v1\`, `bf-workload-v1\`, `pregame-pa-ext-v1\`) — owner's
  local data store, NOT in this repo, never pushed, referenced only
  generically in committed docs.

## Prohibited actions (all chat roles)

- Never `git push` without an explicit, named-branch owner order in the
  live conversation (repo rule; the 2026-10-14 push to
  `research/market-eval-v2` was one such explicit order).
- Never merge PRs, enable auto-merge, or close/reopen PRs without owner
  authorization.
- Never run the gated scoring command against real frozen prep + real
  outcomes. Synthetic test fixtures only (see PROJECT_STATE.md for the
  gated command and its gate).
- Never modify bytes pinned at `02ce162f119208b762edf1fd690edd5e7ee9b8ea`
  (`research/offseason_2026/market_eval/` implementation files). Docs-only
  follow-ups on top of the pin are allowed.
- Never edit live scorers, policy JSONs, schedules, ledgers, or model
  artifacts from research context (research != production rule, AGENTS.md).
- Never commit generated/ignored paths (`data/`, `artifacts/`, `.venv/`,
  caches) and never commit absolute local paths into published docs.

## Authorization boundaries

- Synthetic tests (`python -m pytest research/offseason_2026/market_eval/tests -q`):
  any agent may run, anytime.
- Canonical scoring run: owner-gated, authorized by the owner on the
  record, after the Chat 2 review and the blinding question (INCIDENT.md)
  are resolved.
- Push/PR/merge: only on an explicit owner order naming the branch.
- Disputes about scope: stop and ask the owner; `docs/EXECUTION_BACKLOG.md`
  wins over any agent's reading of a subordinate doc.
