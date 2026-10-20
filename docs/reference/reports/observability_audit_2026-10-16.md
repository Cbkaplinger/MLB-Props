# Production-path observability audit — 2026-10-16 (Chat 3, report-first)

Scope: the active production surfaces — `production/odds/` (6 files),
`production/ops/` (141), `production/projections/` (3), `production/app/` (1),
`production/cloud/` (1), `production/notebooks/` companions. Method: pattern
scan (logging/print, try/except, retry, run_id/manifest, alerting) over all
tracked `.py` in those paths + entry-point/ops-audit caller evidence. Base
`origin/main` @ `1927c8c…`. Confidence: HIGH on pattern counts, MEDIUM on
behavioral claims (no execution). **Report-only.**

## Pattern census (the numbers that matter)

| Family | Files | print | logging | try/except | retry | run_id/manifest | alerting |
|---|---|---|---|---|---|---|---|
| `production/ops` | 141 | 138 | **1** | 44 | 4 | 3 | 10 |
| `production/odds` | 6 | 6 | 0 | 3 | 1 | 0 | 0 |
| `production/projections` | 3 | 3 | 0 | 1 | 0 | 0 | 0 |
| `production/app` | 1 | 0 | 0 | 1 | 0 | 0 | 1 |
| `production/cloud` | 1 | 0 | 0 | 1 | 0 | 0 | 1 |

Conventions observed: print-based operator logs (138/152 files), no structured
logging framework, run manifests on only 3 files, retry logic on 4 (with a
dedicated `tests/test_alert_retry.py`), ntfy alerting on 10. Research runners
are excluded — they already follow the manifest/receipt convention.

## Silent-failure modes (ranked)

| # | Mode | Evidence | Exposure |
|---|---|---|---|
| 1 | **Print-only failure surfacing**: ~94 ops files print errors without exception handling or non-zero exits on every path — failures vanish in cron/exec contexts unless stdout is captured | 138 print vs 44 try/except | High |
| 2 | **No run manifest on daily-chain steps**: only 3 ops files touch run_id/manifest — a failed step leaves no durable identity for later reconciliation (contrast: research lane's manifest convention, which works) | pattern scan | High |
| 3 | **Watcher restart gaps**: background launchers exist (`start_close_watcher_background.ps1`), but watcher health/alerting coverage is 1 file | entry-point audit | Medium |
| 4 | **Operator-flow step failure propagates only via the notebook runner's exit** — Issue #5 showed a missing step fails the run late and loudly | Issue #5 | Medium |
| 5 | **Notification single-channel**: ntfy-only; alert failure = silent (no alert-of-alert-failure) | 10 files, single channel | Low-Med |

## Proposed observability slices (one per path family, small and reversible)

| Slice | Family | Content | Validation |
|---|---|---|---|
| O-1 | daily chain (`ops/run_*.ps1` + entry scripts) | step-level manifest: JSON per run (step, start/end, exit code, artifact paths) into the existing task-log convention (`MLBPROPS_TASK_LOG`); non-zero exit contract per step | one dry-chain run + manifest diff |
| O-2 | watchers (`close_watcher`, background launchers) | heartbeat line + last-success timestamp file; ntfy alert on stall threshold | stall-test in a safe window |
| O-3 | grading/settlement (`grade_odds_ledger`) | exit-code contract + row-count summary line (graded n, skipped n, anomalies n) | settle smoke run comparison |
| O-4 | alerting | alert-delivery failure retry already tested (`test_alert_retry.py`); add a failure-log line when ntfy itself errors | unit test |

Owner gates: O-1/O-2/O-3 touch production scripts (protected) — each needs its
own approved PR; none change behavior beyond added logging/manifests.

## Explicit non-actions

No logging-framework migration (print convention is operator-normal here); no
research-runner changes; no schedule changes; no notification channel additions
without owner order.

## Spec compliance

- **Base SHA (exact):** `1927c8c8c8a4ae72af5be848dea865ce59bd5866` (origin/main).
  **Head at authoring:** branch tip `543fb50036220934948b4fd81ddfe88d4b927d7f`;
  committed as its own increment on top.
- **Inspected paths:** `production/odds/**` (6), `production/ops/**` (141),
  `production/projections/**` (3), `production/app/**` (1), `production/cloud/**`
  (1), `production/notebooks/` companions; caller evidence from
  `entrypoint_inventory_2026-10-16.csv` (committed) + `entrypoint_ops_audit_2026-10-16.md`.
- **Owner:** repo owner (Cbkaplinger) — O-1/O-2/O-3 touch protected production
  scripts; each slice needs its own approved PR.
- **Validation command (re-run the pattern census):**
  `git grep -l "print(" -- production/ops "*.py" | Measure-Object -Line` (expect
  138 files) and `git grep -l "import logging" -- production "*.py"` (expect 1).
- **Confidence:** HIGH on pattern counts; MEDIUM on behavioral claims (no
  execution performed).
- **Risk:** High exposure if O-1/O-2 are not done — cron-context failures stay
  invisible; the slices themselves are Low risk (additive logging/manifests,
  revert = single revert per PR).
- **Smallest follow-up PR:** O-3 (exit-code contract + summary line in
  `grade_odds_ledger.py`) — smallest surface, existing test file to extend.
