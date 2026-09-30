# Skill Catalog

Project skills in `.cursor/skills/<name>/SKILL.md`. All carry `disable-model-invocation: true`: they run only when the user types the slash command. Pre-existing skills (`repo-quality-passthrough`, `.agents/skills/repo-garbage-collector`) are unaffected.

Note: `repo-quality-passthrough` predates the Purpose/Preconditions/.../Stop-conditions section standard and is grandfathered in `scripts/agent/validate_skills.py` (missing sections warn, not fail). It was not modified by this pass.

## Routing

| If the user asks... | Use |
|---|---|
| Is this feature leaking? | `/audit-feature-leakage` |
| How should we test this idea? | `/design-ml-experiment` |
| Does this challenger beat the champion? | `/compare-champion-challenger` |
| Is this backtest/ROI honest? | `/audit-backtest-integrity` |
| Do these baseball totals tie out? | `/reconcile-baseball-stats` |
| What did past research conclude? | `/archive-research-memory` |
| Is this diagram/doc current? | `/document-architecture` |
| Record this decision. | `/write-adr` |
| These two modules do the same thing. | `/consolidate-code` |
| What code is dead? | `/audit-dead-code` |
| Where is the architecture shallow? | `/improve-codebase-architecture` |
| Pressure-test my plan. | `/grill-with-docs` |

## Skills

### audit-feature-leakage

- What: read-only leakage audit of features, joins, and dataset builds.
- When: adding or reviewing features, rolling windows, joins, train/serve paths.
- Slash: `/audit-feature-leakage`. Inputs: module/card, grain, availability claim. Writes: none.
- Context: `src/Python/`, registries, manifests. Output: lineage table, severity table, blocking findings.
- Related: `/design-ml-experiment`, `/reconcile-baseball-stats`. Misuse: asking it to fix or run anything.

### design-ml-experiment

- What: immutable experiment card draft, planning only.
- When: proposing a feature, challenger, calibration, or policy test.
- Slash: `/design-ml-experiment`. Inputs: hypothesis, comparator, population/splits. Writes: none (draft text for approval).
- Context: `experiment_sop.md`, prior cards. Output: card + manifest skeleton + deviations template.
- Related: `/compare-champion-challenger`, `/grill-with-docs`. Misuse: asking it to execute the experiment.

### compare-champion-challenger

- What: read-only verdict on a challenger vs the frozen champion.
- When: judging a challenger or reviewing a promotion claim.
- Slash: `/compare-champion-challenger`. Inputs: champion/challenger ids, panel identity, tier claimed. Writes: none (summary only if authorized).
- Context: `champion_challenger_protocol.md`. Output: gate verdict table, PROMOTE/HOLD/RESEARCH gaps, rollback status.
- Related: `/audit-backtest-integrity`, `/design-ml-experiment`. Misuse: promoting from 2026 slices.

### audit-backtest-integrity

- What: read-only integrity audit of a backtest or replay ledger.
- When: reviewing a backtest, replay, or ROI claim.
- Slash: `/audit-backtest-integrity`. Inputs: replay identity, claimed slice/metric, price/clock definitions. Writes: none.
- Context: `oddsapi_replay_architecture.md`, `experiment_sop.md` section 8. Output: integrity table + honest claim restatement.
- Related: `/compare-champion-challenger`. Misuse: asking for a retune from the findings.

### reconcile-baseball-stats

- What: read-only reconciliation of derived totals to official records.
- When: totals disagree, attribution unclear, dataset validation.
- Slash: `/reconcile-baseball-stats`. Inputs: derived total, official source, grain. Writes: none.
- Context: pipeline code, cards, manifests. Output: layer reconciliation table + residual list + verdict.
- Related: `/audit-feature-leakage`. Misuse: asking it to rebuild or relabel data.

### archive-research-memory

- What: index of research history; originals untouched.
- When: consolidating reports, onboarding to a thread, finding contradictions.
- Slash: `/archive-research-memory`. Inputs: thread, source list, destination. Writes: one new index file only.
- Context: reports, cards, choice log. Output: index + contradiction register + superseded map.
- Related: `/document-architecture`, `/write-adr`. Misuse: asking it to rewrite or delete sources.

### document-architecture

- What: verify docs/diagrams against code; fix prose.
- When: docs drift, onboarding, pipeline-map audit.
- Slash: `/document-architecture`. Inputs: scope, verification depth. Writes: docs only.
- Context: `repo_canonical_map.md`, tree. Output: updated doc + change table.
- Related: `/improve-codebase-architecture`, `/write-adr`. Misuse: asking for code changes.

### write-adr

- What: decision record with evidence.
- When: a durable choice needs capturing.
- Slash: `/write-adr`. Inputs: decision, status, evidence. Writes: one ADR file.
- Context: `docs/adr/TEMPLATE.md`. Output: ADR path + promotion checklist if Proposed.
- Related: `/grill-with-docs`, `/archive-research-memory`. Misuse: inventing Accepted without evidence.

### consolidate-code

- What: duplicate-behavior consolidation plan; characterization tests first.
- When: two modules share behavior, wrappers overlap, seam needs one owner.
- Slash: `/consolidate-code`. Inputs: candidates, caller list, compatibility constraint. Writes: plan only by default; edits only with explicit approval.
- Context: callers, schedules, notebooks. Output: owner/deprecation/migration/rollback plan.
- Related: `/audit-dead-code`, `/improve-codebase-architecture`. Misuse: broad unsupervised merges; mixing research and production.

### audit-dead-code

- What: dead-code classification by confidence; never deletes.
- When: pruning scripts, notebooks, modules.
- Slash: `/audit-dead-code`. Inputs: scope, liveness definition. Writes: none.
- Context: imports, schedulers, history. Output: classification table + smoke checks.
- Related: `/consolidate-code`. Misuse: asking it to delete.

### improve-codebase-architecture

- What: survey for deepening opportunities + HTML report + grill the pick (adapted from Matt Pocock, MIT).
- When: modules feel shallow, logic leaks, tests are hard.
- Slash: `/improve-codebase-architecture`. Inputs: scope, report depth. Writes: temp HTML report only.
- Context: `CONTEXT.md`, `docs/adr/`. Output: report path + candidates + grilling record.
- Related: `/consolidate-code`, `/document-architecture`. Misuse: asking it to implement; proposing retrains or policy changes.

### grill-with-docs

- What: relentless interview with inline doc updates (adapted from Matt Pocock, MIT).
- When: before building anything fuzzy.
- Slash: `/grill-with-docs`. Inputs: plan, decision owner. Writes: `CONTEXT.md` touch-ups / ADR offers only.
- Context: `CONTEXT.md`, `docs/adr/`. Output: resolved plan + open questions + docs touched.
- Related: `/design-ml-experiment`, `/write-adr`. Misuse: asking it to implement or run the plan.

## Deferred (not installed)

validate-temporal-splits, audit-data-lineage, audit-training-serving-skew (fold into leakage/experiment skills), audit-model-calibration, promote-model-candidate, review-experiment-card, zoom-out (not in Matt's catalog; qira-os file not copied), tdd, grill-me, diagnosing-bugs, domain-modeling, code-review (user-global later from Matt, with MIT notice and no MLB rules; never duplicated here).

## Suggested sequences

- Ops understanding (read-only first): `/audit-dead-code` bounded to `market_research/` -> `/archive-research-memory` (report index) -> `/write-adr` (contract decisions) -> `/grill-with-docs` (MLflow A/B, research isolation).
- PA overhaul: `/archive-research-memory` -> `/audit-feature-leakage` -> `/improve-codebase-architecture` -> `/design-ml-experiment`.
- Do not start OPS-1 implementation or OPS-2 before Checkpoint A review + scoped commit clear (see backlog FORWARD).
