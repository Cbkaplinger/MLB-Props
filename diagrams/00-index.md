# Index — MLB Props research map

Four separate phase diagrams. Open each file for detail; this index only shows
how they relate.

```mermaid
flowchart TB
  classDef built fill:#1b5e20,stroke:#a5d6a7,color:#fff
  classDef partial fill:#e65100,stroke:#ffcc80,color:#fff
  classDef missing fill:#b71c1c,stroke:#ef9a9a,color:#fff
  classDef risk fill:#4a148c,stroke:#ce93d8,color:#fff
  classDef research fill:#0d47a1,stroke:#90caf9,color:#fff
  classDef index fill:#263238,stroke:#90a4ae,color:#fff

  IDX["MLB Props research map"]:::index

  A["01 Architecture<br/>as-built L1→L3→train→artifact"]:::built
  B["02 Leakage & risks<br/>priors · parks · ≥9 PA filter"]:::risk
  C["03 Modeling & evaluation<br/>chrono splits · baselines · Steps 1/3/4/5"]:::research
  D["04 Roadmap<br/>TBF · counts · live assembly"]:::missing

  IDX --> A
  IDX --> B
  IDX --> C
  IDX --> D

  A -.->|"feeds"| C
  B -.->|"constraints"| A
  B -.->|"constraints"| D
  C -.->|"gates freeze"| D
```

**Status snapshot (2026-07):**

- Rate model path is built (248-feature LightGBM gate).
- Live lineup **ingestion** is partial; **prediction assembly** is missing.
- Projected TBF, count-probability layer, and Step 5 PA-weighting are missing.
- Step 7 registry freeze is blocked on Steps 1 / 3 / 4 / 5.
