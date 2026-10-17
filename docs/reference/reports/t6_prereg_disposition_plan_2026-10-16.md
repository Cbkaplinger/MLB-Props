# T6 prereg-draft disposition plan — 2026-10-16 (Chat 3, PREPARED, not executed)

Per the four-decision table, applied with fresh reference scans (all six drafts
at `origin/main` @ `1927c8c…`). **Material correction to earlier assumptions:
none of the six drafts is unreferenced** — every one is cited by
`docs/EXECUTION_BACKLOG.md`, three are cited by **frozen research code**, one by
a test, three by a checkpoint-staging doc, one by an external-framework review.
"Delete the redundant draft" is therefore unavailable in all six cases; the
outcome is **archive-with-pointer + reference repointing**, and the code-file
repoints need research-lane ownership.

## Per-pair disposition

| Draft (final pair) | Similarity | References found | Decision (table applied) | Actions |
|---|---|---|---|---|
| `pa-k-baseline-prereg-draft.md` (==final, 1.00) | identical | backlog; **`pa_k_baseline.py`**; **`tests/test_pa_k_baseline.py`** | redundant AND referenced → archive with pointer; repoint code+test refs | `git mv` draft → `docs/archive/prereg-drafts/`; pointer banner; update 2 code-file references to the final (research-lane owned) |
| `expanding-training-prereg-draft.md` (==final, 1.00) | identical | backlog; `evaluation-framework-external-2026-10-06.md` | archive with pointer; repoint 2 doc refs | same pattern (docs-only) |
| `pregame-opportunity-contract-draft.md` (0.975) | drifted | backlog; **`lineup_opportunity.py`**; checkpoint-staging doc | **diverged → preserve as historical evidence** + superseded header/pointer; repoint code ref | header (not delete); code repoint (research lane) |
| `i4-card-source-experiment-draft.md` (0.934) | drifted | backlog | diverged → preserve + header | header only (no code refs) |
| `kcount-integration-prereg-draft.md` (0.905) | drifted | backlog; **`kcount_combiner.py`**; checkpoint-staging | diverged → preserve + header; code repoint | header + code repoint (research lane) |
| `i5-tail-challenger-draft.md` (0.81) | most drift | backlog; checkpoint-staging | diverged → preserve + header (highest unique-content risk) | header only |

## Slice shape (single PR when released)

- 6 headers/pointers + 6 moves to `docs/archive/prereg-drafts/` + 4 doc repoints
  + **3 code-file repoints (research lane sign-off required)**.
- Finals untouched (frozen evidence — per the never-modify rule).
- Validation: link check; grep zero references to draft basenames OUTSIDE
  archive/backlog/staging surfaces; results-index unaffected.
- **Blocking decision for the owner:** whether backlog references should point
  to finals or remain as historical markers (backlog is Chat 1/coordination's
  file — not edited from this lane).
