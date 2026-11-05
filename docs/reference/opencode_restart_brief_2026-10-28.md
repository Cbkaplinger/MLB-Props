# OpenCode restart brief — 2026-10-28 (multi-window closeout)

> **Paste this file into the next builder OpenCode session.** Saved at the
> owner's closeout order 2026-10-28. Approvals and next actions live only in
> [`docs/EXECUTION_BACKLOG.md`](../EXECUTION_BACKLOG.md). If this file and the
> Snapshot disagree, the **Snapshot wins** — then fix this file.
>
> Supersedes the 2026-09-11 paste brief
> ([`opencode_handoff.md`](opencode_handoff.md)) for session-start orientation
> only; the replay-era material there remains historically true. Nothing here
> merges a PR or authorizes an execution.

---

## The brief (verbatim, 2026-10-28)

```text
MLB-PROPS RESTART — 2026-10-28

OPERATING MODEL
One active OpenCode builder + architect.
Independent reviewer invoked at milestones.
Chat 3 dormant; test-cleanup assignment cancelled.

GOVERNANCE
ROLES_REV 2026-10-28-r1.
Updated governance is on PR #46's branch, not yet assumed merged into main.
Read:
  docs/roles/README.md
  docs/roles/chat1-builder.md
  docs/NEXT.md
from the updated documentation revision.
Then read only the relevant task/backlog section.

PUBLISHED CHECKPOINTS
PR #46 — documentation:
  branch chat3/doc-simplify-20261023
  head 587fa4f8fbf5f97526767266b23b9f0e9cf143cf
  reviewer PASS; both CI jobs passed; unmerged.

PR #49 — Stage A prediction-path diagnostic:
  branch docs/lineup-path-reconciliation-spec
  head ca00e4df5a426acf37ef9d3f43f8e25aa95dc8e1
  reviewed READY; CI passed; unmerged; not executed.

PR #50 — historical starter outcomes + baseline helpers:
  branch research/baseline-benchmark-v1
  head 69aa861e398a730b020887eed8a90b6c6cbab688
  reviewer PASS; both CI jobs passed; unmerged.
  Stacked on PR #49.
  Targeted synthetic suite: 36 passed, per published evidence.

PR #48 — calibration execution gate:
  branch research/calibration-exec-gate-v1
  head 1321e4bf45ca1673985612b2994cbda4eca23f9f
  Separate pending integration decision; calibration not executed.

NEXT WORK
1. Verify actual remote heads and local worktree state.
2. Complete authorized integration decisions:
   #46 is independent; #49 precedes #50.
   Handle #48 separately.
3. Finalize the exact historical derivation/overlap execution packet.
4. Obtain the applicable explicit authorization before running it.
5. Preserve output/failure evidence and independently verify results.
6. Then proceed to baseline predictive scoring under its own contract.

DO NOT RESTART
No new architecture exercise, harness, distribution-family search,
repository-wide test cleanup, or fresh investigation of cleared findings.

PRESERVE
Unknown files in the primary checkout.
Three untracked legacy helpers in the review checkout.
Existing branches, worktrees, receipts, and historical evidence.
No reset, clean, stash, deletion, force-push, or automatic branch switching.
```

## What closing the windows did not mean (owner closeout, 2026-10-28)

- It does not merge the open PRs.
- It does not authorize Requests A/B, Stage A, calibration, or scoring.
- It does not require deleting worktrees, branches, local helpers, or unknown files.
- It does not invalidate the existing reviews and test evidence.

The published branches and PR discussions are the durable handoff. Current
successful CI runs are recorded for the documentation and baseline
checkpoints. [PR #46 CI](https://github.com/Cbkaplinger/MLB-Props/actions/runs/40764380198) ·
[PR #50 CI](https://github.com/Cbkaplinger/MLB-Props/actions/runs/40764709996)

## One clarification for the next execution packet (owner, 2026-10-28)

Request B compares realized K/BF outcome values. It is **outcome-artifact
validation** — not merely metadata inspection — although it is not
forecast-performance scoring. Label it accordingly.

The packet also must identify the exact executable wrapper and output-writing
behavior. The derivation function and a prose description of intended files
are not automatically a complete write-once execution procedure. That is a
bounded completion task, not a reason to reopen the model design.

## Who to reopen (owner, 2026-10-28)

Reopen one builder window when ready to work, with this brief. Bring Chat 2
back for the next explicit review or integration gate. Leave Chat 3 closed
until there is a named, compatible cleanup task.

No merges or execution authorizations were issued by the 2026-10-28 closeout.
