# Lineup modes (frozen spec — audit §§AC, AG)

Every PA row carries `lineup_mode` + `lineup_status` + `lineup_fetched_at`
(nullable with reason). Never silently substitute final lineups in a
morning-price simulation.

- Mode 1 (realizable projected): RG snapshot with `fetched_at ≤ wager ts`,
  status kept (projected/confirmed/fallback/missing). Only modes 1–2 support
  historically-actionable claims. Coverage: THIN (5 pre-tip 2026 snapshots; no
  08:00 series) — gates the 2026 run, not the dataset spec.
- Mode 2 (confirmed): mode-1 rows with status = confirmed
  (`require_confirmed` gate semantics). Coverage: THIN (single clean case).
- Mode 3 (oracle actual): realized `is_initial_lineup` 9-man, post-game.
  Labeled non-actionable. Coverage: YES all years (exactly 9/slot, 0 nulls).
  Default for 2023–24 PA training rows; never presented as pregame-realizable.
- Mode 4 (missing fallback): declared null + fallback rule (probable-only /
  prior-day / league fill), logged per row.

Dataset spec rows: 2023–24 train on mode 3 with `lineup_mode=3` flag; 2025/26
odds-evaluable subsets carry modes 1/2 where snapshots exist, else mode 3 with
the actionability caveat. Pending owner call A5: mode priority for the 2026 run.
