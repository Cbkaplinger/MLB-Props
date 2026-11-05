# October pickup checklist (season-end execution order)

Durable trigger list for when the 2026 regular season ends (last games 9/27;
postseason HOLD takes effect automatically — paper continues, BET stops).
Master work state stays in `docs/EXECUTION_BACKLOG.md`; this file is the
ordered runbook. Archive it after execution.

## Trigger

Do not start before: (a) regular season complete, (b) final closeout sweep
(`--end 2026-09-28`) green, (c) September paid-close coverage verified. The
band-grid v2 executor refuses peeked selection mechanically; the official run
uses defaults (`--select-from 2026-09-28`, no flags).

## Order

1. **Closeout.** Final sweep all 15 markets close+morning thru 9/28. Verify
   paid-close coverage on settled+staked (was 92% on 9/16; do not proceed
   under 85% — backfill first).
2. **September judge.** Locked champion on fresh September closes only;
   fills to 20 → `fills_analytics.py` powers on (target 50).
3. **Band-grid v2 single execution.** `python
   production/ops/market_research/band_grid_v2.py` (defaults). Binding per
   prereg `docs/reference/reports/band_grid_v2_prereg_2026-09-17.md`: winner
   promotes exactly (pin + board-fire ceremony); White p ≥ 0.05 or winning
   LCB ≤ 0 → no promotion, live stays, rationale filed.
4. **Full-2026 re-judge** of the winner (max n, September included) +
   cell/month exclusions alongside (advisory).
5. **Follow-ons in order:** slate correlation caps (from exposure columns) →
   stacker verdict → legacy re-gates (floors, veto, deploy matrix) on the v2
   winner → Modal cutover decision (7 agreeing days) or teardown runbook.
6. **Paper.** Extend Table 6 + Figs 10–11 to full season, appendix the v2
   selection, rebuild HTML/PDF, archive this file's completion note.
7. **Money truth.** Fills ledger review at n ≥ 20; paper-vs-fill drift;
   bankroll readout (currently $5,000, flat $50 = 1.0%).

## Standing constraints (unchanged)

Free-only. No retrains (model frozen). No selection on peeked data — the v2
executor enforces this; `--allow-peeked` runs are labeled and never promote.
No live BET-set change without a named owner order. Never `git push` from an
agent turn (owner pushes).

## Artifact inventory (what feeds what)

| Step | Reads | Writes |
|---|---|---|
| Closeout | OddsAPI quota (floor 100k), event map | `consensus_cache.parquet`, `book_lines_*.parquet` |
| September judge | ledger, paid closes, `real_bets` | `daily_grading_*.json`, fills report |
| v2 execute | `juiced_replay_candidates.parquet` | `band_grid_v2_report.json` |
| Promotion | v2 report, `kpi_policy.json`, pin test | board-fire + pin commit |
| Paper | monthly/ab reports, figures | `manuscript.{md,html,pdf}` |
