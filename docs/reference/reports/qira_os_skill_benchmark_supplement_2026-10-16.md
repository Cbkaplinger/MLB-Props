# Qira-OS skill benchmark supplement — 2026-10-16 (Chat 3, report-first)

Additive supplement to [`skill_benchmark_2026-10-16.md`](skill_benchmark_2026-10-16.md) —
the original benchmark is NOT altered. **Repository access resolved:** the
earlier blocker was an offline D: volume behind the junction
`C:\Users\ckaplinger\Downloads\Helios → D:\Helios`; the SSD is now mounted.

## Repository identity

| Item | Value |
|---|---|
| Local path | `D:\Helios\qira-os` |
| Remote | `https://lenovoqira.ghe.com/Lenovo-Qira/qira-os.git` |
| Branch / HEAD | `main` / `ad1d5e9f80d95e96a66bbcbf3a8b0cca8cc658d4` |
| Dirty state | 3 modified lines (noted, not inspected — not our lane) |
| Skills corpus | 28 skills under `.cursor/skills/` |
| Method | frontmatter + full-body reads of `improve-codebase-architecture`, `setup-qira-skills`; repo-wide guardrail-pattern scan; structural inventory (references/, scripts/) |
| Limitations | 3 of 28 skills read in full; pattern scan is regex-based; qira-os domain content (Linear/qira-core/i18n) is out of scope by design |

## Verdicts on the original benchmark's 8 claimed patterns

| Pattern (from `skill_benchmark_2026-10-16.md`) | Qira-OS verdict | Evidence |
|---|---|---|
| Explicit stop conditions | **supported + refined** | refined: qira-os expresses stops as *workflow gates tied to artifacts* ("Do not start TDD until the page has a teach-back sentence: which file, which consumer, which live signature") and *precondition fail-stops* ("When the MCP call fails: Stop. Do not guess ticket contents") |
| Non-goals in the body | **supported** | "This skill **finds evidence at known paths**... does not parse NDJSON itself and does not write ticket code" |
| Pointer-not-copy | **supported + refined** | refined into a *companion-file convention*: skills carry `LANGUAGE.md`/`DEEPENING.md`/`INTERFACE-DESIGN.md` next to `SKILL.md` and link, never inline ("Full definitions in LANGUAGE.md"; "Point, then Read") |
| Fast-path + runbook split | **supported** | helios-qira-build: "The full failure playbook lives at <path>; this skill is the fast path" |
| Error-code triggers | **supported** | frontmatter descriptions enumerate exact symptoms (os error 112, 0xc0000409, "merge-queue ejections") so routing happens at description-read time |
| Fail-stop discipline | **supported** | setup-qira-skills: "This is a prompt-driven skill, not a deterministic script... confirm with the user, then write" |
| Credential hygiene | **supported** | "Do not print tokens" inline in the workflow |
| Gate-before-next-phase | **supported + refined** | refined into **human approval gates**: present findings, walk decisions ONE at a time, get the answer, then proceed ("present a section, get the user's answer, then move to the next") |

**No pattern was contradicted.** Two refinements are substantive (below).

## New Qira-OS conventions worth adopting (not in our benchmark)

1. **Companion language files.** Each skill pairs `SKILL.md` (workflow) with a
   `LANGUAGE.md` (glossary: "Use these terms exactly... Consistent language is
   the point — don't drift"). Our audits produced exactly this vocabulary
   (dead/quarantine/archive/annotate, prereg draft/final, lifecycle states) —
   it should live in a shared `CLEANUP-LANGUAGE.md`, referenced by all six skills.
2. **Domain-informed, no-re-litigate rule.** "The skill is _informed_ by the
   project's domain model... ADRs record decisions the skill should not
   re-litigate." Ours: skills must treat the evidence-maturity register, the
   deletion ledger, and owner rulings as settled — never re-derive them.
3. **Setup/onboarding skill convention** (`setup-qira-skills`): an explicit
   bootstrap skill that scaffolds per-repo configuration (issue tracker, labels,
   domain-doc layout) with **one-decision-at-a-time user confirmation**. For us:
   a `setup-repo-cleanup-skills` step that records the repo's paths (backlog,
   golden metrics, reports dir, lake boundary) the first time cleanup runs.
4. **Explore-don't-assume preflight.** Enumerate the surfaces to read before
   acting; "Read whatever exists; don't assume."
5. **Deletion test as doctrine** ("imagine deleting the module; if complexity
   vanishes it was a pass-through") — a sharper decision heuristic than our
   reference-count approach; adopt as an auxiliary check in the dead-code auditor.

## Reject (Qira-OS specifics, not portable)

Linear/qira-core/i18n/OTEL domain content; `disable-model-invocation` slash-only
routing (our skills are model-invoked by design); repo-specific paths
(`C:\qwt`, Lenovo remotes).

## Proposed MLB-Props `.cursor/skills/` tree (report-only — created by the approved slice)

```text
.cursor/skills/
  repo-garbage-collector/            # UMBRELLA (routed to; keeps 11-phase policy)
    SKILL.md                         # routing + global prohibitions + protected classes
    references/
      cleanup-policy.md              # moved/extended from .agents copy (pointer-not-copy)
      metric-invariants.md
      verification-checklist.md
  repo-docs-canonicalizer/SKILL.md
  repo-dead-code-auditor/SKILL.md
  repo-artifact-lifecycle-auditor/SKILL.md
  repo-ci-coverage-auditor/SKILL.md
  repo-dependency-hygiene/SKILL.md
  CLEANUP-LANGUAGE.md                # shared glossary (single source of terms)
AGENTS.md                            # + one pointer line to the skill block
```

Minimal SKILL.md shape (per specialist, ~30 lines): frontmatter (name +
description with concrete triggers incl. artifact names, e.g. "when a module is
suspected dead, when a draft/final pair is found") → inspects → may output →
never-do → stop condition → pointer to `CLEANUP-LANGUAGE.md` + the umbrella.
No scripts initially (qira-os also keeps scripts minimal: 2 dirs across 28 skills).

## Migration plan (11-phase umbrella → umbrella + specialists, backward-compatible)

| Phase (current umbrella body) | Goes to | Compatibility rule |
|---|---|---|
| Phase 0 baseline / Phase 1 evidence graph | umbrella (stays) — every specialist runs it first | unchanged |
| Phase 2 docs GC + backlog contract | repo-docs-canonicalizer | backlog-sole-ledger rule moves with it; umbrella keeps a pointer |
| Phase 3 Python GC | repo-dead-code-auditor | adds deletion-test heuristic + dynamic-import resolution from our audits |
| Phase 4 notebooks | repo-artifact-lifecycle-auditor | merges artifact census conventions |
| Phase 5 static + deps | repo-dependency-hygiene | current "existing toolchain first" sequencing preserved |
| Phase 6 artifacts | repo-artifact-lifecycle-auditor | lake/Git boundary rule preserved |
| Phase 7 metrics + populations | umbrella (stays) — domain-specific, cross-cutting | unchanged; specialists cite it |
| Phase 8 batches + Phase 9 verify | umbrella (stays) — execution/verification law | unchanged; verification-checklist.md remains referenced |

Backward compatibility: the umbrella keeps the full 11-phase text until the six
specialists exist; the migration commit is one additive PR (new files + umbrella
routing table); no phase text is deleted until each specialist's body has been
reviewed, so an agent invoking only the umbrella behaves exactly as today.
