# Agent instructions (this repo)

**Master file for what to do next:** [`docs/EXECUTION_BACKLOG.md`](docs/EXECUTION_BACKLOG.md)

That backlog is the single holy work-state file (APPROVED / BLOCKED / waiting / parked / deferred, plus PAST / PRESENT / FORWARD / DEFERRED). Open it first; update the Session Snapshot every turn that changes work state. Do not create parallel backlogs.

| Role | Path |
| --- | --- |
| Work queue & approvals | `docs/EXECUTION_BACKLOG.md` |
| **OpenCode / Cursor paste brief** | [`docs/reference/opencode_handoff.md`](docs/reference/opencode_handoff.md) — coworker briefing 2026-09-11; pack #113 built; juiced #123 measured; Dashboard parked |
| Frozen-model Odds API replay spec | [`docs/reference/oddsapi_replay_architecture.md`](docs/reference/oddsapi_replay_architecture.md) — not a queue; freeze/work/product |
| Technical research constraints | `docs/reference/research_assistant_instructions.md` (not a todo list) |
| Daily ops commands | `production/README.md`, `production/INDEX.md`, `production/RUNBOOK.md` |
| Dated evidence reports | `docs/reference/reports/` (point-in-time; not the live plan) |
| Paper / portfolio summary | `docs/paper/manuscript.md`, `docs/paper/resume-summary.md` |

Also always-on: prefer Polars (`.cursor/rules/use-polars.mdc`); never `git push` (`.cursor/rules/git-push-policy.mdc`).

## Cheap-agent / Mac handoff (2026-09-02)

- Context excludes: `.cursorignore`, `.clineignore` (same rules), `.cursorindexingignore`
- Always-on rule: `.cursor/rules/agent-context.mdc` → backlog + `docs/reference/repo_canonical_map.md`
- Historical CLV API research: `docs/reference/reports/historical_clv_odds_apis_2026-09-02.md`
- Live odds remain SharpAPI (`SHARPAPI_KEY`); do not confuse with historical backfill vendors
