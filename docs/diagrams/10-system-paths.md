# 10 - System paths (PROPOSED, 2026-10-21)

> Answers: production path vs research path, inputs, model components,
> outputs, and the promotion boundary. Reuses diagrams 01 (production
> detail), 05 (live flow) and 08 (research decision flow) for depth -
> this is the boundary map, not a competing source of truth.

```mermaid
flowchart TB
  subgraph PROD["PRODUCTION PATH (frozen; live)"]
    IN1["Inputs: Statcast parquet (2022+ prior context, 2023-2025 pipeline seasons)"] --> L1["L1/L2/L3 pipeline: games, rolling, training frames"]
    L1 --> FEAT["features.py + registries.py (frozen feature set)"]
    FEAT --> KRATE["K-rate ensemble (frozen artifacts, manual-winner blend)"]
    L2B["bullpen + workload context"] --> TBF["TBF ridge"]
    KRATE --> COUNT["count_layer.py: Poisson + WS1c Platt -> expected_K, P(K>=line)"]
    TBF --> TBFOUT["projected TBF"] --> COUNT
    COUNT --> POL["policy filter: floors, cap, under-lean, DK+FD, clip"] --> SIZE["flat sizing"] --> OUT["board -> odds ledger -> grading"]
  end
  subgraph RESEARCH["RESEARCH PATH (gated; never feeds production automatically)"]
    RIN["Inputs: same frozen artifacts + registered experiment inputs"] --> RQ["Research questions (A: exact aggregation; B: workload dependence)"]
    RQ --> REVAL["Paired evaluation: count-RPS primary, paired bootstrap"]
    REVAL --> RDEC["Decision: adopt / reject (ADR-0002 kill criteria)"]
  end
  OUT --> EVID["Evidence: receipts, CLV, policy replay"]
  RDEC -- "PROMOTION BOUNDARY (ADR-0001): calibration -> policy replay -> paper trade -> owner gate" --> PROD
```
