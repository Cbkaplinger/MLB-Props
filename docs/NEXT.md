# NEXT — single source of the current action

**Owner of this file:** architect. Every agent reads it first and updates only its own line.
Max 15 lines of status. Link SHAs; do not retype history. Updated 2026-10-22.

## Critical path (one item at a time)

1. **M0 real-data development run** (multiclass PA model vs frozen binary L3).
   - Owner directive 2026-10-22: run M0 now, once, under the registered card.
   - Chat 1: confirm the remote tip contains Chat 2's repairs (ancestry check), confirm the
     non-author acceptance covers that exact SHA, then execute the registered command once.
   - Chat 2: review the receipt and results at the executed SHA. No new scope.
   - Output: effect sizes, intervals, per-class diagnostics, limitations. One verdict: pass, fail, stop.
2. Then M1 (K head through the count layer) per ROADMAP. Not before M0 reports.

## M0 framing (not "multiclass instead of binary")

The binary L3 stays the frozen production model until M0 passes its registered gate.
M0 is a test of whether a softmax version is non-inferior on K-vs-not-K and better on the
five-class loss. A fail freezes binary and ends the multiclass line.

## Parked (no work until promoted; each has a promote-or-kill date)

| Item | Decision date |
| --- | --- |
| Decision-flip rerun with repaired bootstrap | 2026-11-07 (run after M0 verdict) |
| Coverage policy for 59 cold-start starts | 2026-11-07 (default: league-rate prior, flagged) |
| History extension toward 2015 (M4) | Kill unless M0 passes; revisit 2027-01 |
| Question B | Kill unless M1 passes |

## Chat 3 cleanup list (finite; finishing it ends the lane)

1. Execute the EXECUTION_BACKLOG split: evergreen core under 40 KB plus a byte-preserving archive file; update inbound links; link check green.
2. Archive the four superseded reports marked in the reports index and re-point every tracked citation in the same PR.
3. Move `report/` into `docs/reference/reports/`; ask the owner nothing further.
4. Consolidate the diagram set: retire 09 into 13 after re-pointing consumers; keep the rest.
5. Reduce root entry points: README, CONTEXT, AGENTS each get a one-line pointer to NEXT.md and PROJECT_STATE.md.
6. Line-by-line review applies only to files touched by items 1-5, not all 692.
7. Never touch research/, models/, frozen registrations, or production/.

One PR per item, docs-only, merged after Chat 2's bounded review. Report with PR links only.

## Rules that prevent drift

- One critical-path item at a time; nothing starts while it is open.
- A report states: SHA, command, result, next step. No restated project history.
- Unverified numbers carry the label UNVERIFIED until a receipt exists.
