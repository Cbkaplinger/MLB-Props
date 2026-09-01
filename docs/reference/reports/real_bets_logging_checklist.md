# Real bets logging checklist

Use this whenever money is down (or a hard skip overrides paper KING).

## Why

Paper `ledger.parquet` ≠ cash. Discretionary skips (Seymour-style) and the live **4.5-over hard skip** only help measurement if they are recorded.

## Minimum fields per real ticket

| Field | Example | Notes |
| --- | --- | --- |
| `game_date` | `2026-08-31` | YYYY-MM-DD |
| `player_name` | `Ian Seymour` | Stable spelling |
| `line` | `6.5` | |
| `side` | `under` | `over` / `under` |
| `book` | `draftkings` | For identity only — not a quality filter |
| `bet_price` | `-115` | **Decision-time** American |
| `stake` | `50` | Dollars actually risked |
| `result` | `win` / `loss` / `push` / `pending` | |
| `pnl` | `43.48` | Signed dollars when settled |
| `note` | `discretionary skip of 4.5 over` | Optional but useful |

## Hard-skip logging (recommended)

When paper/KING would have bet a **4.5 over** and you skip live, append a note row or keep a daily list:

- date / pitcher / line 4.5 over / `skipped_live_hard_rule` / paper edge if known

That lets the weekly pack compare “cash policy” vs paper without guessing.

## How to write

1. Fill rows in `production/ops/backfill_real_bets.py` (`REAL_TICKETS`) with real `bet_price` / `stake` / `pnl` (never leave zeros for settled cash tickets).
2. Run: `python production/ops/backfill_real_bets.py`
3. Or call `Python.real_bets.append_real_bets([...])` from a small one-off.

Unpriced rows are **held back** on purpose — do not invent prices.

## Weekly habit

After each settle day:

1. Append settled real tickets.
2. Note 4.5-over hard skips.
3. Run `python production/ops/run_weekly_policy_settle_pack.py`.
