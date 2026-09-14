# Cloud cutover (Modal) — staged, not deployed

## Why Modal + parquet (not SQL)

- Daily chain reads 18k-row frames (seconds per scan) and appends single-writer
  parquet. No concurrent writers, no relational queries in the prod path.
  SQL buys nothing; Neon-style free Postgres adds idle-sleep flakiness plus a
  ledger-write migration. Revisit only on multi-reader contention.
- Hot state ≈ 350 MB (L3/rolling 248 + live_scores 75 + odds_log 15 + models 8
  + projection_log 2 + policies). Volumes give 1 TB free: upload once.

## Go-live checklist (owner gates)

1. `pip install modal` → `modal token new` (OAuth, no card).
2. `modal secret create mlb-props-keys SHARPAPI_KEY=... THEODDSAPI_KEY=... NTFY_TOPIC=...`
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
