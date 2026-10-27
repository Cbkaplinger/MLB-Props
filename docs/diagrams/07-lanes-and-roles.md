# 07 - Lanes and responsibilities (PROPOSED, 2026-10-21; revised)

> Answers: who builds, who reviews, who AUTHORIZES EXECUTION, and who
> APPROVES PROMOTION. Reuses the evidence-lifecycle states in diagram 13
> (diagram 09 was retired there; PR #40). Owner decisions and builder
> actions are separated.
> Role definitions are canonical at `docs/roles/` (ROLES_REV 2026-10-22-r2);
> where this diagram conflicts with them or `docs/NEXT.md`, those win.

```mermaid
flowchart LR
  OWNER["OWNER: authorizes real-data execution; approves promotion; holds abstain-vs-handle"]
  ARCH["ARCHITECT/ORCHESTRATOR: ADRs, PRD, gate design (proposals only)"]
  B["CHAT 1 BUILDER: implements on research branches; commits/pushes own fixes; never self-approves; states exact head on handoff"]
  R["CHAT 2 REVIEWER: exact-head verdicts; separates correctness / readiness / authorization; never repeats cleared reviews"]
  C["CHAT 3 CLEANER: docs-only cleanup; never touches research, frozen cards, results, artifacts, or the canonical backlog (proposes backlog corrections to Chat 1)"]
  OWNER -->|"authorizes execution (pre-registered single run)"| B
  OWNER -->|"approves promotion (calibration + policy replay + paper trade)"| PROD["Production (frozen stack)"]
  ARCH -->|"proposals, drafts"| OWNER
  ARCH --> B
  ARCH --> R
  ARCH --> C
  B -- "publishes exact head" --> R
  R -- "correctness PASS / fixes required" --> B
  R -- "readiness separate from authorization" --> OWNER
  C -. "docs-only; no canonical-backlog edits" .-> B
```
