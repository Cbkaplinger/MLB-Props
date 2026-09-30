# Operations Contracts Checkpoint A -- 2026-09-30

Scope: three risks only (deployment truth, settlement semantics, dashboard lineage).
No production change, no experiments, no model-thread interference.
Master queue: `docs/EXECUTION_BACKLOG.md`. This report is point-in-time evidence.

## 0. Repository-state snapshot

- Before: tree dirty with concurrent work (see `git status --short`); `docs/diagrams/00,02,04,05` carry this window's verification edits; `01`/`03` carry other-session edits.
- This checkpoint adds exactly one file: `docs/reference/reports/ops_contracts_2026-09-30.md` (this report).
- No tracked file modified; nothing staged, committed, or pushed.

## 1. Deployment verification matrix

Source definitions verified in `production/cloud/modal_app.py` (5 functions, NY-local crons, volume `/state`, secrets by name only). Remote facts UNVERIFIED from this window (no Modal auth here; no local heartbeat file -- it lives on the Modal volume, not in this checkout).

| Workflow | Source definition | Remote evidence | Active status | Schedule (source) | Confidence |
|---|---|---|---|---|---|
| Morning board | `morning_workflow` modal_app.py:137 | UNVERIFIED | UNKNOWN (header says scaffold-not-deployed; comments claim 2026-09-16 cloud cutover) | 08:00 NY | source HIGH / live UNKNOWN |
| Hourly refresh | `hourly_refresh` modal_app.py:163 | UNVERIFIED | UNKNOWN | 09-22 NY | source HIGH / live UNKNOWN |
| Close sweep | `close_sweep` modal_app.py:202 | UNVERIFIED | UNKNOWN | q5m 12-22 NY | source HIGH / live UNKNOWN |
| Settle | `end_of_day_settle` modal_app.py:236 | UNVERIFIED | UNKNOWN | 03:00 NY | source HIGH / live UNKNOWN |
| Drift | `nightly_drift` modal_app.py:251 | UNVERIFIED | UNKNOWN | 05:30 NY | source HIGH / live UNKNOWN |
| Laptop schedulers | Task Scheduler mirror, claimed disabled | UNVERIFIED | UNKNOWN | n/a | LOW (comment-only) |

Heartbeat rule (accepted qualification): a heartbeat proves a job ran with a reported
version. It does NOT prove absence of other schedulers. Absence-of-duplicates requires
scheduler inventory on both sides (Modal schedules + laptop Task Scheduler state).

Owner-provided evidence needed: `modal app list` output; deployment history export
(app, functions, schedules, TZ, latest timestamp, build/image identity);
`cloud_heartbeat.jsonl` tail from the volume; laptop Task Scheduler enabled/disabled
state; live `IMAGE_VERSION`.

## 2. Settlement findings and contract

Verified in `src/Python/odds_ledger.py` (`apply_settle`, lines 892-943): match by
`ticket_id`; unconditionally overwrites `settle_value`, `result`, `pnl`, `status`.
No settled guard, no source-fact fingerprint, no revision counter, no prior-value
preservation. Unknown `ticket_id` is a safe no-op. Identity keys exist:
`open_dedupe_key` (date|player|book|line), `signal_key` (date|player|line|side),
`family_key` (date|player|side).

Per-case answers:

1. Same facts, repeated request: rewrites identical values (effectively harmless, not a true no-op).
2. Partial failure + retry: recoverable, no duplicate rows (in-place by `ticket_id`).
3. Concurrent settlement: last-writer-wins, no conflict detection. Safe today only because a single schedule writes.
4. Official-stat correction: silently overwrites; prior outcome/PnL lost.
5. Late void/scratch correction: same silent overwrite; no reason recorded.
6. Newly available result: indistinguishable from a retry.
7. Explicit manual override: same code path as retry; not separately auditable.

No demonstrated financial corruption is claimed; unconditional assignment is the
mechanism, the missing audit trail is the risk.

### Proposed minimal contract (no new database)

- Stable ticket identity: existing `ticket_id` (assigned at open logging).
- Source-fact fingerprint: `(settle_value, settle_source)` where source is one of `mlb_api_final`, `void_scratch`, `manual`, `correction`.
- Same ticket + same fingerprint: return ledger unchanged (true no-op, no rewrite).
- Changed authoritative facts: bump nullable `settle_revision`, stash previous value/PnL, require `settle_reason` + provenance + logical effective time + processing time + operator/workflow identity.
- Concurrency: single-writer assumption documented until a lock or compare-and-swap exists; concurrent execution is a detected conflict, not a silent merge.
- Audit history recoverable from the revision columns (or a corrections JSONL sidecar if columns prove disruptive).

### Characterization-test matrix (for future authorization)

- Repeat same facts twice: second call returns frame unchanged (byte-identical parquet).
- Unknown ticket: frame unchanged.
- Corrected value: revision bumps, previous preserved, reason required (missing reason fails loudly).
- Void after settle: status flips with reason, prior retained.
- Concurrent double-apply: second writer does not silently win (detect or serialize).

### Implementation card OPS-1 (recommended next)

Problem: silent settlement overwrite. Evidence: odds_ledger.py:892-943. Likely
locations: `apply_settle` + `grade_odds_ledger.py` settle wiring. Protected: ledger
schema consumers (grading, notebooks, dashboard), `dedupe_ledger_props`. Tests first:
matrix above. Minimal change: fingerprint no-op + revision/reason columns. Rollback:
revert commit; ledger remains readable (nullable new columns). Owner decision: void
reason taxonomy + single-writer affirmation. Scope: small (one function + wiring).

## 3. Dashboard lineage findings and contract

Sources verified in `production/app/dashboard_streamlit.py`, `production/notebooks/README.md`,
`src/Python/odds_ledger.py` (`dedupe_ledger_props`), `src/Python/market.py` (CLV).
No historical values recomputed.

| Panel | Source | Row meaning | Identity key | Dedupe | Filters | Formula | Units | Lane |
|---|---|---|---|---|---|---|---|---|
| Overview Daily ROI | ledger settled + operator summary (dashboard recompute overrides file) | settled ticket (display) | gdate/player/book/line/side (`_dedupe_frame`, exact dupes only) | exact-dupe removal | settled, stake>0, BET if column exists | pnl/stake per day | inferred median unit ($50 default) | actionable, paper |
| Past History cumulative | ledger settled | settled ticket (display) | same `_dedupe_frame` | same | same | cumulative pnl; edge-weighted expected (oracle) | same inferred unit | mixed actionable + oracle |
| Risk / bankroll | ledger settled | settled ticket | same | same | tail-7 rows | cum pnl/peak/drawdown | same | actionable, paper |
| CLV analysis | ledger `clv_pp` (+ xbook/paid cols unused by display) | measured ticket | none (mean over non-null) | none | clv non-null | mean pp; beat rate | pp | measurement, headline-book only |
| Recommended today | `recommendations.parquet` | board signal | none | none | recommendation==BET | sort by edge | dollars | actionable, pre-ticket |
| Calibration | snapshots + scorecard + `graded.parquet` | mixed snapshot/model/residual | n/a | n/a | varies, some unfiltered | MAE/deltas/lines | mixed | mixed oracle + actionable |
| Policy sweep/scoreboard | sweep/scenario/governance artifacts | counterfactual row | UNVERIFIED (no dedupe call in traced lines) | UNVERIFIED | edge>=floor ex post | pnl/stake; best-row by roi | dollars | oracle threshold vs actionable policy, untagged |

Answers: a display row is not always a ticket (exact-dupe removal keeps multi-book rows
that canonical grading collapses); voids/pushes and stake-denominator handling differ
across implementations; stakes are recorded facts but unit conversion re-infers the
median over history (silently rescales past panels when sizing changes); paper vs
realized is unseparated (real-bet backfill unrun); oracle vs actionable lanes mix on
cumulative, edge-bin, side, and sweep panels; model/champion version appears on no
money panel; freshness math mixes UTC stamps with local conversion and date-string
grouping.

### Canonical metric contract

- Money panels (ROI/PnL/WR/drawdown) use `dedupe_ledger_props` (one row per prop,
earliest logged) unless the panel explicitly claims book-level analysis and says so.
- Every money panel labels: population, denominator, units (contemporary unit, never
re-inferred history), lane (paper-actionable / oracle-counterfactual / measurement),
model+calibrator+policy identity, freshness timestamp + timezone.
- Voids/pushes excluded from ROI denominators and counted separately.
- Parity tests: dashboard money panels vs canonical-dedupe recomputation agree
row-for-row; any intentional deviation carries a lane tag and a test pinning it.

### NON-AUTHORITATIVE FOR FINANCIAL CLAIMS (until parity tests pass)

Overview Daily ROI override, Past History cumulative + expected line, edge-bin and
side realized-vs-expected, sweep best-row, CLV panels with mixed book lanes.
Panels not altered in this phase.

### Implementation card OPS-2

Problem: display/canonical dedupe divergence. Evidence: dashboard `_dedupe_frame`
vs `dedupe_ledger_props:1063`. Locations: `dashboard_streamlit.py` money panels +
parity test file. Protected: dashboard file (parked; display-only changes),
canonical ledger function (untouched). Tests first: row-for-row parity + lane tags.
Minimal change: route money panels through canonical dedupe; tag intentional
deviations. Rollback: revert display commit. Owner decision: per-panel dedupe rules
(one-row-per-prop is not assumed universal). Scope: medium (display + tests only).

## 4. Characterization tests + ranked cards

Cards: OPS-1 settlement contract (recommended; verified accounting risk, small scope),
OPS-2 dashboard parity (display-only, medium scope). Notification design explicitly
deferred to a later checkpoint not covered here. Pruners stay distinct and manual
(see prior census). MLflow remains an optional tracking decision after contracts land;
manifests stay authoritative.

## 5. Owner questions (recommended defaults)

1. Void/correction reason taxonomy: accept `mlb_api_final / void_scratch / manual / correction`? Default YES.
2. Single-writer affirmation for settlement until locking exists? Default YES.
3. Per-panel dedupe rules: money panels canonical, book-level only where labeled? Default YES.
4. Proceed to implementation card OPS-1 after contract review? Default YES.
5. Defer notification design + MLflow + research migration until OPS-1/OPS-2 land? Default YES.

## 6. Before/after repository-state changes

Before: dirty tree with concurrent work (snapshot in section 0). After: +1 new file (this
report). No tracked file touched, nothing staged or committed. Unrelated concurrent
changes reported, not reverted.
