# Interim Live Skip Rules

**Dated:** 2026-09-01  
**Status:** **PROMOTED to live policy** (see `live_policy_promotion_2026-09-01.md`). Paper/`KING` freeze notes updated; quality gate enforces hard veto.  
**Further instructions / what next:** [`docs/EXECUTION_BACKLOG.md`](../../EXECUTION_BACKLOG.md) — this report is the rule card, not the work queue.  
**Evidence:** post-freeze KING ledger + weekly settle pack.

## Hard rule (do this)

| Bet | Action |
| --- | --- |
| **4.5 over** | **Do not bet.** |

Post-freeze: 4.5 overs n=18 ROI ≈ **−41%** WR 33%. Removing them flips status-quo −1.55% → **+8.25%** on the same window. All-time KING floor: 4.5 overs n=48 ROI ≈ **−27%**.

## Soft probation (judgment OK)

| Bet | Action |
| --- | --- |
| 2.5 over | Prefer skip when unsure (tiny n, red). Not a hard system veto yet. |
| 3.5 over | Caution / half-size OK; do **not** auto-veto (bleed milder than 4.5). |
| 5.5 over | Watch list (all-time ugly, post-freeze thin). Discretionary skip fine. |

## Keep betting

- **Unders** at current floor / flat stake (including **4.5 unders** — those are not the drag).
- Mid/high overs without a hard veto, subject to normal edge floor.

## Explicit non-rules

- No book-quality filter (books used for lines; usually synced).
- No live calibration swap.
- No stake-up on unders.
- No hard veto of *all* ≤4.5 overs unless weekly pack + bootstrap still favor it after more settles.

## Logging

Log every **real** ticket (and every hard skip of a 4.5 over that would have been KING) into `real_bets` / notes so paper ≠ cash stays honest. Checklist: `docs/reference/reports/real_bets_logging_checklist.md`.

## Review

Re-run weekly:

```bash
python production/ops/run_weekly_policy_settle_pack.py
```

Promote anything beyond the 4.5-over hard skip only with expanding n + bootstrap CI not dominated by status quo + explicit sign-off.
