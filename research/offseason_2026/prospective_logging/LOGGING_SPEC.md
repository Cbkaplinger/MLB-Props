# Prospective 2027 logging spec (pregame-state / forecast capture)

Status: DESIGN + SKELETON. No live calls, no production changes, no scheduler.
Owner: desk owner. Target season: 2027.

## Why

The 2024-2025 pregame diagnostics (bf-workload-v1, pregame-state-v1) had to
approximate or reconstruct pregame state from hindsight data. Three things
were missing historically and still are in production:

1. a timestamped lineup snapshot with per-batter MLBAM IDs in slot order
   at fetch time (partially exists - see gap list),
2. the model forecast that was actually live at cutoff (probabilities +
   artifact hashes),
3. market prices at the same cutoff.

Logging these three, write-once, makes every 2027 start a clean pregame
forecast-and-settlement row with no reconstruction.

## Record types

Four append-only record types, one JSON object per record, one JSONL file
per record type per day (`records/<record_type>/<YYYY-MM-DD>.jsonl`).

### 1. Lineup snapshot (`lineup_snapshot`)

One record per (game_pk, team) per fetch. Never updated in place; a later
fetch appends a new record (revisions are resolved by latest
`fetched_at <= cutoff`).

```json
{
  "record_type": "lineup_snapshot",
  "schema_version": "lineup_snapshot/1",
  "record_id": "<hex64 content hash>",
  "prev_hash": "<hex64 or null for first of the day>",
  "fetched_at": "2027-04-01T12:00:00Z",
  "forecast_cutoff": "2027-04-01T12:00:00Z",
  "game_date": "2027-04-01",
  "game_pk": 745123,
  "double_header": "S",
  "game_number": 1,
  "team": "NYY",
  "lineup_status": "confirmed",
  "source": "rotogrinders",
  "probable_pitcher_id": 677944,
  "slots": [
    {"slot": 1, "batter_id": 680757, "batter_name": "Player One"},
    {"slot": 2, "batter_id": 608070, "batter_name": "Player Two"}
  ],
  "n_slots": 9
}
```

Rules: `batter_id` is the MLBAM id (integer), never name-matched after the
fact; slot order is the captured batting_order at fetch time; `lineup_status`
is the vendor status at fetch (confirmed/projected); a record is never
rewritten - a lineup change after the cutoff produces a NEW record that a
later cutoff would reject, which is exactly the audit trail we want.

### 2. Forecast record (`forecast_record`)

One per (game_pk, side, pitcher) per cutoff - the model's pregame output.

```json
{
  "record_type": "forecast_record",
  "schema_version": "forecast_record/1",
  "record_id": "<hex64 content hash>",
  "prev_hash": "<hex64>",
  "forecast_cutoff": "2027-04-01T12:00:00Z",
  "game_date": "2027-04-01",
  "game_pk": 745123,
  "side": "home",
  "pitcher_id": 669302,
  "model": {
    "bundle_name": "bf-bundle-2027-...",
    "artifact_sha256": {"model_txt": "<hex>", "sidecars": ["<hex>"]},
    "recipe_hash": "<sha256 of the frozen recipe/config JSON>",
    "arm": "h3_logistic|cumulative_log5|champion"
  },
  "inputs": {
    "lineup_snapshot_ids": ["<record_id>", "..."],
    "bf_pmf37": [0.001, "... 37 floats, index 36 = P(N>=37)"],
    "p_bar_per_slot": [0.211, "... 9 floats, cycled-sequence base"],
    "count_pmf": {"k_max": 24, "probs": [0.001, "... 24 floats"]}
  },
  "exposure": {"e_n": 18.4, "point_exposure_n": 18}
}
```

Rules: probabilities are stored at full float precision (no rounding);
`bf_pmf37` uses the frozen 37-category convention (index 36 = overflow);
`count_pmf` uses k_max=24 with the last bucket absorbing >=23 (kcount
prereg convention); `lineup_snapshot_ids` ties the forecast to the exact
snapshots consumed (id-level lineage, not just game_pk).

### 3. Market snapshot (`market_snapshot`)

One per (game_pk, pitcher, book, line) per poll - timestamped, append-only.

```json
{
  "record_type": "market_snapshot",
  "schema_version": "market_snapshot/1",
  "record_id": "<hex64 content hash>",
  "prev_hash": "<hex64>",
  "captured_at": "2027-04-01T12:05:00Z",
  "game_date": "2027-04-01",
  "game_pk": 745123,
  "pitcher_id": 669302,
  "book": "fanduel",
  "line": 6.5,
  "side": "over_under",
  "over_price": -115,
  "under_price": -105,
  "source": "sharpapi"
}
```

Rules: raw prices as returned (American); both sides of the same line in
one record when the book returns both; polls append, never update; the
ledger remains the bet-grade source - this capture is the forecast-side
market state at cutoff.

### 4. Settlement record (`settlement_record`)

One per (game_pk, pitcher) after the game, written once by the settlement
step (corrections are new records with `corrects_record_id`, never edits).

```json
{
  "record_type": "settlement_record",
  "schema_version": "settlement_record/1",
  "record_id": "<hex64 content hash>",
  "prev_hash": "<hex64>",
  "game_pk": 745123,
  "pitcher_id": 669302,
  "final_k": 7,
  "final_bf": 23,
  "game_status": "final",
  "void_reason": null,
  "push_semantics": {"half_lines_cannot_push": true,
                     "integer_line_push": "void_refund"},
  "corrects_record_id": null,
  "settled_at": "2027-04-02T12:00:00Z"
}
```

Join keys back to forecasts: `(game_date, game_pk, pitcher_id)`;
`pitcher_id` must be reconciled against the forecast's `pitcher_id`
(probable-vs-realized mismatch is a documented event, not a silent rejoin).

## Write-once / hash-chain convention

- **Append-only JSONL.** One file per record type per day. Never rewrite,
  never delete; corrections are new records referencing the old
  `record_id`.
- **Daily chain.** Within a `(record_type, game_date)` file, every record
  carries `prev_hash` = the previous record's `record_id` (null for the
  first record of the day, which anchors the chain).
- **record_id.** `sha256(canonical_json(record_without_record_id))` -
  canonical = sorted keys, no whitespace, UTF-8. Because `prev_hash` is
  part of the hashed body, editing ANY written record (or reordering
  rows) breaks the chain at recomputation; `logger.py` fails loudly.
- **Daily head.** After the last append of the day, the chain head is
  recorded in `chain_state.json` (`{record_type, date, last_hash, n_records}`).
  `logger.py verify_chain(record_type, date)` recomputes the full chain and
  fails loudly on any break (tamper-evidence, no network I/O).
- Storage clock: UTC timestamps everywhere (`fetched_at`, `captured_at`,
  `settled_at`), tz-aware ISO-8601, per the ET-display/UTC-storage
  convention already adopted for the archive.

## What production daily_lineups already provides

`data/processed/daily_lineups_*.parquet` (2026 capture, 6 dates) already
has: `fetched_at` (one per file), `lineup_status` (confirmed/projected),
`batting_order` (1-9), `batter` (MLBAM id), `player_name`, `game_pk`,
`game_number`, `double_header`, `away_probable_pitcher_id` /
`home_probable_pitcher_id`, `game_time`, `rg_game_number`, team columns.
Slot order at fetch time IS captured per batter - this is the part the
historical research could not get.

## Gap list vs this spec (what 2027 logging must add)

| Gap | Detail |
|---|---|
| Raw-response hash | captures are ingestion-verified but raw-hash-unverified; store sha256 of the vendor payload at fetch time (backlog 2026-10-09 finding) |
| Guaranteed cadence + cutoff field | 2026 capture was intermittent (6 fetches in ~4 weeks); schedule the snapshot daily before the declared cutoff and stamp `forecast_cutoff` explicitly |
| In-file revision chain | one fetch per file today; multiple same-day fetches must each append (record_id chain gives revision history) |
| Forecast record | nothing logged today: model/bundle hashes, BF PMF, p_bar, count PMF, cutoff are not persisted with predictions |
| Market prices | no per-game pregame price capture at cutoff for non-bet games (ledger only logs bets) |
| Settlement join | final K/BF per (game_pk, pitcher) with void/push semantics is not captured as a record; settlement join keys must be `(game_pk, pitcher_id)` with probable-vs-realized reconciliation |
| Batter id completeness | 2026 files have batter ids, but null-rate for projected lineups and late scratches must be monitored; record n_slots + status per snapshot |
