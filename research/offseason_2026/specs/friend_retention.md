# H4 ADDITIONS: friend-opens redundancy (measured 2026-09-28).

## DELETED 2026-09-28 on explicit owner order (uncommitted; owner commits).
Both CSVs removed from `data/Odds-Open-Close-2025-2026/`. Preserved in
workspace `artifacts/` (provenance, never inputs): 290 K + 34 outs
friend-only rows (`friend_only_backup_*.parquet`) covering 35 + outs-only
events with no paid-lake equivalent, incl. 12 real starts.

#
# Friend CSVs are DEPRECATED but RETAINED (not deleted):
# - 2,964 friend events; 2,929 overlap the paid lake; 35 events are friend-only.
# - Of those 35, 12 match real starts in pitcher_games (87 rows) — unique opens
#   with no paid-lake equivalent. Deleting the files would destroy those opens.
# - Reads: 290 friend-only rows / 35 events / 12 real-start events (ID join on
#   game_date + pitcher_id). Method: exact ID join, no name matching.
# - Rule: keep both CSVs until the 2026 run; re-check the 12 events then. Friend
#   never feeds a build as anything but fallback opens with provenance tag.
