# 09 - Evidence gate (PROPOSED, 2026-10-21)

> Single run, write-once output; the receipt records consumed inputs, executed
> code SHA and output hashes before acceptance (ADR-0001).

```mermaid
flowchart LR
  P["Pre-registration card"] --> I["Implementation + synthetic tests"]
  I --> RV["Reviewer PASS at exact head"]
  RV --> AU["Owner authorization"]
  AU --> RUN["Single run, write-once output"]
  RUN --> REC["Receipt: consumed inputs, code SHA, hashes"]
  REC --> RV2["Reviewer verifies"]
  RV2 --> CL["Closeout"]
```
