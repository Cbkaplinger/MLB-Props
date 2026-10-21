# ADR-0001: Evidence gates before any promotion

**Status:** PROPOSED (2026-10-21; pending owner approval)

## Context

Several lanes have produced PA-level or aggregation improvements that did not
survive evaluation. Provenance defects have recurred (in-place receipt repair
with original bytes lost; a merge before the corrected head was reviewed).

## Decision

1. Each research question gets a pre-registered card: one contrast, one primary
   metric, a paired population, and a stated stop condition.
2. A result is valid only if the receipt records the consumed inputs, the
   executed code SHA and the output hashes, and those are written before
   acceptance.
3. Research code never feeds production automatically. Promotion needs a
   separate gate: calibration, policy replay, and an owner decision.
4. A negative result closes the specific recipe, not the idea.
5. Frozen registrations, pins and hashes outrank living documents - and this
   includes THIS ADR, the PRD, and any role rules: they cannot override
   frozen registrations, protocols, pins, or hashes.

## Consequences

Slower per experiment; avoids reruns and disputes. "READY" and "authorized"
remain separate states.
