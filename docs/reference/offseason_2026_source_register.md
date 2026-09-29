# Offseason 2026 data-source register (§AH companion — measured 2026-09-28)

Refresh pulled 2026-09-28 (~18:17–18:18 UTC rebuilds). Never merge sources.
Precedence: raw JSON > envelope vendor-ts > normalized book_lines > consensus
(research only, never re-devig) > derived panels. Counts measured read-only.
Note: a concurrent pull session rebuilt derived artifacts the same evening
(postseason purge); the four hashes below are as-measured on current disk
(re-verified identical after that session).

## 1. The four odds parquets (`data/Odds-Historical/theoddsapi/`)

| File | Bytes | sha256 (2026-09-28 build) | Rows | Clocks | Coverage |
|---|---|---|---|---|---|
| `book_lines_pitcher.parquet` | 8,199,246 | `0ca77ba3…c82` | 2,404,372 | board / close / morning | snapshot_ts 2025-03-18 → 2026-09-27 |
| `book_lines_batter.parquet` | 52,944,232 | `98103f64…14e` | 15,577,193 | board / close / morning | same lake build |
| `consensus_cache.parquet` | 687,982 | `01a63d0f…78a` | 97,801 | board / close / morning | gd 2025-03-27 → 2026-09-27 |
| `snapshot_envelope.parquet` | 492,216 | `2b73bc40…3b9` | 14,531 | board 4,912 / close 4,724 / morning 4,895 | commence 2025-03-18 → 2026-09-27 |

(Full hashes in funnel-manifest addendum 2026-09-28; abbreviated above.)

## 2. Clock definitions (board-canonical)

- **board** (CANONICAL OPEN): requested 12:00 UTC ≈ 08:00 ET; vendor lag ~4.4 min
  (probe `open_clock_probe_board.json`). K-main: 115,103 rows / 4,841 events.
- **close**: ≈ commence−5 min. K-main: 156,660 rows / 4,705 events.
- **morning**: ≈ commence−5 h. K-main: 153,468 rows / 4,866 events.
- Board+close K-main event intersection: 4,645 events.
- No −30h/−24h clocks exist for MLB props (probes `_12`, `_12_8` tested −12h and
  thinner books; open ≈ 8am board stands). Friend −12h CSVs deprecated (end 07-10).

## 3. Books, markets, provenance

- Books (9, all clocks): DK, FD, BetMGM, BetOnline, Bovada, Fanatics, BetRivers,
  WH_US, MyBookie. Raw: `raw/snapshots/{board,close,morning}/` (~10.4k JSONs) +
  `raw/event_index/` + `raw/featured/totals/{morning,evening}/`.
- Pitcher markets: K-main 425,231 rows; K-alt 1,145,185; hits-allowed 287,103;
  outs 240,426; ER 231,212; walks 75,215. Alt is over-only by design; ER/hits/
  outs carry one-sided rows — same-book-preferred, cross-book fallback.
- Batter-K is a GHOST market: 43,006 rows / close 742 + morning 602 events (no
  board rows measured) vs pitcher-K ~4.7–4.9k events/clock. Never a primary.
- Consensus: devig-median, `n_books` kept; K 50,673+ rows across 3 clocks.
- Postseason: 88 Oct/Nov-2025 envelope rows exist — excluded by design (§AI-5).

## 4. Provenance chain

Per event/clock: raw JSON (`timestamp/previous/next`) → envelope
(`vendor_timestamp`, `reconstructed_ts`, lag fields, `has_envelope` = 100%, 0
missing) → normalized `book_lines` → `consensus_cache`. Envelope gates every
judge: postdate rows refused (board 2, close 14, morning 0 with
`lag_vendor_vs_commence_sec < 0`); recon>10min rows flagged; no recon-ts
substitution, no forward-fill.

## 5. Skipped-events / 404 record
- `raw/skipped_events.json`: 51 event IDs skipped at pull (kept, reason-coded at
  pull time; re-check before the 2026 run — a skipped event with later coverage
  must not silently re-enter).
- `pull_state.json` (theoddsapi root): spent 688,189 / remaining 3,003,381
  credits at refresh end.
- No separate 404 file exists; HTTP-level misses are represented inside
  `skipped_events.json` only. Absence of a row is NOT evidence of absence of a
  market — see §AI-1 (missing-board = no-bet).

## 5b. Dup-key resolution rule (measured 558, post-refresh recount)

Exact duplicate keys on
`(event_id, snapshot, book, market, player_norm, line, side)`: **558** (was 548
pre-refresh). Of these, 48 carry >1 distinct price; the rest are identical-price
vendor double-posts. Concentrated in BetOnline outs close/morning.
Rule (frozen): **first-wins** — panel builders take `.first()` per key, never
average, never last-wins. Multi-price subset (48) is flagged in the join audit,
never silently resolved. Any rebuild that changes this count trips the manifest
hash and gets a choice-log entry.

## 6. Non-canonical companions (never merged)

- `featured_totals.parquet` (526,693 bytes, `b9d6a50f…e56`; 220,482 rows;
  clocks morning/evening; gd → 2026-09-10, STALE): slate-shock environment only.
- Friend opens: RETIRED 2026-09-28 on owner order (both CSVs deleted,
  uncommitted). Preserved as workspace evidence only:
  `friend_only_backup_pitcher_strikeouts_early_open.parquet` (16,589 bytes,
  sha256 `104e3169…f21fef`, 290 rows) +
  `friend_only_backup_pitcher_outs_open.parquet` (11,379 bytes, sha256
  `bf097e37…c395b9`, 34 rows) — 35 friend-only events incl. 12 real starts.
  Production grading degrades gracefully (missing files are skipped, verified
  `grade_odds_ledger.py:79`); research callers fail loud if run. Re-check the
  12 starts before the 2026 run.
- `_probe/open_clock_probe*.json` (4 files): evidence-only clock experiments,
  never inputs.
- Kalshi `k_ladder/k_closes.parquet` (07-02 → 09-07): marquee-only second
  opinion. Live tip-window ticks live in cloud volume only.
