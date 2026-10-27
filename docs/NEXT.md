# NEXT — single source of the current action

Owner: architect. Work-state text last updated 2026-10-22 (evening); confirmation-policy amendment 2026-10-27. ROLES_REV 2026-10-27-r1. Read `docs/roles/README.md` first.

## Confirmation-policy amendment (2026-10-27)

`docs/roles/README.md` now distinguishes repository delegation from mandatory connector confirmation. The orchestrator requests owner confirmation with the exact resolved target and full arguments before each side-effecting connector write. Approval covers that write only, not a later merge, experiment, or protected-data access. Local agent permissions are not otherwise changed. This docs-only amendment does not refresh the historical work-state sections below or assign new scientific work; reconcile current assignments through `docs/EXECUTION_BACKLOG.md` and exact-SHA review receipts.

## Standing delegation

The owner delegates routine project decisions and execution authority to the architect within agreed scope. When relevant tests and required checks pass, proceed without requesting repeated authorization, except where a mandatory tool confirmation or approval gate applies (see `docs/roles/README.md`). Escalate only material scope changes, unresolved correctness risks, spending, production changes, or irreversible actions with unclear consequences. Existing repository protections still apply.

**Language:** all chat reports and review comments must be in English.

## M0 v2 — ACCEPTED (development-only)

- v1 STOPPED at `71b236f` (class 4 structurally absent); preserved run stays UNACCEPTED.
- v2 executed once at `2e2482b` (fix head `ae3cd19`; attempt 1 defect record preserved). Chat 2 independently verified receipts, pins (4,823 / 82,817 / `c6568151`), block isolation and endpoint math: PASS.
- EP1 and EP2 pass. Effects are small: K log-loss delta about -7e-06; multiclass 1.2241 vs log5 1.2263 vs league 1.2377; count-RPS delta -0.000169. Accepted as a valid diagnostic, not as evidence of practical betting value.
- No promotion, production, or betting use without the separate gate.

## Critical path

1. Chat 1: build C-B1 (exposure profile) through the synthetic-first evaluation runner, paired count-RPS, slate-date bootstrap and receipts. No real-data run until its registered gate is met.
2. Chat 2: one check of the C-B1 runner when Chat 1 declares it ready; concrete defects only.
3. Architect: decide the next registered step from the M0 result (finer taxonomy, e.g. HR/HBP split, only if C-B1 needs it).

## Chat 3 cleanup lane

One focused stream: remove verified dead or duplicate files, move misplaced files, collapse stale docs, retire obsolete diagrams, prune branches proven merged or redundant. Correct the reported size math with a reproducible tracked-file measurement. No status documents, no research coordination.

## Parked

Decision-flip result unaccepted pending a receipted rerun. Coverage policy for cold-start starts is a product decision (default league-rate prior, flagged). Promotion is separate from M0.
