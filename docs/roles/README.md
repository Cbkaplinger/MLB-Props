# Roles (ROLES_REV 2026-10-28-r1)

Owner: architect. Read this file, your role card, then docs/NEXT.md.

## Authority and ownership

Safety, protected-data restrictions and the contract of an executing experiment remain binding. These role cards govern responsibilities; NEXT governs current assignments; EXECUTION_BACKLOG is the only work queue (Chat 1 writes it; others propose corrections). Older AGENTS_ROLES, agent/tool instructions and PR discussions must point here rather than maintain competing policy. Proposed ADRs are not adopted decisions.

Frozen means reproducible historical state, not permanent architecture. Do not change an approved run under its existing identity. New data windows, methods and artifacts may be introduced through an explicitly versioned contract before scoring. Artifact coverage is not a scientific reason to reject earlier available history. Changes to frozen contracts still require the applicable explicit authorization.

## Delivery cycle

Experiment gate chain: Question and acceptance evidence -> reuse existing code -> implement and synthetic-test -> publish immutable checkpoint -> consolidated independent review -> applicable execution authorization -> run -> reproduce -> accept or reject -> integrate -> update current action. Implementation and maintenance tasks follow their own shorter chains (`docs/reference/pr_workflow.md`, "Gates by task type"). Code may merge before a run when appropriate; merge never authorizes execution.

One scientific implementation milestone plus an independent cleanup lane. One writer per claimed path. A review names a SHA; each new checkpoint explicitly supersedes the previous target. Review the delta and affected behavior, not the whole history. New blockers require a violated requirement and reproducer. No polling or repetitive unchanged-status reports. Gates scale with task type (implementation / experiment / maintenance; the three operational chains live in `docs/reference/pr_workflow.md`, "Gates by task type").

Routine scoped coding, synthetic tests and documentation checks do not need repeated permission. Real-data reads, derivations, scoring, protected partitions, production, spending and deletions retain their applicable authorization boundaries. An authorization packet must state exactly what is allowed. A test token is not owner authorization.

## Approval requests

Ask one explicit question naming exactly one action with its full SHA, packet, data scope and destination. Record the approval where the work state lives. Do not ask again while the approved scope is unchanged; a scope change needs a new request.

## Integration

All changes use owned branch -> PR -> current-head review and required checks -> merge. No direct or force push to main. Chat 2 merges only when the architect delegates on the PR. Target at most three open PRs; existing excess is closed through integration, not by deleting evidence. Dependent PRs name their base and dependency. Coordinate before remote edits to another agent's branch.

## PR communication

The PR description is the current dashboard: keep it current and concise; link the card, test evidence and checkpoint instead of pasting their tables. Evidence lives in committed files, CI and artifact receipts. No status-only comments or unchanged-status reports; batch minor corrections into the next coherent checkpoint. One consolidated review response per gate; a merge gets one integration summary, not one message per merge or check. Explicit owner decisions: one concise question with exact scope and packet link. Routine handoffs target 150 words or fewer; longer write-ups are justified only by defects needing explanation. Never delete historical evidence to tidy a thread. A checkpoint is READY FOR REVIEW only after verified publication: local HEAD == freshly fetched remote branch SHA == PR head SHA (operational steps in `docs/reference/pr_workflow.md` section 2). A failed push is a blocker, not a delivered checkpoint; unpushed work is labeled LOCAL ONLY.

## Correcting and reducing documentation

Correct wrong numbers and references in current summaries; state the source and scope of the correction. Preserve underlying historical artifacts and original result receipts. Never silently replace a failed run or relabel inspected data as untouched. Git history preserves document revisions; active instructions do not need endless append-only corrections. Consolidate duplicates, use short pointers, and remove obsolete authority from startup paths. Moves/deletions require exact scope, consumer/reference checks and applicable approval.

NEXT <=4 KB; required startup documents <=12 KB; other living docs <=40 KB. Reduce or archive before creating more files. Reports are evidence, not queues.

Report only a changed state, completed checkpoint or actionable blocker, with the identity fields the work state needs: role revision | task | PR link | published SHA | tested SHA | reviewed SHA/status | next owner/action. Classify findings BLOCKER / NONBLOCKING / RESOLVED. One consolidated response per checkpoint/gate, not one per lifetime PR.

[Architect](architect.md) | [Builder](chat1-builder.md) | [Reviewer](chat2-reviewer.md) | [Documentation maintainer](chat3-cleaner.md)
