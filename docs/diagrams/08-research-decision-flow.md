# 08 - Research decision flow (PROPOSED, 2026-10-21)

> Batter-history challenger REJECTED (R60/m30 recipe only, not recency
> modeling in general). Question A built, not evaluated on real outcomes.

```mermaid
flowchart TB
  F["Frozen baseline"]
  X["Batter-history R60/m30: REJECTED"]
  A["Question A: exact Poisson-binomial (built, not evaluated)"]
  Ev["Count-RPS evaluation (needs owner authorization)"]
  B["Question B: workload dependence (design card only)"]
  G["Promotion gates: calibration, policy replay, paper trade"]
  F --> X
  F --> A --> Ev
  Ev -- "improves" --> G
  Ev -- "no gain" --> B
  B -.-> G
```
