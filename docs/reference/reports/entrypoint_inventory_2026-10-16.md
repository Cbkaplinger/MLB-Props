# Entry-point inventory — 2026-10-16 (Chat 3, report-first)

Per-entry-point companion to [`entrypoint_ops_audit_2026-10-16.md`](entrypoint_ops_audit_2026-10-16.md).
All **294 `__main__` files** at `origin/main` @ `1927c8c…`, machine-generated:
`entrypoint_inventory_2026-10-16.csv` alongside this file. Columns: path, family,
kind (scheduled/ops/research-runner/model/tooling), static-reachability,
last-touch, external APIs, file-write behavior, doc-reference count, caller
evidence, owner. Confidence: HIGH on static facts.

## Distribution

| Family / kind | Count |
|---|---|
| production/ops | 136 |
| production/scheduled (cron/scheduler mentions) | 13 |
| models (trainers + research-era tuners) | 68 |
| research runners | 38 (+5 scheduled-flagged) |
| scripts tooling | 19 (+1) |
| src / docs / playground / .agents | 13 (+1 scheduled) |
| **Total** | **294** |

## Findings

1. **62 entry points (21%) have zero documentation references** — no mention in
   any tracked `.md`. Largest blocks are `models/**` research-era tuners and
   `production/ops/build_*` helpers. Disposition: not dead (static reachability
   and caller evidence vary per row — see CSV `called_by_sample`); they need an
   INDEX-completeness pass (ops audit finding 1), not deletion.
2. **22 scheduled-flagged entry points** — the scheduler surface is wider than
   the pipeline registry's 10 schedules; reconciling registry rows to these 22
   is a small owner-reviewed follow-up (registry is design-only by charter).
3. **External API surface is concentrated**: SharpAPI, The Odds API, Kalshi,
   Novig, ntfy, pybaseball/Savant — all env-keyed (see config provenance audit);
   none hardcoded.
4. **Write behavior flagged per row** (`writes_files`) — daily-chain writers
   conform to the write-once/run-dir + append-with-dedupe conventions; no
   ad-hoc overwrite patterns surfaced in this pass.
5. **Last-touch spread**: research runners cluster at their freeze dates
   (expected); several production helpers last touched 2026-08/09 — no
   staleness action implied without behavioral evidence.

## Smallest safe follow-up

INDEX-completeness slice for the 62 undocumented entry points (grouped
one-liners, owner sign-off on which are intentionally internal).
