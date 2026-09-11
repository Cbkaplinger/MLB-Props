# Market Research Ops

Post-hoc research only: chrono-safe panels, small challengers, shadow gates.
Live plan lives in `docs/EXECUTION_BACKLOG.md` (master work-state); program
doc `docs/reference/beat_the_books_program.md`; experiment rules
`docs/reference/experiment_sop.md`; retrain discipline
`docs/reference/retrain_spec.md` (pregame retrain path CLOSED 2026-09-10).

## Pipeline (run in order)

1. **Score** frozen bundle over history (no re-spins, ever):
   `score_historical_range.py` → `artifacts/live_scores/historical_scores_2025_2026.parquet`
   (`--out` for config variants, e.g. `historical_scores_live_20260910.parquet`
   scored under Poisson + WS1c).
2. **Join** model x books: `join_universe.py` (`--scores/--panel-out/--audit-out`)
   → `artifacts/odds_log/universe_panel[_live].parquet` (70k line-points) +
   join audit. Shared keys in `join_keys.py` (`sorted_key`, `read_consensus_cache`
   — all research reads the cache, never re-devigs).
3. **Cells** (bins-first doctrine): `run_universe_cells.py`, `ws1c_line_recal.py`
   (per-line Platt — SHIPPED live 9/10), `alt_curve_harness.py` (curve shape),
   `rescore_shiplift.py` (ship-lift), `rescore_cal_cells.py` (ECE/MCE/bias).
4. **Consensus**: `build_consensus_cache.py` (70k props, K+outs x close/morning).
   Pulls: `pull_oddsapi_historical.py` (paid, closes-first, credit-capped) +
   `pull_regular_season_closeout.py` (day-by-day driver to season end) +
   `pull_kalshi_k_history.py` (sharp anchor) + `pull_opencommand.py` /
   `build_start_command.py` (NC-licensed command data, research only).
   Envelope recovery: `recover_snapshot_envelope.py` ($0; vendor
   timestamp/previous/next from raw JSON — normalizer reconstructs clocks).
   Featured totals: `pull_featured_totals.py` (whole-slate `/odds`, ~7.3k
   credits, slate environment — not a K feature).
   Standing spec: `docs/reference/oddsapi_replay_architecture.md`.
   Inventory: `docs/reference/reports/oddsapi_replay_inventory_2026-09-11.md`.
   Juiced ledger report: `docs/reference/reports/juiced_replay_ledger_2026-09-11.md`.

## Workstream probes (all post hoc; kills filed in backlog)

Blends: `fit_consensus_blend.py`, `combo_matrix.py` (both dead — w=0).
Count family: `count_family_race.py` (Poisson wins — SHIPPED live 9/10).
Staleness: `ws2_staleness_probe.py` (dead), `ws2_age_cells.py` /
`ws2_age_correct.py` (U-shape found; overlay dead, retrain dead #66),
`build_age_table.py`.
TBF: `ws3_tbf_probe.py`, `ws3b_hook_rates.py`, `ws3c_workhorse.py` (all dead).
Timing: `ws6_timing_decay.py` (bet-at-open doctrine). Floors: `ws7_floor_gate.py`
(challenger dead — live policy stands). kAdj: `ws8_kadj_probe.py`,
`kadj_l3_parity.py`, `ledger_gate_kadj.py` (both vehicles dead).
Matchups: `ws9_famvuln_probe.py` (dead). Tails: `tail_recal.py` (healthy),
`nb_tbf_mixture.py` (dead). Command: `command_optionA_retest.py` (dead).
Slots: `ws5b_poisson_binomial.py`, `ws5b_blend_fit.py` (dead, w=0).
Retrain ablations: `models/Strikeout-Model/research/` (age/command/combined60/
walkforward — path EXHAUSTED, spec section 7).

## Live challengers (shadow → gate → sign-off)

- `distill_stacker.py` (morning-consensus logit overlay — SURVIVED universe +
  `ledger_gate_stacker.py` bettable gate) — promotion proposal in backlog.
- `ledger_gate.py` (original ship-gate pattern for Poisson + WS1c).
- `correction_audit.py` (price-offset audit + `--caps` shadow arms) and
  `deploy_regate.py` (ON/OFF re-derive) — recommend only, acting needs sign-off.
- `decision_grade_harness.py` (2025-select → 2026-judge policy simulator) +
  `juiced_price_spike.py` (fair→juiced translation: -3.3pp).
- `juiced_replay_ledger.py` (frozen `p_ours_cal`, juiced open/morning, rejected
  candidates, four sizing arms). Measurement only — do not retune live policy
  from 2026 confirmatory ROI. Report: `artifacts/odds_log/juiced_replay_report.json`.

## Policy inputs (live; freshness in `../policy_freshness_audit.py`)

Fresh: WS1c pointer, Poisson default, veto/floors (evidence-backed), L3.
Stale-regate: price offsets (cap/remove/keep pending owner), deploy matrix.

## Run All (legacy entry point)

```powershell
.\.venv\Scripts\python.exe production/ops/market_research/run_market_research.py
```

## Live Testing Hook

```powershell
.\.venv\Scripts\python.exe production/odds/odds_board.py --unit 50 --roi-mode conservative
```

`conservative` enables correction offsets + line floors + deploy-matrix filter
at edge floor 0.12. Intraday harvest: `../frozen_edge_watch.py` (pages only
skip/HOLD→BET flips; wired into `run_market_refresh.ps1`).
