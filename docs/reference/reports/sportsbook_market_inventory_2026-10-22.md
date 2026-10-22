# Sportsbook market inventory (open + close data) — 2026-10-22

One-page inventory of every market with timestamped open/close
sportsbook data on disk. VERIFIED DIRECTLY FROM THE PARQUETS (polars
scan), not from prior reports. For repo searchers (Perplexity et al.):
the odds data is NOT in git — it lives in the gitignored `data/` tree
and the research lake (`C:\Users\ckaplinger\MLB-Props-Research\`).

## Where the data lives (repo map)

| what | path |
| --- | --- |
| Historical quotes archive (The Odds API, sha-manifested) | `data\Odds-Historical\theoddsapi\` |
| Pitcher quote rows | `data\Odds-Historical\theoddsapi\book_lines_pitcher.parquet` |
| Batter quote rows | `data\Odds-Historical\theoddsapi\book_lines_batter.parquet` |
| Snapshot envelope (5 pregame clocks + commence times) | `data\Odds-Historical\theoddsapi\snapshot_envelope.parquet` |
| Raw vendor payloads (32,080 JSONs) | `data\Odds-Historical\theoddsapi\raw\snapshots\{close,morning,board,board_2023_24,open18}\` |
| Kalshi exchange capture | `data\Odds-Historical\kalshi\k_ladder.parquet`, `k_closes.parquet` |
| Archive manifest + hashes | `data\Odds-Historical\theoddsapi\archive_manifest_2026-10-06.json` |
| Coverage/feasibility analysis (existing) | lake: `MLB-Props-Research\odds-coverage-v1\COVERAGE_REPORT.md` |
| Archive acceptance audit | lake: `MLB-Props-Research\odds-archive-acceptance-20261006\acceptance-audit-report-2026-10-06.md` |
| Market-eval harness (existing, 84 KB module + card) | lake: `MLB-Props-Research\market-eval-v1\` |
| Live SharpAPI poll artifacts (2025-26 era) | `artifacts\odds_log\` (universe_panel, open_quotes_canonical, sharp_quotes_latest, real_bets, tickets) |
| Live poll code | `production\odds\poll_odds.py`, `odds_board.py`, `close_watcher.py`; `src\Python\odds_ledger.py`, `sharp_odds.py` |
| Historical pull code | `production\ops\market_research\pull_oddsapi_historical.py` |
| Empty placeholder (documented, no data) | `data\Odds-Open-Close-2025-2026\` |

## The inventory (verified 2026-10-22)

Schema for both quote parquets: `event_id, snapshot, snapshot_ts,
game_date, season_type, book, market, player, player_norm, line, side,
price`. Pregame clocks (snapshots): `close` (T-5min requested, returned
p50 T-9.35min), `morning` (T-5h), `open18` (T-18h, 2023-24),
`board_2023_24`, `board` (12:00Z, 2025-26).

### Pitcher markets — `book_lines_pitcher.parquet` (4,025,730 rows)

| market | rows | date range | books | events | implied prediction target |
| --- | --- | --- | --- | --- | --- |
| pitcher_strikeouts_alternate | 1,553,267 | 2023-08-01..2026-10-08 | 9 | 8,156 | full K ladder (line 0.5..22.5) — count distribution |
| pitcher_strikeouts | 923,171 | 2023-05-03..2026-10-08 | 13 | 9,262 | principal K line — count O/U |
| pitcher_hits_allowed | 505,062 | 2023-05-03..2026-10-08 | 8 | 9,221 | hits allowed O/U — PA hit-class aggregate |
| pitcher_earned_runs | 441,525 | 2023-05-03..2026-10-08 | 8 | 9,221 | runs allowed O/U — not directly modeled |
| pitcher_outs | 396,910 | 2023-05-03..2026-10-08 | 10 | 8,830 | outs recorded — invertible from BF/K/BB mix |
| pitcher_walks | 205,795 | 2023-05-03..2026-10-08 | 5 | 9,114 | walks O/U — PA walk-class aggregate |

Books: barstool, betmgm, betonlineag, betrivers, bovada, draftkings,
fanatics, fanduel, mybookieag, pointsbetus, superbook, unibet_us,
williamhill_us. Line range 0.5..22.5.

### Batter markets — `book_lines_batter.parquet` (33,245,961 rows)

| market | rows | date range | books | events | implied prediction target |
| --- | --- | --- | --- | --- | --- |
| batter_total_bases | 7,675,980 | 2023-05-03..2026-10-08 | 12 | 9,280 | TB O/U — needs batted-ball model (not built) |
| batter_hits | 6,516,178 | 2023-05-03..2026-10-08 | 13 | 9,280 | hits O/U — needs batter-class model (not built) |
| batter_home_runs | 4,033,981 | 2023-05-03..2026-10-08 | 13 | 9,279 | HR O/U — not modeled |
| batter_rbis | 3,809,574 | 2023-05-03..2026-10-08 | 10 | 9,278 | RBI O/U — team-context, not modeled |
| batter_runs_scored | 3,417,591 | 2023-05-03..2026-10-08 | 9 | 9,279 | runs O/U — team-context, not modeled |
| batter_hits_runs_rbis | 2,977,684 | 2023-05-03..2026-10-08 | 8 | 9,265 | combined — not modeled |
| batter_singles | 2,801,065 | 2023-05-03..2026-10-08 | 10 | 9,278 | singles O/U — not modeled |
| batter_walks | 1,498,739 | 2023-05-03..2026-10-08 | 5 | 9,257 | walks O/U — batter-class aggregate |
| batter_strikeouts | 515,169 | 2023-05-03..2026-10-07 | 4 | 4,713 | batter K O/U — never offered in 2025 (documented gap) |

### Exchange

| artifact | rows | content |
| --- | --- | --- |
| `k_ladder.parquet` | 11,929 | Kalshi K yes-price ladder (small) |
| `k_closes.parquet` | 676 | Kalshi closes |

## Top 2 markets by data volume (the owner's calibration-plan targets)

1. **pitcher_strikeouts (+ alternate ladder)** — 2.48M combined rows,
   13 books, deepest history, closes for ~90% of cohort starts
   (coverage join in COVERAGE_REPORT.md). Target: the K count
   distribution — exactly what the count layer, M0, and the C-B1
   machinery produce.
2. **pitcher_hits_allowed** — 505k rows, 8 books. Target: the hits-
   allowed count — the M0 four-class model's P(class 3 = hit) per PA
   aggregated over the BF workload is the natural generator.
