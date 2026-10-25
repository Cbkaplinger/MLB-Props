> **Canonical role map:** `docs/roles/`. This file is the historical detail layer; where it conflicts with `docs/roles/` or `docs/NEXT.md`, those win (see docs/roles/README.md for precedence).

# AGENTS_ROLES — who does what (chat agents + owner)

**Date:** 2026-10-14. Updated 2026-10-19: Chat 3 role, ownership/handoff rules,
and evidence-preservation rule consolidated from the AGENTS.md role map.
Updated 2026-10-21 (owner directive via architect): standing push/merge
authorization within stated limits, long-lived PR rules, three review gates,
statistics rules, folder-by-folder cleanup. The 2026-10-21 section supersedes
any earlier line it contradicts.
Authoritative role map for the market-eval v2 review workflow and general repo
work. When a chat agent is unsure whether it may do something, it may NOT —
ask the owner.

## Roles

**Canonical role map:** `docs/roles/` (README + per-chat cards). The table
below is the historical detail layer; `docs/roles/` overrides where they
conflict.

| Role | Who | Scope |
| --- | --- | --- |
| Architect / orchestrator | Master orchestrator chat | Sequencing, direction, ADR/PRD, statistical rules, assignments |
| Builder | Chat 1 | Scientific implementation, project-state page |
| Trailing reviewer / fixer | Chat 2 | Independent review, bounded repairs, GitHub-side actions |
| Cleanup (temporary) | Chat 3 | Documentation contradictions, indexes, archiving, doc budget |
| Coordinator | Owner | Real-outcome execution, deletions, protected paths, promotion, the private research lake. Sole holder of the blinding question (INCIDENT.md). |

## Worktree ownership

- `MLB-Props-worktrees\main-active` — builder worktree (Chat 1). Chat 2
  works from remote branches / fresh checkouts, never in the builder's
  working tree.
- One active owner per file/path/decision; separate worktree/branch per chat.
- Private research lake (`<private research lake>\...`, e.g.
  `market-eval-v1\`, `bf-workload-v1\`, `pregame-pa-ext-v1\`) — owner's
  local data store, NOT in this repo, never pushed, referenced only
  generically in committed docs.

## Handoff contents

- Handoffs include: repo URL + branch + base SHA + current full SHA + dirty
  state + PR + CI + tests + artifacts.
- Builder self-check is not independent READY; execution is gated on review
  of the exact published SHA.

## Prohibited actions (all chat roles)

- No `git push` except to the chat's own named branch as allowed by the
  2026-10-21 standing authorization. Never push to `main`, never force-push.
- Never merge PRs outside the 2026-10-21 standing merge authorization; never
  enable auto-merge or close/reopen PRs without owner authorization.
- Never run the gated scoring command against real frozen prep + real
  outcomes without owner authorization on the record. Synthetic test fixtures
  only otherwise (see PROJECT_STATE.md for the gated command and its gate).
- Never modify bytes pinned at `02ce162f119208b762edf1fd690edd5e7ee9b8ea`
  (`research/offseason_2026/market_eval/` implementation files). Docs-only
  follow-ups on top of the pin are allowed.
- Never edit live scorers, policy JSONs, schedules, ledgers, or model
  artifacts from research context (research != production rule, AGENTS.md).
- Never commit generated/ignored paths (`data/`, `artifacts/`, `.venv/`,
  caches) and never commit absolute local paths into published docs.
- No execute/merge/delete/reset/rebase/force-push outside the standing
  authorization without explicit owner authorization.

## Authorization boundaries

- Synthetic tests (`python -m pytest research/offseason_2026/market_eval/tests -q`):
  any agent may run, anytime.
- Canonical scoring run against real outcomes: owner-gated, authorized by the
  owner on the record, after the Chat 2 pre-execution review.
- Disputes about scope: stop and ask the owner; `docs/EXECUTION_BACKLOG.md`
  wins over any agent's reading of a subordinate doc. Frozen registrations,
  pins, hashes, and pre-registered protocols outrank this file, ADRs, PRDs,
  and any role rule.

## Evidence preservation

- Historical evidence is preserved: corrections append or supersede, never
  delete.

## Historical operating rules (2026-10-19; superseded by docs/roles/)

Superseded by `docs/roles/README.md` and `docs/NEXT.md`. Preserved for
lineage.

## Operating rules (owner directive, 2026-10-19)

1. **One active worktree per chat**, plus an integration checkout if needed.
   Preserved WIP is an explicit temporary exception with an owner and a
   closure condition - not an active workspace.
2. **One writer per branch and checkout.** No parallel windows commit to the
   same branch; parallel-window output is handed off, not re-committed.
3. **One designated backlog writer** (Chat 1 for PROJECT_STATE.md and the
   backlog fold-in). Other agents provide updates; they do not independently
   edit shared state.
4. **Published means remotely reachable.** Committed, pushed, reviewed, and
   merged are four different states - report the exact state, never "done"
   for committed-only work.
5. **Reviews name exact heads.** Later commits receive only the necessary
   delta review; earlier verdicts are not silently reused for new heads.
6. **No new worktree without an owner, a task, and a closure condition.**
   Worktree-creation freeze remains in effect until the count reaches the
   steady state (three active + one integration checkout).
7. **Post, retrieve, then report.** (Narrowed 2026-10-21: applies to review
   verdicts. A merge receipt is its own proof and needs no retrieve step.) No
   new blocker without evidence naming the exact requirement and artifact.

Violations of rules 1-4 observed 2026-10-19 (dual-window commits to one
branch; verdicts reported but unposted; "merged/open" contradictions) are
recorded in docs/reference/reports/chat3_final_handoff_2026-10-19.md and
the PR #18 reconciliation thread.

> **Preserved 2026-10-23:** these rules are the historical operating context. `docs/roles/` and `docs/NEXT.md` override where they conflict.

## Operating rules (owner directive, 2026-10-21)

### Standing authorization (replaces per-action owner orders)

- **Push:** every chat may push to its own named branch without asking.
  Pushing to `main` and force-pushing stay prohibited.
- **Merge:** Chat 2 may merge a PR when (a) it holds a PASS verdict at the
  current head, (b) CI is green at that head, and (c) the PR touches only
  docs, tests, or research code. The merge receipt (SHA) is posted on the PR.
- **Still owner-only:** real-outcome execution, production paths, deletions,
  promotion, frozen-contract changes, spending the confirmation block.

### Long-lived PR rule

- **One PR per lane** (research, cleanup, governance). At most **three** open
  PRs repo-wide. No cap on commits per PR.
- Fixes, corrections, and follow-up cards go on the open PR for that lane.
- A new PR requires a new milestone, not a new correction or a new folder.
- Do not merge a PR early just to unblock a review; a PR merges at a milestone
  or when its lane has nothing further to add.

### Review gates

Chat 2 reviews at three gates only: (1) before any real-outcome run,
(2) when a result is accepted, (3) before merge. Docs-only deltas are
"checked" and merged. Chat 1 and Chat 2 communicate on the PR, once per
gate; no relay messages, no re-verification of cleared items. The standing
pre-execution check: the entry point produces a complete receipt on synthetic
input (consumed-input identities populated, no placeholders).

### Statistics rules (apply to every pre-registration card)

1. One primary metric, one contrast, sign convention stated before the run.
2. A practical-significance threshold is declared before the run, in addition
   to any significance test.
3. Report effect size with its interval; never a p-value alone. Report a
   resolution-floor p as "p <= 1/(B+1)".
4. Multiplicity counts across experiments that reuse the same development
   set. The confirmation block is not spent on marginal effects.
5. Resample by slate date (clustered), never by start or PA.
6. Fix the population before looking; state selection and abstention rules.
7. Secondary metrics and subgroups are descriptive. Never quote them as
   improvements.
8. Non-significance supports a stop decision; it is never evidence of
   equivalence. For "no worse than" claims, pre-declare a non-inferiority
   margin.
9. Proper scoring rules only (log loss, Brier, RPS). No accuracy.

### Cleanup, folder by folder

Chat 3 works one folder at a time and delivers four lines per folder: folder,
files read, fixes, proposals. No coverage restatement outside the registry.
Deletions and frozen or active-research paths are proposals to the owner,
never executed.

### Reporting format (all chats)

SHA, what changed, tests (passed/total), what is next. Commit messages: 10
lines at most; detail belongs in the result record.
