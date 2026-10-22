# ADR (PROPOSED 2026-10-21): Evidence-driven, checkpoint-based delivery

**Status:** Proposed; requires publication and review. No scientific
authorization is granted by this ADR.

## Context

The repository's canonical rules define scientific safeguards and agent
responsibilities, but the documented reviewer role conflicts with the
newly requested trailing-fixer workflow. Existing audits also show that
reusable provenance and contract mechanisms already exist, so a new parallel
governance or experiment platform would risk duplication.

## Decision

Adopt **evidence-driven, checkpoint-based delivery** with a small control
plane and explicit scientific gates.

| Responsibility | Accountable role | Required output |
|---|---|---|
| Architecture, scope, sequencing | Architect | Bounded assignment, acceptance criteria, dependency decision |
| Scientific implementation | Chat 1 | Tested builder checkpoint |
| Trailing review and bounded repairs | Chat 2 | Findings or repair checkpoint with regression evidence |
| Independent acceptance of repairs | Qualified non-author | Verdict on exact repair/integrated SHA |
| Temporary documentation cleanup | Chat 3 | Approved deliverable and residual-risk handoff |
| Restricted actions | Owner | Explicit authorization where required |

### Operating invariants

- Every active task has one owner, bounded paths, acceptance criteria, and a
  closure condition.
- One task record links its implementation, tests, verdict, and artifacts;
  narrative progress reports do not create parallel queues.
- Separate worktrees remain mandatory.
- Chat 1 and Chat 2 may publish to the research integration branch only under
  the documented shared-branch exception.
- Publication requires current-head reconciliation and affected-suite
  verification.
- Findings and verdicts identify immutable SHAs.
- A fixer cannot independently accept its own repair.
- Execution, result acceptance, merge, and production promotion remain
  separate states.
- Frozen registrations and owner-only authorization boundaries outrank this
  ADR.
- New evidence appends or supersedes historical evidence; it does not rewrite
  it.
- Routine updates use artifact links and short deltas rather than repeated
  full-context summaries.

### Contract enforcement

Introduce executable checks incrementally around existing infrastructure:

1. Validate consumed input identities and the registered evaluation
   population.
2. Validate declared endpoints, baseline identities, and required output
   schemas.
3. Exercise the real entry point on synthetic fixtures, including expected
   failures.
4. Bind acceptance to the code, contract, inputs, and environment identities
   actually used.
5. Preserve a clear distinction between execution success and scientific
   success.

### Alternatives rejected

| Alternative | Reason |
|---|---|
| Return to alternating builder/reviewer dialogue | Reintroduces routine handoff waiting |
| Unrestricted concurrent writers | Increases integration ambiguity |
| Chat 2 repairs and self-approves | Removes independent acceptance |
| Build a bespoke agent orchestration platform now | Adds infrastructure before the lightweight process has been measured |
| Rewrite the research stack | Disrupts the current critical path without demonstrated benefit |

### Consequences

Expected benefits are fewer repeated explanations, earlier integration
failures, and more verifiable acceptance. Costs include maintaining
executable contracts and occasionally pausing overlapping work for
reconciliation. These are expected outcomes, not measured savings.

### Adoption criteria

The ADR is operational only after:

- Canonical rules and contradictory entry points are updated together.
- The governance revision is remotely reachable.
- Each agent acknowledges the actual revision.
- One research checkpoint completes the publication and
  independent-acceptance protocol.
- Remaining contradictions are resolved explicitly.

### Revisit triggers

Revisit the shared-branch arrangement if repeated conflicts, stale-head
reviews, integration breakages, or reviewer starvation occur. Prefer isolated
repair branches and controlled integration if the lightweight shared-branch
protocol proves unreliable.
