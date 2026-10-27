# NEXT — current action

Owner: architect. Updated 2026-10-27. ROLES_REV 2026-10-22-r2 remains unchanged. Read docs/roles/README.md first. Frozen registrations, pins and protected-data rules remain authoritative.

## Workflow reset

Use EXECUTION_BACKLOG.md as the only work queue. This page is its short current-action pointer, not another backlog. Existing proposed ADRs/PRDs are not automatically adopted. C-B1 is completed/rejected per the latest handoff; do not rebuild it. Preserve historical evidence and reconcile its source in the backlog.

Cycle: specify one question -> implement -> synthetic tests -> publish exact SHA -> one consolidated independent review -> authorized development run if needed -> reproduce -> retain/reject -> merge -> update current action. Review computational deltas only; do not reopen cleared findings without new evidence. Merge, execution and promotion are distinct decisions.

## Current assignments

Chat 1: own scientific implementation and the canonical backlog. Address one consolidated review of PR #49. Stage A only is active: define prediction-path equivalence, all input artifacts, fixed features, keyed joins, exclusions, and synthetic smoke tests. Distinguish no realized-K scoring from any realized-PA-derived inputs. Stage B remains deferred, not automatically authorized by Stage A PASS. Do not alter the frozen calibration branch or run real-data diagnostics without the applicable authorization.

Chat 2: close PR #48 integration after architect delegation on that PR, current-head PASS and green checks; verify integrated identities once. Review PR #49's published head rather than searching again for publication. Return one actionable blocker list or PASS, and review only changed content thereafter. No automatic calibration execution.

Chat 3: ACTIVE on its existing cleanup branch/PR. Reconcile stale operational instructions, precedence links, supersession labels and diagram pointers. Do not edit scientific code, frozen cards, results, artifacts or the canonical backlog concurrently with Chat 1. Propose backlog corrections to Chat 1. Claim exact paths before editing. Preserve unknown local changes; no deletions or branch pruning without explicit approval. This architect-owned NEXT update is authorized for inclusion in the cleanup PR.

Architect: resolve scope and sequencing, own NEXT and role changes, delegate integration explicitly, and select the next experiment from evidence. Argon is finished and inactive.

## Baseline-to-advanced sequence

1. Close prediction-path correctness with synthetic tests and a separately authorized Stage A if needed.
2. Freeze one runnable baseline: target, features, estimator, workload, scorer, partitions and artifact identities. Inventory LightGBM regression separately from binary/multiclass PA research; do not silently switch lanes.
3. Test one feature family at fixed settings against that baseline; assess both its component endpoint and downstream K distribution.
4. Freeze features; run a bounded, chronologically validated hyperparameter search for the explicitly selected model. Preserve all trials. No confirmation/2026 tuning.
5. Lock the candidate; evaluate under its registered rules. Calibration is optional and separately fitted/evaluated for that candidate. Confirmation, paper operations and production require their own gates.

Calibration execution, Stage B, new model families, market reconstruction, Kelly and live execution remain deferred. Existing M0 development acceptance is not production approval.

## Handoff

Report: ROLES_REV | task | full SHA | tests/checks | durable PR/artifact link | next action | concrete blocker or none. No polling, repeated owner relays, duplicate queues or new governance documents. FAIL is localized repair; a valid negative result closes that hypothesis. No retries to seek a favorable result.
