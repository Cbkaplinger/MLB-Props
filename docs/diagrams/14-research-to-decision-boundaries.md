# 14 - Research-to-decision boundaries (TARGET-STATE, PROPOSED 2026-10-21)

> The repository already has pipeline, contract, lineage, and operational
> components; the recommendation is to clarify and validate their boundaries,
> not assume they need replacement. Dashed edges feed health/recovery evidence.

```mermaid
flowchart LR
    S["Source data<br/>Provider, license, arrival time"]
    I["Ingestion boundary<br/>Identity, deduplication, freshness"]
    C["Canonical observations<br/>Grain, keys, event time"]
    F["Point-in-time features<br/>As-of rules, missingness, support"]
    M["Model probability outputs<br/>Versioned inputs and model"]
    K["Opportunity / count distribution<br/>Aggregation contract"]
    P["Market comparison<br/>Timestamped line and price"]
    D["Decision policy<br/>Eligibility, abstention, risk"]
    L["Decision / settlement ledger<br/>Stable identity and corrections"]
    E["Evaluation packet<br/>Predictive and market evidence"]
    H["Health / recovery evidence<br/>Failures, alerts, replay"]

    S --> I --> C --> F --> M --> K --> P --> D --> L --> E
    I -.-> H
    F -.-> H
    P -.-> H
    L -.-> H
```
