# production/odds — live betting path (paper execution + grading)

## Purpose

Everything that turns projections + quotes into BET/HOLD rows, logs them,
and grades them. This is the money-adjacent layer: frozen probs in, paper
tickets out. No training, no calibration fits — scoring only.

## Daily flow (follow the data)

1. `odds_board.py` — scores the logged projection slate vs SharpAPI quotes
   (`--write-quotes` persists the quote set). Writes
   `recommendations.parquet` (+ exposure columns, veto/deploy/postseason
   reasons). BET logic lives in `src/Python/odds_board.py`.
2. `poll_odds.py --snapshot open --from-recommendations` — logs open rows
   to `ledger.parquet` (replace-per-slate; staked rows persist, no dupes).
3. `grade_odds_ledger.py` — settles (`--auto-settle-api` post-game ONLY),
   fills closes (`poll_odds.py --snapshot close`), `--status` summaries.
4. `close_watcher.py` + `run_close_sweep.py` — tip-aware close fills
   (daemon on laptop, sweeps on cloud).

## Key files

| File | Role |
|---|---|
| `odds_board.py` / `src/Python/odds_board.py` | Scoring: floors, veto/probation, edge cap, lean, DK+FD guard, exposure + game-cap (off by default) |
| `poll_odds.py` | Open logging + close fills + exposure controls (per-line/per-game/daily) |
| `grade_odds_ledger.py` | Settle/void, CLV, status, threshold curves |
| `close_watcher.py` | Laptop daemon (retires at cloud cutover) |
| `log_odds_quotes.py`, `build_ab_board_diff.py` | Quote logging, A/B board diffs |

## Rules (load-bearing)

- Never `--auto-settle-api` on unstarted games (pregame K=0 fabricates finals).
- Intraday decay never un-takes a logged ticket (staked rows persist).
- Live policy keys: `production/ops/kpi_policy.json` (+ `line_floor_policy.json`).
- Math: `src/Python/market.py` (devig, edge, Kelly, CLV, `bet_pnl` — the one money function).
- Runbook: `production/RUNBOOK.md`. Scheduler: `production/ops/setup_automation_tasks.ps1`.
