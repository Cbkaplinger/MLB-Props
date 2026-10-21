# 07 - Lanes and responsibilities (PROPOSED, 2026-10-21; revised)

> Answers: who builds, who reviews, who AUTHORIZES EXECUTION, and who
> APPROVES PROMOTION. Reuses the evidence-gate diagram (09) for the
> receipt chain. Owner decisions and builder actions are separated.

```mermaid
flowchart LR
  OWNER["OWNER: authorizes real-data execution; approves promotion; holds abstain-vs-handle"]
  ARCH["ARCHITECT/ORCHESTRATOR: ADRs, PRD, gate design (proposals only)"]
  B["CHAT 1 BUILDER: implements on research branches; commits/pushes own fixes; never self-approves; states exact head on handoff"]
  R["CHAT 2 REVIEWER: exact-head verdicts; separates correctness / readiness / authorization; never repeats cleared reviews"]
  C["CHAT 3 CLEANER: stable older repo only; registry-derived counts; never touches research, backlog, open-review files"]
  OWNER -->|"authorizes execution (pre-registered single run)"| B
  OWNER -->|"approves promotion (calibration + policy replay + paper trade)"| PROD["Production (frozen stack)"]
  ARCH -->|"proposals, drafts"| OWNER
  ARCH --> B
  ARCH --> R
  ARCH --> C
  B -- "publishes exact head" --> R
  R -- "correctness PASS / fixes required" --> B
  R -- "readiness separate from authorization" --> OWNER
  C -. "never touches research, backlog, open-review files" .-> B
```
