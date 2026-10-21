# 11 - Experiment evaluation flow (PROPOSED, 2026-10-21)

> Answers: what happens between frozen inputs and a decision for one
> experiment (Question A shape; the same skeleton applies to any
> pre-registered question under ADR-0001/0002).

```mermaid
flowchart LR
  FI["Frozen inputs (registered pa_table, preds blocks, BF PMF; sha256-pinned)"] --> PA["Paired arms: baseline (frozen recipe) vs challenger (one component changed)"]
  PA --> SC["Scoring: count-RPS per start (paired population, same keys)"]
  SC --> UNC["Uncertainty: paired slate-date bootstrap, null-centered test, Holm family"]
  UNC --> DEC{"Decision (pre-registered stop condition)"}
  DEC -- "improvement distinguishable from zero" --> PROM["Promotion path (ADR-0001 boundary)"]
  DEC -- "no gain" --> KILL["Close the specific recipe; move to next lane"]
```
