# Archive Consolidation Map

`docs/archive/` keeps superseded or invalid historical evidence so current
operations can stay clean without losing auditability.

## Current archive contents

- `pre-pipeline-v6/`
  - Early pre-pipeline baseline exports and SHAP-era artifacts.
  - Historical only; not valid for current leakage-safe pipeline decisions.
- `leaky-baseline-2026-07-23/`
  - Invalid overlapping-date baseline retained for transparency.
  - Must not be used as final evaluation evidence.

## Usage policy

- Archive files are read-only evidence.
- Do not link archive metrics as current performance claims.
- Active references should point to:
  - `docs/research/` for current experiments,
  - `docs/reference/` for current operations/policy,
  - `production/` docs for execution commands.

## Deletion policy

Archive deletion requires explicit confirmation and should be rare. Prefer:

1. Keep files in place.
2. Tighten links so active docs no longer depend on archive content.
3. Delete only truly redundant duplicates with preserved provenance elsewhere.
