# NEXT — single source of the current action

**Owner of this file:** architect. Agents read it first and update only their own line.
Link SHAs; do not retype history. Updated 2026-10-22 (afternoon).

## Critical path (one item)

**M0 v1 STOPPED at `71b236f`:** registered stop fired (class 4 caught_stealing_or_pickoff has 0 training
PAs in block_2024H2). No outcome metric was produced. Recorded as STOPPED, not a negative result.
Ruling and branching: PR #34 comment (architect, 2026-10-22).

1. Chat 1: per-class, per-block TRAINING label counts + raw class-4 event counts (descriptive only).
2. Chat 2: independent reproduction; classify as (A) structurally absent or (B) label-join defect.
3. (B) -> repair, rerun once under the same card. (A) -> v1 closed; draft card v2 with the taxonomy
   restricted to classes that exist (Chat 1 drafts by 2026-10-27, Chat 2 reviews, architect approves).
4. If no reviewed v2 by 2026-11-07: freeze binary, close M0 (ROADMAP pivot rule 3).

## Authority

The architect decides scientific sequencing and branching. The owner is asked only for restricted
actions (spending, deleting, production changes). Agents do not list "owner must decide" options.

## Parked (promote-or-kill dates)

| Item | Decision date |
| --- | --- |
| Decision-flip rerun with repaired bootstrap | 2026-11-07 |
| Coverage policy for 59 cold-start starts | 2026-11-07 (default: league-rate prior, flagged) |
| History extension toward 2015 (M4) | Kill unless M0 passes |
| Question B | Kill unless M1 passes |

## Chat 3 (finite list; ends the lane)

Waiting on merges (#37 and #33 are merged). Then: rebase #36 (drop ROADMAP edit, keep both sides of
00-index, fix duplicate header, backlog-split owner = Chat 3), then the backlog split as its own PR,
then archive four superseded reports, move report/, retire diagram 09, add entry-point pointers.
Max three open PRs. Docs only. Never touch research/, models/, production/, frozen paths.

## Anti-drift rules

- One critical-path item at a time. Reports: SHA, command, result, next step.
- Unverified numbers carry UNVERIFIED until a receipt exists.
- No new ideas enter via chat; ideas go to the architect and get a promote-or-kill date.
