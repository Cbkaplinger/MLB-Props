# production/ops — automation, alerting, policy, research ops

## Purpose

Schedulers, workflow scripts, alerting, policy files, and the market-research
lab. Three lanes: **run** (daily automation), **watch** (alerts + health),
**learn** (market_research probes, each script + report JSON).

## Run (scheduler entry points — all best-effort + failure banners)

| Script | When | What |
|---|---|---|
| `run_morning_workflow.ps1` | 08:00 daily | statcast → features → projections → board → poll → alert |
| `run_market_refresh.ps1` | hourly 08:00–22:00 | re-log projections (dynamic lineups) → board → poll → edge-watch → flips-only alert |
| `run_wake_recovery.ps1` | logon after a gap | full chain rebuild (never settles, never fabricates missed slates) |
| `run_end_of_day_settle.ps1` | 03:00 daily | settle + voids + reports (post-game only) |
| `run_nightly_drift.ps1` | 05:30 daily | drift check + self-check, pages on RED only |
| `run_close_sweep.py` | q20min 12:00–22:07 ET | close fills (watcher-daemon replacement, container-safe) |
| `run_catchup.ps1` | manual | settle/grade/self-check/alert after missed days |
| `setup_automation_tasks.ps1` | owner minutes | registers everything incl. logon WakeRecovery |

## Watch

`send_morning_alert.py` (ntfy-only; `--dry-run` never clobbers the live
record), `frozen_edge_watch.py` (pages skip/HOLD→BET flips only),
`build_automation_self_check.py` (task health → RISK pages),
`run_task_captured.ps1` (keep-awake + truthful exit codes).

## Learn (`market_research/`)

Frozen-model replay, gates, audits — see `production/ops/market_research/README.md`.
Every probe: pre-registered kill rule, script + `*_report.json`, no live
change without sign-off + gate.

## Policy files (the live contract)

`kpi_policy.json` (veto/probation/cap/lean/books/season/bankroll),
`line_floor_policy.json`, `live_krate_ensemble.json`. Changes need a named
owner order + same-commit pin update + green suite.

## Rules

- Catch blocks read `$_`, never `$_.Exception.Message` (string throws have
  no `.Exception` — the 2026-09-11 blank-banner root cause).
- ASCII-only scripts (PS 5.1 reads files as ANSI; non-ASCII breaks parsing).
- No-arg entry scripts for scheduler (flags break under `powershell -File`).
