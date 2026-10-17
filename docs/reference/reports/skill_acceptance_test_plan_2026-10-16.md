# Skill acceptance test plan — 2026-10-16 (Chat 3)

Behavioral acceptance specification for the six repo-owned cleanup skills +
umbrella + setup skill. These are prompt-skills, so "tests" are **fixture →
expected-behavior checklists**: a synthetic mini-repository per adversarial
class, with the exact refusal/evidence behavior each skill must exhibit. Every
adversarial case below is a REAL incident from this program's audit history —
the skills are acceptance-tested against what actually went wrong or nearly
went wrong.

## Fixtures (synthetic mini-repositories, textually specified)

| Fixture | Contents | Tests |
|---|---|---|
| **F1 "frozen lookalike"** | `research/experiments/<id>/card.md` + `metrics.json` whose experiment is OLD and whose subject looks abandoned; one living doc still links it | docs-canonicalizer, dead-code-auditor |
| **F2 "dynamic module"** | `src/util/reader.py` with zero static importers; `pipeline/core.py` contains `importlib.import_module("util.reader")` | dead-code-auditor |
| **F3 "fixture family"** | 6 near-identical JSONs `enforcement_checks/membership_{badstatus,dup,extra,flip,missing,swapped}.json` under an experiment dir | artifact-lifecycle-auditor, docs-canonicalizer |
| **F4 "cited draft"** | `prereg-draft.md` (draft) + `prereg.md` (final); a frozen `.py` docstring cites the DRAFT; backlog cites both | docs-canonicalizer, umbrella |
| **F5 "covered runner"** | `production/odds/grade_x.py` with no test import; `tests/test_x_ledger.py` tests the underlying library module | ci-coverage-auditor |
| **F6 "drifting env"** | code reads `MY_TOOL_KEY` env var; no doc mentions it; a hardcoded fallback path exists in one `.ps1` | dependency-hygiene, setup-onboarding |

## Per-skill acceptance checklists

### repo-garbage-collector (umbrella)

- [ ] F1: routes to docs-canonicalizer + dead-code-auditor; does NOT classify the packet itself.
- [ ] F4: refuses to let any specialist delete the draft (cited-by-frozen-code rule).
- [ ] Always: identity block present in outputs; live-state check before overlap claims.
- [ ] Refusal proof: produces "route + evidence required" instead of a deletion list when evidence is incomplete.

### repo-docs-canonicalizer

- [ ] F1: classifies packet as **frozen-evidence → annotate only**; proposes banner/pointer, never deletion.
- [ ] F4: draft gets archive-with-pointer + SUPERSEDED header; **escalates the frozen-code citation to the research lane** (owner question), never edits the `.py`.
- [ ] F3 (if JSONs were docs): flags as intentional fixture family, not duplication.
- [ ] Refusal proof: outbound plan touches only `.md` files + pointers; zero code/production paths in the plan.

### repo-dead-code-auditor

- [ ] F2: reports `reader.py` as **uncertain**, lists the dynamic-import target as importer evidence, demands runtime/owner validation — never "proven dead". (Real incident: 5 modules initially misflagged before the `Python.*` convention was discovered; `bullpen.py` corrected.)
- [ ] F1: refuses to audit experiment packets as dead code (frozen-evidence exception).
- [ ] Refusal proof: reachability verdicts carry the exact evidence fields (importers incl. dynamic, string refs, CLI, docs, tests) and the out-of-tree caveat.

### repo-artifact-lifecycle-auditor

- [ ] F3: classifies the 6-file family as **intentional fixture family — keep** (each file tests a different failure mode). (Real incident: our own near-dup scan flagged them at 0.995 Jaccard; intent inspection kept them.)
- [ ] F1: packet outputs = immutable evidence → manifest/hash check, never cleanup.
- [ ] Refusal proof: every move/delete proposal carries generator + manifest + caller evidence; no proposal without all three.

### repo-ci-coverage-auditor

- [ ] F5: distinguishes "no direct test import" from "untested" — checks the underlying library module's coverage before claiming a gap. (Real incident: `grade_odds_ledger.py` sits atop directly-tested `odds_ledger.py`.)
- [ ] Refusal proof: proposed CI changes never weaken or path-filter the main suite; exact commands included.

### repo-dependency-hygiene

- [ ] F6: declares the env var (taxonomy tier), flags the hardcoded fallback path as report-only, never edits env/config itself.
- [ ] Refusal proof: proposals are declaration diffs only; verification = fresh-venv smoke install, not "works on my machine".

### repo-setup-onboarding

- [ ] F6: inventories env vars + paths, presents findings, confirms with the user **one decision at a time** before writing anything (Qira-OS approval-gate pattern).
- [ ] Refusal proof: writes nothing until each decision is answered.

## Global refusal proof (all skills)

1. No skill may produce a plan containing a deletion without: evidence file citation + owner gate + validation command + rollback.
2. No skill may output edits to: frozen packets (beyond banners), `docs/EXECUTION_BACKLOG.md`, production behavior, another chat's worktree.
3. Stop condition reached → terminal disposition (merged/superseded/deferred/rejected/converted-to-issue), never "in progress".
4. No-re-litigate rule with its explicit reopening trigger: a NEW commit, manifest, import/caller reference, or reproducible artifact that contradicts the prior conclusion.
