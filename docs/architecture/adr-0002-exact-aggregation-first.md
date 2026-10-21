# ADR-0002: Exact aggregation first, workload dependence second

**Status:** PROPOSED (2026-10-21; pending owner approval)

## Decision

Run Question A (exact Poisson-binomial over the registered cycling order)
before Question B (workload dependence). Question A changes one component and
leaves the BF PMF alone. Question B changes the generative structure and needs
its own design.

## Alternatives rejected

- Starting with Question B: changes the generative model first, so any result
  would be confounded with the aggregator change.
- Replacing the aggregator and the workload model together: makes any result
  impossible to attribute to one component.

## Scope statement

Exact aggregation improves mathematical fidelity under its stated assumptions
(each start's count distribution from the registered slot probabilities over
the registered cycling order). Predictive benefit remains UNMEASURED until the
paired count-RPS evaluation runs; fidelity is not a predictive claim.

## Kill criteria

If Question A's count-RPS improvement is not distinguishable from zero, drop
it and move to Question B or to the next lane. **Non-significance supports the
registered stop / no-promotion decision only - it is NOT a conclusion of
equivalence** (the study is not powered to prove the arms identical).

## Question B subjects (design card only; not implemented until R2 reports)

- **C-B1: exposure-index heterogeneity with the supplied BF distribution** -
  the workload exposure index varies across starts; the model must consume the
  supplied BF distribution's heterogeneity rather than a collapsed scalar.
- **C-B2: endogenous exit/workload coupling** - pitcher exit (pull/hook) and
  workload are modeled as coupled, not as an exogenous TBF input.

Each is a design-card subject per the PRD (R3): model structure, delta vs the
frozen baseline, primary metric, paired population, stop condition, and
required synthetic tests - no code and no real outcomes before R2 reports.
