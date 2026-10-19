---
name: repo-docs-canonicalizer
description: Language rules for repo-docs-canonicalizer. Canonical, landing page, supersession, banner, pointer, repoint, draft/final lineage.
---

# Docs-canonicalizer language

- **Canonical landing page** — the single doc designated to answer a question (see source-of-truth index). Consolidation routes readers TO it.
- **Banner** — one-line `> SUPERSEDED: see <target>` at the top; content untouched below.
- **Pointer** — an edit replacing a stale reference with the current target. Pointers replace copies; never duplicate content.
- **Repoint** — updating a REFERENCE (in docs, code docstrings, tests) from a draft/superseded file to its canonical successor. Repointing frozen-code references is a research-lane action, not cleanup.
- **Draft/final lineage** — `*-draft.md` (pre-freeze working copy) vs the registered final. Drafts are superseded by definition; retention is the default while any reference exists.
- **Isolation** — zero inbound AND outbound links. By design for entry points (skills, README, CONTEXT); a consolidation candidate otherwise.
- **Archive** — `git mv` into `docs/archive/...` with a manifest README and same-slice pointer updates. History preserved; reversible.
