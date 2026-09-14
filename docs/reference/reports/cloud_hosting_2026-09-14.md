# Cloud hosting + state: cost-benefit (researched 2026-09-14)

> Free-only constraint stands. Sources: Modal pricing/docs (checked Aug 2026),
> GitHub billing docs + July-2026 community findings. All $0 options below.

## Our load (measured, per day)

| Job | Shape | Cost driver |
|---|---|---|
| Morning chain (statcast→board→poll→alert) | ~35 CPU-min, 1×/day | ~17.5 CPU-hr/mo ≈ $0.82 + memory ≈ **~$1–2/mo on Modal** |
| Settle + drift + pack | minutes/day | negligible |
| Close watcher today | 8h idle daemon | does NOT fit serverless — replaced by cron-sweep closes (Phase 2 design: q15–20min sweeps in game windows only) |
| State on disk | ledger MBs; L3 ~40MB; Savant GBs (rebuildable, never ships) | needs ~100MB persistent |

## Host comparison

| | Modal Starter | GitHub Actions | Render/Fly free | Oracle |
|---|---|---|---|---|
| Price | $0 + $30/mo credits (no card; workloads stop, never bill) | 2,000 min/mo free — BUT **scheduled cron is disabled on private repos with a free account** (known limitation) | $0 with sleep | ruled out 9/08 (capacity + halving) |
| Cron | 5 crons native (we need ~4) | needs Pro $4/mo, public repo, or external cron → dispatch hack | sleeps kill reliability | — |
| Our fit | morning + settle + drift + sweeps ≈ $2–5/mo, inside $30 | ~1,100 min/mo fits IF cron worked | no | no |
| SharpAPI/ntfy | env secrets, plain HTTPS — works anywhere | same via repo secrets | same | — |
| Gotchas | 1-day logs; cold starts (fine for batch); needs 10-min OAuth signup | private+free = no cron; 500MB artifact cap; stateless (see below) | cold sleep misses windows | — |

**Recommendation: Modal.** Only option that is $0, cron-native, and solves state. Actions is the fallback (needs Pro $4/mo or repo-public decision + state surgery).

## State comparison

| | Modal Volumes | Free Postgres (Neon) | Actions cache/artifacts | DuckDB committed to repo |
|---|---|---|---|---|
| Price | $0.09/GiB-mo, **first 1 TiB free** = $0 for us | free tier ~0.5GB, sleeps when idle | 500MB shared / 10GB cache, hourly accrual | $0 |
| Migration | zero (parquet as-is) | small (ledger writes → SQL) | hacky (cache restore/save each run; 500MB cap) | zero, but repo bloat + merge pain |
| Verdict | **winner on Modal** | runner-up (relational only pays if we need queries) | fallback-only | avoid |

## Cutover plan (post-9/27, owner gates each step)

1. Owner: 10-min Modal signup (OAuth, no card) → token.
2. Agent: image (python + deps) + 4 crons (morning, settle, drift, close-sweeps) + volumes mount + secrets (SHARPAPI_KEY, THEODDSAPI_KEY, NTFY_TOPIC).
3. Parallel-run ≥7 days: cloud boards vs laptop, diff-checked, laptop still primary.
4. Cutover: laptop retires to backup; cloud primary. Kill-switch stays ntfy + postseason HOLD (config, travels free).
5. Watcher daemon retires → cron-sweep closes (already designed, same cutover).

## Credit/quota safety

Odds API ($119 sunk, 3.7M left) and SharpAPI (paid/held) are quota-capped client-side already (max-credits, quota-floor); cloud changes nothing except removing the box-off failure class. No new spend anywhere in this plan.
