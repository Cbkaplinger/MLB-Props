# Documentation consolidation design — 2026-10-16 (Chat 3, PROPOSED, staged)

Target information architecture for the 203 tracked Markdown files, built on the
canonical-document register + staleness audit. **Design only — no document is
edited, moved, or deleted by this proposal.** Each stage is small, reversible,
and separately approvable.

## Target architecture

```text
docs/
  EXECUTION_BACKLOG.md        work-state (unchanged; Chat 1/coordination lane)
  reference/                  LIVING standards + current state + machine indexes
    current_state_*.md        research narrative (PR #4)
    results_index.{md,csv}    machine evidence (PR #8)
    pr_workflow.md            PR/review/merge standard (PR #10) + template pack
    repo_canonical_map.md     surface classification
    golden_metrics.md         citable numbers (cite-only)
    pipeline_registry.json    machine pipeline catalog
  agent_roles/                role cards (planned governance slice)
  diagrams/                   dated visual maps (00–06)
  reports/                    point-in-time evidence (frozen; errata only)
  paper/                      publication surfaces
  research/ + archive/        historical evidence (immutable)
  RUNBOOK-class ops docs      stay beside production/ (operator proximity)
```

Principles: one authoritative home per question (source-of-truth index);
living docs link down to evidence, evidence never links up as authority;
historical material is immutable; **pointers replace copies**.

## Staged consolidation sequence (small, reversible PRs)

| Stage | Content | Files touched | Reversibility |
|---|---|---|---|
| S1 | Role cards + template-pack adoption + AGENTS.md pointer (already sequenced T1) | new dir + 2 pointer lines | trivial revert |
| S2 | Superseded-pointer pass: banners + forward links on stale-flagged docs (register list) | ~14 doc edits, 0 deletions | trivial |
| S3 | `src/Notebooks/` archival: move to `docs/archive/legacy-notebooks/` + README manifest (post caller-validation T11) | ~10 moves + 1 manifest | git mv history preserved |
| S4 | Draft==final prereg pair resolution (archive drafts with pointer) | 2 files | trivial |
| S5 | INDEX completeness pass for undocumented production entry points (ops audit finding 1) | `production/INDEX.md` sections | trivial |
| S6 | Canonical landing-page polish: README/AGENTS link the source-of-truth index once #4/#8/#10 land | 2 files | trivial |
| S7 (deferred) | Any actual deletion — only after inbound-link zero-check + owner sign-off per the register's delete gates | — | — |

Redirect/pointer convention: superseded files get a one-line banner
(`> SUPERSEDED: see X`) and keep their content — never blanked, never deleted
before the inbound-link count is zero and the owner approves.
