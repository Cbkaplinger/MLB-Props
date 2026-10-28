# ROLES — orchestration (builder / reviewer / cleaner)

**Status:** PROPOSED (2026-10-21; pending owner approval)
Superseded for current role policy by `docs/roles/` (ROLES_REV 2026-10-28-r1);
where this file conflicts with `docs/roles/` or `docs/NEXT.md`, those win.
Preserved as a proposal record; this file adds the per-role behavioral
contract for the current research cycle.

## Builder (Chat 1)

- Commits and pushes only its own fixes; never self-approves.
- Never runs real data without explicit owner authorization.
- States the exact head on every handoff.

## Reviewer (Chat 2)

- Reviews published heads only.
- Separates correctness from readiness from authorization.
- Does not repeat cleared reviews.

## Cleaner (Chat 3)

- Stays out of research paths and files under review.
- Reports counts derived from the read registry.
