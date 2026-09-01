# Live Policy Promotion — 2026-09-01

**Status:** PROMOTED (user sign-off 2026-09-01)  
**Scope:** decision policy only — **no** calibration map swap, **no** champion→monotone, **no** book-quality filter.

## What went live

| Rule | Mechanism | Location |
| --- | --- | --- |
| **Hard veto `over @ 4.5`** | Quality-gate HOLD + scorer `policy_reason=veto_4_5_over` | `production/ops/kpi_policy.json` → `quality_gate.rules.side_line_vetoes`; `src/Python/odds_board.py` |
| Soft probation `over @ 2.5 / 3.5` | `probation_edge_floor=0.18` + line floor 3.5→0.18 | kpi_policy + `line_floor_policy.json` |
| Unders (incl. 4.5 under) | Unchanged | Keep betting under existing floors |
| Book-quality filter | **WONT_DO** | Explicit non-goal |
| Calibration / monotone | Unchanged | Deferred |

## Evidence anchors

- Post-freeze KING: status quo ROI −1.55% → veto 4.5 overs **+8.25%** (`weekly_policy_settle_pack_latest`).
- All-time KING floor: 4.5 overs ≈ −27% ROI; rest ≈ +4.5%.
- Bootstrap still wide (few date blocks) — treat as **risk control**, keep weekly settle pack running.

## Operator checklist

1. Follow BET board: 4.5 overs should show **HOLD** / skip with `veto_4_5_over`.
2. Log real tickets + hard skips: `docs/reference/reports/real_bets_logging_checklist.md`.
3. Weekly: `python production/ops/run_weekly_policy_settle_pack.py`.

## Related docs

- Interim skip rules (now promoted): `interim_live_skip_rules_2026-09-01.md`
- Prior shadow stance: `interim_postfreeze_ops_stance_2026-09-01.md`
- Settle pack report: `weekly_policy_settle_pack_latest.md`

## Explicitly not promoted

- Live recalibration overlay / granular open calib challenger
- Hard veto of all ≤3.5 overs
- Asymmetric live over floor as sole gate (tracked in shadow lanes)
- Book-quality filters
