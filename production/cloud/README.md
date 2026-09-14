# Cloud cutover (Modal) — staged, not deployed

## Architecture (how it all fits)

```mermaid
flowchart LR
    subgraph LAPTOP["Laptop (research + backup)"]
        LAKE[(Odds-Historical lake\nSavant raw\nresearch scripts)]
    end
    subgraph MODAL["Modal Starter ($0)"]
        IMG[Image: code + deps\n(versioned, rebuilt on deploy)]
        VOL[(Volume: hot state ~350MB\nL3/rolling, ledger, recs,\nscores, models, policies)]
        CRON1[08:30 morning chain]
        CRON2[03:00 settle]
        CRON3[05:30 drift]
        CRON4[q15min close sweeps\nin game windows\n(script unbuilt)]
        SEC[(Secrets:\nSHARPAPI/OddsAPI/NTFY)]
    end
    subgraph VENDORS["Vendors (network)"]
        SH[SharpAPI live quotes]
        OA[OddsAPI history]
        SV[Savant nightly delta]
        MLB[MLB Stats API settle]
    end
    YOU([You: Novig fills\nntfy alerts])
    CRON1 & CRON2 & CRON3 & CRON4 --> IMG --> VOL
    IMG <--> VENDORS
    IMG -->|ntfy| YOU
    YOU -->|fills| VOL
    LAKE -. research only, never in cron .- IMG
```

Key locality rule: containers are EPHEMERAL (fresh code each run), the
Volume is PERSISTENT (all state). Nothing is stored in the image; nothing
executes from the volume. Laptop keeps the research lake and becomes backup.

## Why Modal + parquet (not SQL)

- Daily chain reads 18k-row frames (seconds per scan) and appends single-writer
  parquet. No concurrent writers, no relational queries in the prod path.
  SQL buys nothing; Neon-style free Postgres adds idle-sleep flakiness plus a
  ledger-write migration. Revisit only on multi-reader contention.
- Hot state ≈ 350 MB (L3/rolling 248 + live_scores 75 + odds_log 15 + models 8
  + projection_log 2 + policies). Volumes give 1 TB free: upload once.

## Credit burn (exact math — cloud changes nothing)

| Meter | Laptop today | Modal | Verdict |
|---|---|---|---|
| Modal compute | $0 | morning ~35 CPU-min/day ≈ $0.055/day + memory ≈ $0.019/day; settle/drift/sweeps ≈ +$1/mo → **~$3–5/mo of $30 free** | 6–10× headroom |
| SharpAPI | per-key rate limits (Free 12/min; client self-throttles 6s) + plan quota; ~4 polls/day | identical call pattern, same key | no change |
| OddsAPI | 3.7M left, client-capped (max-credits, quota-floor) | same closeout cadence, same caps | no change |
| ntfy | a few alerts/day | same | no change |

The cloud cannot burn credits the laptop wouldn't: every vendor call is
client-capped in code, and Modal meters only our compute (pennies).

## Watcher, redesigned (no daemon)

Today's watcher is an 8-hour idle daemon — on serverless that means paying
for allocated-but-idle time, so it does NOT port. Replacement (already the
Phase-2 design): **cron-sweep closes** — q15–20min sweeps inside game
windows only, each run fetching latest quotes, writing close rows, exiting.
Close = latest pre-first-pitch quote per ticket (Statcast first-pitch anchor,
never cron alignment). Same data, ~1/10th the compute, zero idle billing.
The daemon + lock retire at cutover.

## Language: Python, nothing else

Zero rewrites: the crons shell to the exact `.py` scripts the laptop runs
(the `.ps1` wrappers stay laptop-only; Modal calls the Python underneath).
New code is Python (Modal SDK is Python-native). No second language, no
port, no translation risk — parallel-run diffs verify byte-behavior, not
rewrites.

## Credit guards (four layers — nothing can run away)

1. **No payment method on file.** Modal Starter requires none; without one,
   workloads STOP at $30 instead of billing. This is the hard ceiling —
   overspend is structurally impossible, not just unlikely.
2. **Client-side caps in code** (work on laptop AND cloud identically):
   OddsAPI pulls carry `--max-credits` + a 100k quota floor; closeout caps
   5,000/day and refuses today/future/past-9/28; SharpAPI self-throttles
   (1 req/6s) under its per-key rate limits; ntfy is a few alerts/day.
3. **Cron-shaped load.**Batch jobs that release containers cost ~$3–5/mo.
   Nothing idles, nothing warms, no `min_containers`. The one anti-pattern
   (keep-warm) is absent by inspection — `grep keep_warm production/cloud/`
   must return nothing, and CI could pin that.
4. **Dashboard check.** Modal metrics show spend per app; a 2-minute look
   weekly in September is the whole monitoring program. Starter logs keep
   1 day — the ledger, not Modal logs, is the durable record.

## Teardown (regular season ends 2026-09-27 — no postseason predictions)

The live product already stops itself: postseason HOLD fires 9/27
(`season.regular_end`, board-level, tested). Cloud teardown after the
October judge program finishes (judge needs compute; predictions don't run):

1. `modal app delete mlb-props` (crons stop same minute).
2. Optional: `modal volume get mlb-props-state` snapshot of final ledger,
   then `modal volume delete mlb-props-state`.
3. `modal secret delete mlb-props-keys` (keys stay in your password manager).
4. OddsAPI: verify auto-renew is OFF in the dashboard (was calendar-noted at
   the $119 buy — confirm once, key stays free tier).
5. Laptop resumes as the archive + research box (lake never left it).

October compute (full-season judge, stacker verdict) runs ad-hoc, not on
cron — spin up, run, spin down. No standing spend at any point.

## Go-live checklist (owner gates)

1. `pip install modal` → `modal token new` (browser OAuth, no card).
   The token lands in `~/.modal.toml` on YOUR machine — never in the repo,
   never committed. Verify with `modal profile current`.
2. `modal secret create mlb-props-keys SHARPAPI_KEY=... THEODDSAPI_KEY=... NTFY_TOPIC=...`
   (values live in Modal's secret store + your password manager only).
3. `modal volume put mlb-props-state data/ data` + `artifacts/ artifacts`
   (hot state only; Savant raw + Odds-Historical lake stay on the laptop).
4. `modal deploy production/cloud/modal_app.py` (3 crons: morning/settle/drift).
5. ≥7 parallel days: diff cloud vs laptop boards/ledgers; laptop primary.
6. Cutover: laptop to backup. Kill-switch (ntfy + postseason HOLD) travels as config.

## Path notes (verified 2026-09-14)

- `config.py` honors `MLB_PROPS_DATA_DIR` / `MLB_PROPS_OUTPUT_DIR` /
  `MLB_PROPS_SAVANT_DATA_DIR` — the scaffold points all three at the volume,
  which also fixes the `Data` vs `data` case gap on Linux.
- Settle/drift run the underlying `.py` scripts directly (the `.ps1`
  wrappers are Windows-only). Watcher daemon is NOT ported — cron-sweep
  closes replace it at cutover (already the Phase-2 design).
- SharpAPI/ntfy are plain HTTPS + env keys: no code change for cloud.
- Case-sensitivity + any non-config relative paths are verified by the
  parallel-run diff (step 5), not by inspection.
