---
name: repo-dead-code-auditor
description: Proves or refutes dead-code claims in MLB-Props via static imports (bare, dotted, and Python.* convention), dynamic-import targets, string references, CLI/scheduled callers, and test references. Use when a module is suspected dead, an orphan file is found, or a deletion/quarantine of Python code is proposed.
---

# Dead-code auditor

## Trigger
A module/file is suspected dead; a deletion or quarantine of Python is
proposed; reachability of an entry point is questioned. Does NOT apply to:
research experiment packets (frozen evidence), notebooks, docs.

## Explore first (required inventory)
1. Full import scan with ALL conventions: bare stems, repo-dotted paths, and
   the `Python.*` internal convention (sys.path=src). (Real incident: skipping
   `Python.*` misflagged 7 modules; `bullpen.py` was proven active after
   correction.)
2. Dynamic-import targets: every `import_module`/`__import__` literal in the
   tree (58 sites at last audit).
3. String references as a module (qualified and bare) — dispatch tables live in
   strings.
4. CLI/scheduled/doc-as-instruction references (`git grep` across ps1/py/json/md).
5. Out-of-tree caveat: lake-archived runners and external schedulers are
   invisible — owner question required for anything ever doc-canonical.

## Scope
`src/`, `production/`, `models/`, `scripts/`, `research/` Python files. Never:
notebooks (artifact-lifecycle skill), docs (docs-canonicalizer), evidence
deletion.

## Evidence
Per candidate: importers (all forms), dynamic targets, string refs, CLI/doc
refs, test refs, entry-point status, last touch. Verdict classes: active /
test-only / static-orphan (referenced) / proven-dead (all zero + owner ruling) /
uncertain.

## Allowed output
Reachability verdict; quarantine ledger row; owner one-question memo; approved
narrow deletion PR (constitution Article 1 conditions ALL met).

## Never do
Delete on static evidence alone; treat "zero static importers" as "dead" when
any dynamic-import site exists unresolved; touch experiment packets; batch
deletions across path families.

## Stop condition
Every candidate carries the full evidence fields and either a verdict with
owner ruling or an explicit owner question. A "dead" claim without the
out-of-tree caveat answered is not a verdict.

## Escalation
Doc-canonical modules (e.g. listed in CONTEXT.md) → owner question before any
disposition. Frozen-code citation → research lane.

## Glossary
Static orphan, proven dead, uncertain, deletion test ("would deleting it
concentrate complexity?") — see
[repo-garbage-collector/LANGUAGE.md](../repo-garbage-collector/LANGUAGE.md).
