# Agent instructions (this repo)

**Master file for what to do next:** [`docs/EXECUTION_BACKLOG.md`](docs/EXECUTION_BACKLOG.md)

That backlog is the single holy work-state file (APPROVED / BLOCKED / waiting / parked / deferred, plus PAST / PRESENT / FORWARD / DEFERRED). Open it first; update the Session Snapshot every turn that changes work state. Do not create parallel backlogs.

| Role | Path |
| --- | --- |
| Work queue & approvals | `docs/EXECUTION_BACKLOG.md` |
| Technical research constraints | `docs/reference/research_assistant_instructions.md` (not a todo list) |
| Daily ops commands | `production/README.md`, `production/INDEX.md`, `production/RUNBOOK.md` |
| Dated evidence reports | `docs/reference/reports/` (point-in-time; not the live plan) |
| Paper / portfolio summary | `docs/paper/manuscript.md`, `docs/paper/resume-summary.md` |

Also always-on: prefer Polars (`.cursor/rules/use-polars.mdc`); never `git push` (`.cursor/rules/git-push-policy.mdc`).
