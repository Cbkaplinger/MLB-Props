---
name: repo-artifact-lifecycle-auditor
description: Classifies MLB-Props artifacts and notebooks by lifecycle state (canonical source, immutable evidence, reproducible generated output, lake-only, cache, duplicate, fixture family, deletion candidate) and validates the lake/Git boundary. Use when a notebook or artifact's purpose, provenance, retention, or archival is questioned.
---

# Artifact lifecycle auditor

## Trigger
A notebook/artifact's purpose or retention is questioned; archival of
notebooks is planned; the lake/Git boundary needs verification; a group of
similar artifacts needs intent classification. Does NOT apply to: Python module
reachability (dead-code auditor), docs (docs-canonicalizer).

## Explore first (required inventory)
1. Tracked-tree classification by path/extension + Git blob identity.
2. Caller evidence (`git grep` basename across md/ps1/py/json) — including
   subprocess and scheduler references.
3. Generator + manifest check: does a declared generator and hash manifest
   exist? (Convention: lake holds bulk; Git holds identity.)
4. Fixture-family intent check: near-identical evidence files that each differ
   in one semantic field are INTENTIONAL (e.g. enforcement negative-probes),
   not duplication.

## Scope
`*.ipynb`, `models/**`, `research/**` artifacts, `docs/paper/figures`, report
CSV/JSON, figures and binaries. Never: lake contents (out of Git), frozen
packet content, production behavior.

## Evidence
Per item: lifecycle state (canonical source / immutable evidence / reproducible
generated / lake-only / cache / duplicate / fixture family / unknown), callers,
generator+manifest, size, last touch. Unknown is a valid state with the exact
evidence needed to resolve it.

## Allowed output
Lifecycle map; archival spec (git mv list + archive manifest + pointer
edits); retention note; owner-gated deletion-candidate row.

## Never do
Move or delete immutable evidence; propose lake migration for Git-held provenance
(boosters, figures) without owner order; treat a fixture family as duplication;
strip notebook outputs from operational surfaces.

## Stop condition
Every artifact in the audited set carries a lifecycle state and a disposition
(keep / archive-planned / owner-gated / intentional-family).

## Escalation
Model-artifact changes → Chat 1/owner. Operational-notebook changes → ops owner.
Any evidence deletion → umbrella + owner.

## Glossary
Lifecycle states, fixture family, lake-only — see
[repo-garbage-collector/LANGUAGE.md](../repo-garbage-collector/LANGUAGE.md).
