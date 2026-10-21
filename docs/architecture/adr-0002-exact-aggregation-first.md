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

## Kill criteria

If Question A's count-RPS improvement is not distinguishable from zero, drop
it and move to Question B or to the next lane.
