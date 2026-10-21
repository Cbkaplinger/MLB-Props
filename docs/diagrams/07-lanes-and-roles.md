# 07 - Lanes and roles (PROPOSED architecture, 2026-10-21)

> Owner-approved draft pending integration. Status vocabulary matches the
> existing index (EXISTING, RESEARCH-BUILT, PROPOSED, REJECTED, UNRESOLVED).

```mermaid
flowchart LR
  OWNER["Owner: authorizes execution and promotion"]
  ARCH["Architect/Orchestrator: ADR, PRD, gates"]
  B["Chat 1 Builder: research branches"]
  R["Chat 2 Reviewer: exact-head verdicts"]
  C["Chat 3 Cleaner: stable older repo"]
  OWNER --> ARCH
  ARCH --> B
  ARCH --> R
  ARCH --> C
  B -- "publishes head" --> R
  R -- "PASS / fixes required" --> B
  C -. "never touches research, backlog, open-review files" .- B
```
