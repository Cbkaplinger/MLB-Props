# Cleanup skill taxonomy — 2026-10-16 (Chat 3, PROPOSED)

Six repo-owned skills split from the umbrella, per the Helios packaging pattern
(narrow triggers, stop conditions, non-goals, pointer-not-copy, bounded outputs).
**Proposal only — skill files are created by an approved slice** (they land in
`.cursor/skills/<name>/SKILL.md` + AGENTS.md pointer update; nothing written yet).
The umbrella `.agents/skills/repo-garbage-collector/` stays as policy source.

| Skill | Trigger (invoke when) | Inspects | May output | Must NEVER do | Stop condition |
|---|---|---|---|---|---|
| **repo-garbage-collector** (umbrella) | any cleanup task; routes to the five below | everything (delegates) | triage verdict, routed task, protected-class list | execute sub-skill work itself; delete anything | every finding routed or dispositioned |
| **repo-docs-canonicalizer** | doc sprawl, stale refs, draft/final pairs, archive routing | register CSV, inbound links, SUPERSEDED banners | pointer plan, consolidation slices, archive manifest | rewrite frozen evidence; delete before inbound-link zero + owner | every doc classified + disposition attached |
| **repo-dead-code-auditor** | dead-code claims, module reachability questions | static imports (bare + dotted + `Python.*`), dynamic targets, string refs, CLI/doc/scheduled refs, tests | reachability verdict, quarantine ledger row, owner question | delete on static evidence alone; ignore dynamic-import caveat | every candidate has importer/caller/owner evidence |
| **repo-artifact-lifecycle-auditor** | artifact class questions, notebook lifecycle, lake/Git boundary | file classes, manifests, generators, sizes, callers | lifecycle map, archival spec with mv-list + pointer list | move/delete evidence; touch lake | every artifact has a lifecycle state |
| **repo-ci-coverage-auditor** | CI green vs actual coverage doubts | testpaths, collected/excluded file lists, suite inventories | coverage map, minimal non-weakening fix spec | weaken the main suite; add path filters | collected+excluded lists are exact |
| **repo-dependency-hygiene** | import/declaration mismatches, lockfile questions | pyproject vs import surface, extras, env pins | declaration diff spec, taxonomy, lockfile recommendation | edit pyproject/CI without an approved slice | every import is declared or homed |

## Shared body rules (all six)

1. Report-first: findings commit to the quality-baseline branch before any PR.
2. Identity block on every handoff (repo, branch, base, HEAD, dirty, PR/CI).
3. Stop-and-report on any precondition failure (Helios fail-stop pattern).
4. Phase transitions gated on an artifact (audit file exists → then propose slice).
5. Security line: never print secret values; report file:line only.
6. Live-state check (`git fetch --prune`) before every overlap claim.
