# NEXT — single source of the current action

Owner: architect. Updated 2026-10-22 (evening). ROLES_REV 2026-10-22-r2. Read `docs/roles/README.md` first.

## Critical path (one item)

M0 v1 STOPPED at `71b236f` (class 4 caught_stealing_or_pickoff: 0 training PAs in block_2024H2; no outcome metric produced). Ruling: PR #34 architect comment.

1. Chat 1: per-class, per-block TRAINING label counts + raw class-4 event counts (descriptive only).
2. Chat 2: independently reproduce; classify (A) structurally absent from PA-completing rows or (B) label-join defect.
3. (B): repair under the same card, rerun once. (A): v1 closed; draft card v2 with 4 classes: strikeout, walk (incl. HBP, catcher interference), hit, in-play out (incl. errors, sacrifices, DP outs). Same features, folds, margin, endpoints, Holm m=2, same 82,817 key set; declare per-class minimum count from label counts only. Chat 1 drafts by 2026-10-27; Chat 2 reviews; architect approves.
4. No reviewed v2 by 2026-11-07: freeze binary, close M0.

## Chat 3 (finite)

1. Rebase #36 (drop ROADMAP edit; keep both sides of 00-index; fix duplicate header; backlog-split owner = Chat 3).
2. Contradiction sweep PR: point AGENTS_ROLES/AGENTS/.cursor rules/pr_workflow at docs/roles/; remove conflicting text (reviewer read-only; owner-gate options; stale M0 status).
3. Backlog split PR (index + parts; each part <= 12 KB; closed items archived with pointer).
4. Archive four superseded reports; report/ move; retire diagram 09. Then the lane ends.

## Parked (promote-or-kill)

Decision-flip rerun 2026-11-07 · coverage policy for 59 cold-start starts 2026-11-07 (default league-rate prior, flagged) · history extension: kill unless M0 passes · Question B: kill unless M1 passes · finer taxonomy (HBP/HR split, double-play state): after v2 result.
