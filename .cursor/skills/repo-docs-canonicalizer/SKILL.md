---
name: repo-docs-canonicalizer
description: Canonicalizes MLB-Props documentation — stale references, draft/final prereg pairs, SUPERSEDED banners, archive routing, and the source-of-truth index. Use when a doc contradicts current state, a draft/final pair is found, a living doc references a superseded file, or consolidation of documentation is planned.
---

# Docs canonicalizer

## Trigger
Doc sprawl; stale/dead references; `*-draft.md` pairs; missing SUPERSEDED
banners; docs describing behavior different from the repo; archive routing.
Does NOT apply to: frozen-packet content (banners only), code, CI, production.

## Explore first (required inventory before conclusions)
1. `docs/reference/reports/canonical_document_register_2026-10-16.csv` — class + inbound links per file.
2. Reference scan for the specific file (`git grep` basename across md/py/ps1/json/ipynb).
3. `supersession_graph_2026-10-16.csv` — does a living doc already point here?
4. Live-state check: `git fetch --prune`; overlap claim vs open PRs.

## Scope
All tracked `.md` files; archive moves; pointer edits. Never: research packet
content, code files, `docs/EXECUTION_BACKLOG.md`, production behavior.

## Evidence
For every proposed action: inbound-reference list (re-verified same-day), blob
identity for draft/final claims, class from the register, owner gate (if any).

## Allowed output
SUPERSEDED banner + pointer; archive plan (git mv + manifest + pointer list);
canonicalization slice spec; registered-prereq note for the results index.

## Never do
Delete a cited draft (escalate frozen-code citations to the research lane);
rewrite frozen packet content; mass "update all docs" passes; blank superseded
files; touch the backlog.

## Stop condition
Every touched doc has a disposition (kept / banner+pointer / archive-planned /
owner-gated) and zero broken links remain in the affected set.

## Escalation
Backlog repoint decisions → owner/coordination. Frozen-code citation repoints →
research lane (Chat 1) proposal. Deletion candidates → umbrella + owner.

## Glossary
Draft/final, SUPERSEDED, archive, pointer-not-copy — see
[repo-garbage-collector/LANGUAGE.md](../repo-garbage-collector/LANGUAGE.md).
Doc-specific: **canonical landing page** (the one doc that answers a question),
**isolation** (zero in/out edges — by design for entry points, a finding
otherwise).
