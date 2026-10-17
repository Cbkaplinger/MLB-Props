# Cleanup constitution (draft v1) — 2026-10-16 (Chat 3)

Short governing document for future cleanup PRs. **Draft** — adoption rides the
governance vehicle (role-card PR or PR #10 refresh, one of them). Until adopted,
the standing owner rules remain authoritative; this draft consolidates them so
adoption is a pointer, not a renegotiation.

## Article 1 — What cleanup may DELETE (all conditions required)

1. Proven zero references: zero static imports (bare + dotted + `Python.*`),
   zero dynamic-import targets, zero string references as a module, zero CLI
   callers, zero scheduled/deployment references, zero test references.
2. Owner ruling recorded (one word in the ledger or backlog) for anything that
   was ever doc-canonical.
3. Full inbound-reference list attached to the PR body, re-verified same-day.
4. Rollback path stated (`git revert` suffices; no history rewrites).
5. Post-change validation command green (pytest + link check + zero-match grep).

## Article 2 — What must be ARCHIVED (moved with manifest, never deleted)

1. Lineage notebooks superseded by living code (`src/Notebooks/` class).
2. Draft artifacts superseded by finals (prereg draft==final pairs) — unless the
   owner chooses retain-as-lineage.
3. Any file with historical value whose inbound references are only historical
   docs. Moves preserve git history; every move ships with a manifest README and
   same-slice pointer updates.

## Article 3 — What may only be ANNOTATED

1. Frozen experiment packets (cards, manifests, prereg docs): addenda/banners
   only — never retrospective edits, never relabeling failure evidence.
2. Dated evidence reports: SUPERSEDED banners + forward pointers.
3. Blob-identical duplicates inside experiment packets where the copy may be
   intentional lineage (annotate pending owner ruling).
4. Anything whose classification is uncertain: retain-but-flag with the exact
   evidence needed to decide.

## Article 4 — What requires OWNER sign-off

1. Any deletion from Article 1 that touched doc-canonical surfaces.
2. Any change to protected production paths (`AGENTS.md` protected list).
3. Dependency tier changes and lockfile adoption.
4. CI workflow changes (even coverage-preserving ones).
5. Any consolidation that merges or removes a canonical living document.
6. Notebook archival; schedule/registry reconciliation; operator-flow changes.

## Article 5 — What cleanup must NEVER change

1. Frozen scientific registrations, registration hashes, endpoint/seed/bootstrap
   definitions, or experiment outputs.
2. `docs/EXECUTION_BACKLOG.md` work-state (other lanes own it).
3. Evidence of failed runs (preserved, clearly labeled — e.g. the `count_b1`
   failed directory).
4. Metric definitions, golden-metric numbers, or population semantics.
5. Another chat's worktree, branch, or open PR.
6. The main suite's test semantics (coverage additions must not weaken or
   path-filter it).

## Article 6 — Process law

1. One task, one owner, one branch, one PR; one active PR per path family.
2. Report-first: every destructive action cites a committed evidence artifact.
3. Live-state check before every overlap claim; `git fetch --prune` first.
4. No direct pushes to main; no force-push; no history rewrites.
5. Status reports deliver a deliverable, a decision, or a concrete blocker.
6. Every cleanup task closes with a disposition: merged / superseded / deferred /
   rejected / converted-to-issue. Never an ambiguous "in progress".
7. Skills own their scope (taxonomy doc); the umbrella routes; the constitution
   overrides any skill instruction on conflict.
