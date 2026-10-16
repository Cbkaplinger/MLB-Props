# Configuration provenance audit — 2026-10-16 (Chat 3, READ-ONLY)

Complete inventory of environment/configuration dependencies at
`origin/main` @ `1927c8c…` (scan: `os.environ`/`os.getenv`/`$env:` across all
tracked `.py` + `.ps1`). **Nothing modified.** Confidence: HIGH.

## Environment variables (19 distinct)

### Secrets / credentials (env-sourced; no hardcoded values found)

| Variable | Used by | Notes |
|---|---|---|
| `SHARPAPI_KEY` | `src/Python/sharp_odds.py` | live odds vendor |
| `SHARPAPI_MIN_INTERVAL_S` | `src/Python/sharp_odds.py` | rate-limit tuning |
| `THEODDSAPI_KEY` | `production/ops/market_research/pull_oddsapi_historical.py` | historical lake pulls |
| `NOVIG_CLIENT_ID` / `NOVIG_CLIENT_SECRET` | `src/Python/novig_client.py` | Novig API |

### Data roots / lake paths

| Variable | Used by | Default behavior |
|---|---|---|
| `MLB_PROPS_DATA_DIR` | BF cohort enumeration/seal prep | repo-relative default per AGENTS.md convention |
| `MLB_PROPS_SAVANT_DATA_DIR` | 3 (p1 harness builders, BF prep) | raw Savant redirect |
| `P1_RAW_SAVANT_DIR` | `p1_harness/scripts/build_pa_table.py` | harness-specific raw dir |
| `BF_P2_PREDS_DIR` | `bf_workload_v1/scripts/run_kcount_comparison.py` | staged-preds override |
| `MLB_PROPS_RESEARCH_LAKE` | 2 (BF enumeration/seal prep) | external lake root |
| `MLB_PROPS_EXIT_ANOMALY_OVERRIDE_PATH` | `src/Python/pipeline/rolling.py` | override table path |

### Ops / alerting

| Variable | Used by |
|---|---|
| `NTFY_URL` / `NTFY_TOPIC` | 5 files (alerting: drift check, automation self-check, morning alert chain) |
| `ALERT_MAX_BETS` | `send_morning_alert.py` |
| `MLB_PROPS_NO_ALERT` | 3 (dry-run/no-alert toggle) |
| `MLBPROPS_TASK_LOG` | `run_task_captured.ps1` |

### Runtime

| Variable | Used by | Notes |
|---|---|---|
| `PYTHONIOENCODING` | 10 `.ps1` files | cp1252-console mitigation — an OS constraint in config (see dependency audit) |
| `PYTHONUNBUFFERED` | close-watcher background launcher | streaming logs |
| `PYTHONPYCACHEPREFIX` | `activate.ps1`, `export-notebook.ps1` | cache redirection |

## Findings

1. **No `.env` file is required or referenced** — configuration is
   process-environment only; secrets never sit in the tree (matches the clean
   secrets audit).
2. **Silent defaults exist for data roots** (repo-relative fallbacks per
   `AGENTS.md`) — documented convention, but a fresh machine without the env
   vars pointed at real data roots will silently produce empty/missing-input
   behavior rather than fail. Worth a startup assertion in the daily chain
   (small slice, owner approval).
3. **Undocumented variables**: `MLBPROPS_TASK_LOG`, `ALERT_MAX_BETS`,
   `MLB_PROPS_NO_ALERT`, `PYTHONPYCACHEPREFIX` appear in no tracked doc — the
   INDEX/runbook completeness slice (ops audit) should include an env-var table.
4. **Credential variables are read-and-fail or read-and-degrade** in their
   single consumers; no fallback-to-public-endpoint silently spending quota was
   observed.

## Smallest safe follow-up

Add an environment-variable reference table to the ops runbook (with the
required-vs-optional and default-behavior columns above) as part of the INDEX
completeness slice — no code change.
