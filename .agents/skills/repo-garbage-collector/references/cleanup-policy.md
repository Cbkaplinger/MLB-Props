# Cleanup Policy (deletion gates + classification)

## Classify every file

CANONICAL, GENERATED, HISTORICAL DECISION, ACTIVE PLAN, COMPLETED EVIDENCE,
EXPERIMENT, REDUNDANT, STALE/WRONG, ORPHANED/UNKNOWN.

## Markdown: delete outright when migrated AND one or more hold

- Duplicates a canonical doc.
- Completed one-off session report.
- Stale generated numbers (should be artifact/command).
- Obsolete plan superseded by `docs/EXECUTION_BACKLOG.md`.
- Deleted path / retired workflow.
- Agent transcript, temp audit, scratchpad, handoff with no unique durable decision.
- Thin wrapper around another doc.
- Irreproducible with no defensible rationale.

Keep rationale only as compact ADR (one decision, context, decision,
consequences, verification; status accepted/deprecated/superseded).

## Python: never delete on a single signal

Vulture/Ruff/IDE-unused/zero-imports are candidate generators. Required
before delete: repo-wide reference trace (imports, console/Modal/scheduler/
config/notebook/test/dynamic/subprocess/shell/external), execution-path
analysis, test inspection. Scheduler reachability: decorators, deployment
commands, configs, string refs.

High-confidence removes: unused imports, unreachable blocks, obsolete shims,
commented implementations, debug prints, dead flags/branches.

## Protected entry points (verify without deploying)

Modal apps/decorators, cron/scheduler registrations, CLI commands, grading
(`grade_odds_ledger.py` + settle paths), ntfy alert paths
(`send_morning_alert.py`, `send_daily_grading.py`, watchers, failure banners),
postseason HOLD, pins (`test_live_stack_pin.py`), atomic ledger writes.

## Artifacts

Delete reproducible stale outputs with canonical tested generator. Never delete
irreplaceable raw data or model artifacts for size. One declared output
location. Update all refs/tests. Secrets audit every batch; never print secrets.
