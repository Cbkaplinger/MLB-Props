# Orchestrator source pack — what to upload, what to leave out

Purpose: the curated file list an orchestrator chat should receive as uploaded
sources, plus the provenance and refresh rules for those uploads. Verified
against main on 2026-11-05 (re-verified at `466f98d` after the #57/#58/#59
integration). This file is a navigation layer; it duplicates no authority
below.

## Rules for the upload itself

- 8-12 files. Fewer, fresher files beat complete-looking stacks.
- Code and CI are read live from GitHub. Upload snapshots only for a focused
  audit, and remove them when the task closes.
- The permanent instruction field explains how to find the active SHA and task
  (run `git log --oneline -5`, read `docs/NEXT.md`). It never embeds a SHA,
  snapshot, or current-status text.
- Every uploaded file gets a provenance header (template at the bottom).

## Core pack (upload these)

| # | Path | Why | Status |
|---|---|---|---|
| 1 | `AGENTS.md` | Working rules + protected paths + role map | governing |
| 2 | `docs/EXECUTION_BACKLOG.md` | The ONE work queue: approvals, blockers, Snapshot PAST/PRESENT/FORWARD/DEFERRED | governing; refresh frequently |
| 3 | `docs/NEXT.md` | Current action and latest verified result (small, architect-owned) | governing; refresh frequently |
| 4 | `docs/roles/README.md` | Canonical roles, delivery cycle, approval + PR communication rules (ROLES_REV) | governing |
| 5 | role card for the orchestrator's job (`docs/roles/architect.md`, `chat1-builder.md`, `chat2-reviewer.md`, or `chat3-cleaner.md`) | The one card matching the chat's role | governing |
| 6 | `CONTEXT.md` | Glossary, lifecycle, grains, paths - adds vocabulary, not duplicate policy | reference |
| 7 | `docs/reference/pr_workflow.md` | Canonical PR/integration/authorization conventions | governing |
| 8 | `docs/DECISIONS.md` | The decision register (D1-D4). Adopted decisions live HERE, not in ADR files | governing |
| 9 | `docs/diagrams/00-index.md` + current architecture (`01-architecture.md`) and pipeline-stage (`19-pipeline-stages.md`) diagrams | Navigation plus data flow and boundaries, as Mermaid source | reference |
| 10 | `docs/reference/experiment_sop.md` + the ACTIVE assigned experiment card. As of 2026-11-05: platoon-information value is assigned (see `docs/NEXT.md`); its card is `docs/adr/PROPOSED-platoon-information-multiclass.md` with packet `research/offseason_2026/pregame_pa_ext/execution_packet_platoon_v1.md` - label it ASSIGNED, NOT EXECUTED | How the next experiment must be run + the actual next comparison | governing |
| 11 | `docs/reference/golden_metrics.md` | Canonical numbers - cite, never recompute | governing |
| 12 | `docs/reference/lineup_train_serve.md` | Train/serve timing contract (lineup proxy vs announced order) | governing |

Optional add-ons, only when relevant to the task:

- `docs/reference/pa_feature_lineage_2026-09-30.md` +
  `pa_split_provenance_correction_2026-09-30.md` - PA feature timing/provenance
  contracts, for any PA-lane or point-in-time question.
- `docs/reference/oddsapi_replay_architecture.md` - replay-spec work only.
- `docs/paper/manuscript.md` (+ `docs/paper/README.md`) - research background
  and claim status. Never the first source for today's task; it can lag
  accepted evidence. Do not upload `resume-summary.md` for orchestrator work.
- One actively-decided `PROPOSED-*` ADR, clearly labeled PROPOSED - only when
  a decision on it is actually pending (currently the 2026-10-21 delivery
  pair). Note: all ADR full texts are archived under
  `docs/archive/consolidated/adr/` and governed by `docs/DECISIONS.md`.
- Exception to that rule: the platoon card named in row 10 is a PROPOSED-file
  by location but is the owner-ASSIGNED active experiment - include it with an
  ASSIGNED-NOT-EXECUTED label, distinct from undecided proposals.
- `docs/reference/results_index.md` - machine-generated experiment index; not
  a source of truth until independently reviewed.
- For a code audit: the runner under review, its spec, its tests, and
  `.github/workflows/ci.yml` (temporary - remove after the task).

## Corrections to earlier pack proposals

- Do NOT upload `docs/AGENTS_ROLES.md`. It is superseded for current policy by
  `docs/roles/` (ROLES_REV 2026-10-28-r1). Upload `docs/roles/README.md` + one
  card instead.
- Do not hunt for "adopted ADR files". Adoption is recorded in the
  `docs/DECISIONS.md` register; the ADR directory holds only PROPOSED and
  archived text.
- A machine-generated `results_index.md` row with MISSING fields is not
  evidence; the verified result text lives in `docs/NEXT.md`.

## Never upload

- Full historical chat exports as governing context.
- Superseded preflight receipts without a specific lineage question.
- Raw datasets, protected partitions, or outcome files.
- Credentials, `.env`, account or machine inventories.
- Model artifacts and generated plots wholesale.
- Betting screenshots presented as validated evidence.
- Overlapping backlogs or "master plans" - `EXECUTION_BACKLOG.md` is the only
  queue; any drag-in gets reconciled into it and retired.
- Old metrics without cohort, timestamp, and experiment context.

## Provenance header (add to every uploaded file)

```
Repository: Cbkaplinger/MLB-Props
Path:
Source commit: (git rev-parse HEAD at upload time)
Snapshot date:
Status: governing / reference / proposed / historical
Supersedes:
Refresh trigger:
```

## Refresh triggers

Re-verify each file against current main before any re-upload:

- `docs/NEXT.md` or the backlog Session Snapshot changed -> refresh both.
- Roles revision (ROLES_REV bump) or PR-communication change -> refresh
  `docs/roles/README.md`, `docs/reference/pr_workflow.md`, `AGENTS.md`.
- New decision registered or an ADR adopted/rejected -> refresh
  `docs/DECISIONS.md`.
- Architecture or pipeline change -> refresh the touched diagram(s).
- The assigned experiment changes (closeout lands, new card assigned) ->
  swap the row-10 card and packet to the newly assigned pair.
- Between refreshes, GitHub is the live source of status; uploaded snapshots
  are stale by default.
