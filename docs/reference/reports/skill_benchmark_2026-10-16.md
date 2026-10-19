# Skill benchmark — Helios/user-global skills vs our cleanup corpus (2026-10-16, Chat 3)

Sources inspected (read-only): our `.agents/skills/repo-garbage-collector/SKILL.md`
(+ 3 reference files); user-global Helios-derived skills `helios-ticket-attack`,
`helios-qira-build`, `idart-jira` (the qira-os monorepo skill tree is not cloned
locally — the four user-global skills are the available corpus; the VoltAgent
"awesome-agent-skills" packaging principles are taken from the coordination brief).
Confidence: HIGH on what was read.

## Patterns extracted from the Helios-derived skills

| Pattern | Observed in | Essence |
|---|---|---|
| **Explicit stop conditions** | `helios-ticket-attack` ("When to stop": PASS/INCONCLUSIVE → write pass 1, recommend close, do NOT offer other skills) | a skill ends in a named terminal state, not open-endedly |
| **Non-goals in the body** | `helios-ticket-attack` ("does not parse NDJSON itself and does not write ticket code") | scope defended in prose, not just frontmatter |
| **Pointer-not-copy** | `helios-ticket-attack` ("Do not copy live-repro... skills into this file. Point, then Read") | skills reference each other; no duplicated methodology |
| **Fast-path + runbook split** | `helios-qira-build` ("full failure playbook lives at <path>; this skill is the fast path") | routine path in the skill; exhaustive path in a referenced runbook |
| **Error-code triggers** | `helios-qira-build` description (os error 112, 0xc0000409 → this skill) | triggers include the exact symptoms that should route here |
| **Fail-stop discipline** | `idart-jira` ("When the MCP call fails: Stop. Do not guess ticket contents") | on precondition failure: halt and report, never improvise |
| **Credential hygiene line** | `idart-jira` ("Do not print tokens") | security rule stated inside the workflow |
| **Gate-before-next-phase** | `helios-ticket-attack` ("Do not start TDD until the page has a teach-back sentence") | phase transitions require an artifact, not an intention |

## Our current corpus vs that standard

`.agents/skills/repo-garbage-collector/SKILL.md` is methodologically deep
(11 phases, guardrails, acceptance) and already matches several patterns
(read-only git guardrails, evidence-first, backlog-as-sole-ledger, "no delete on
zero-import alone", never print secrets). Gaps against the Helios standard:

| Gap | Consequence | Verdict |
|---|---|---|
| One giant prompt covering docs/code/notebooks/deps/CI/metrics | blurred ownership; every cleanup pulls the whole 11 phases | **adopt the split** (taxonomy proposal) |
| No stop conditions / terminal states | audits ran long; reports accumulated without dispositions | **adopt** |
| No per-phase output contract | findings not machine-actionable | **adopt** (report → ledger → slice spec chain, already emerging in our reports) |
| No trigger routing between skills | future agents re-discover from scratch | **adopt** |
| Written as prompt, not packaging (no bounded outputs) | inconsistent depth across runs | **adapt** |
| Phase 9 independent-verifier requirement | stronger than Helios pattern | **keep — ours is better here** |
| Metric-population reconciliation phase | domain-specific, no external analogue | **keep — ours is better here** |

**Reject:** copying any Helios domain content (Linear/qira/OTEL specifics) — the
lesson is the packaging pattern only. **Adapt:** our single skill becomes the
umbrella policy; six narrow skills inherit phases as their bodies.
