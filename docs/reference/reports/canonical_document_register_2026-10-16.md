# Canonical-document register — 2026-10-16 (Chat 3, report-first)

Machine-assisted classification of **all 203 tracked Markdown files** at
`origin/main` @ `1927c8c…` (register generated from the tracked tree; data:
`canonical_document_register_2026-10-16.csv` alongside this file — regenerate via
the Chat 3 census script; classes follow the six-way policy in
[`repo_quality_baseline_2026-10-16.md`](repo_quality_baseline_2026-10-16.md) §2).

## Class counts

| Class | Files | Rule |
|---|---|---|
| canonical-living | 70 | updated when its source of truth changes |
| frozen-evidence | 64 | experiment packets under `research/offseason_2026/`; addenda only, never retrospective edits |
| historical-evidence | 43 | `docs/archive/`, `docs/research/`, research notebooks; retain, errata only |
| operational | 26 | production runbooks/notebooks; update only when ops behavior changes |
| **Total** | **203** | |

Every row in the CSV carries: path, class, owner lane, **inbound relative-link
count**, and a disposition note. Superseded-class entries appear only after
individual audit (34 files already self-mark SUPERSEDED; the register keeps them
in their evidence class until an inbound-link + owner check approves a pointer).

## Notable register findings

1. **Zero-inbound "canonical-living" docs (54).** Mostly false alarms by design —
   root entry points (`README.md`, `CONTEXT.md`, `AGENTS.md`-linked) and skill
   definitions (`.cursor/skills/*/SKILL.md`, loaded by tooling, not by links).
   The remainder are the real consolidation candidates and are queued for the
   staleness audit (see [`docs_staleness_audit_2026-10-16.md`](docs_staleness_audit_2026-10-16.md)):
   `docs/agent/skills-catalog.md` vs `docs/agent/skills-provenance.md` overlap,
   and reference standards no other doc cites.
2. **Frozen-evidence mass (64 files)** is exactly the packet convention working:
   experiment cards, manifests, prereg docs. Disposition: never rewrite; the
   results index (PR #8) becomes their machine-readable front door.
3. **Duplicate draft/final packets (2 pairs)** carried into the register with
   `disposition: hold-owner`: `pa-k-baseline-prereg-draft.md` == final,
   `expanding-training-prereg-draft.md` == final (content-identical; owner decides
   archive-with-pointer).
4. **Ownership column** maps to lanes: `chat1` = science/builder, `chat2` =
   review/ops, `chat3` = repo health, `owner` = explicit owner decisions.

## Disposition summary (register-wide)

| Disposition | Count | Next action |
|---|---|---|
| keep (in active use or inbound-linked) | most | none |
| keep-entry-point (0 inbound but load-bearing) | ~40 | none; documented so audits don't misread them |
| consolidation candidate (canonical, 0 inbound, superseded content) | ~14 | staleness audit → bounded slice with owner |
| hold-owner (duplicates, canonicality questions) | 4 | owner decision (prereg pairs, prune_artifacts pair) |
| erratum candidate | 0 identified | none |

**Register is evidence, not authorization.** No file is deleted, moved, or
rewritten on this register alone; each cleanup requires its own approved slice
with the inbound-link list attached.
