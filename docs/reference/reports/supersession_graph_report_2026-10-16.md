# Reference-integrity and supersession graph — 2026-10-16 (Chat 3, report-first)

Directed reference map over all 203 tracked Markdown files at `origin/main` @
`1927c8c…`. Machine-readable edge list:
`supersession_graph_2026-10-16.csv` (source, source class, target, target class,
flag). Method: relative-link extraction → register classification → flag rules
(living→draft, frozen→outside-tree). Confidence: HIGH.

## Graph summary

| Measure | Value |
|---|---|
| Markdown files (nodes) | 203 |
| Relative-link edges | 50 |
| Broken edges | **0** (consistent with both prior scans) |
| Flagged: living-doc → draft | **0** — no living documentation points at any `*-draft.md` |
| Flagged: frozen-packet → outside research/ | **0** — frozen packets are internally self-contained |
| Isolated canonical-living docs (no in/out edges) | 48 |

## Interpretation

1. **The living doc layer is clean**: no canonical document routes readers to a
   draft. Draft references come exclusively from two other layers — the
   **work-state backlog** (all 6 drafts) and **frozen research code/packets**
   (`pa_k_baseline.py`, `lineup_opportunity.py`, `kcount_combiner.py`,
   `tests/test_pa_k_baseline.py`, checkpoint-staging doc). See
   [`t6_prereg_disposition_plan_2026-10-16.md`](t6_prereg_disposition_plan_2026-10-16.md).
2. **Frozen packets never reach outside `research/`** — the lake/Git and
   lane-boundary discipline holds in the reference graph, not just in prose.
3. **48 isolated canonical-living docs**: ~40 are entry points by design
   (skill definitions loaded by tooling; root README/CONTEXT/AGENTS). The
   genuine find: the **reference standards with zero in/out links** (the ~14
   consolidation candidates already queued from the register) — confirmed by a
   second, graph-based method. Their canonicalization must come to them (a
   link FROM the source-of-truth index), not the reverse.

## Recommended actions (pointer-level only; no edits made)

| Finding | Action | Owner |
|---|---|---|
| 0 living→draft edges | none needed — the living layer already routes correctly | — |
| Draft refs from frozen code (3 files) + test | repoint to finals in the T6 slice (research-lane sign-off) | Chat 1/owner |
| Backlog draft references (6) | owner decides: point at finals vs keep as historical markers | owner/coordination |
| 14 isolated reference standards | canonicalization candidates S2 (superseded-pointer pass) + source-of-truth index inbound links | Chat 3 (approved slice) |
| 0 broken links | none — the link layer needs no repair pass | — |
