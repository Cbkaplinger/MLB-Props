# Measurement operations (replicable runbook for every analysis family)

Every command below reruns from disk ($0 unless noted) and rewrites its
report JSON in `artifacts/odds_log/`. Pre-register kill rules BEFORE running
anything new (`docs/reference/experiment_sop.md` §8). Same-subset always.

## Nightly / weekly (ops hygiene, always allowed)

```powershell
python production/odds/grade_odds_ledger.py --auto-settle-api --void-scratches --status  # post-game only
python production/ops/run_weekly_policy_settle_pack.py
python production/ops/market_research/ledger_gate_stacker.py
python production/ops/paper_quant_track.py
python production/ops/market_research/fills_analytics.py
python -m pytest tests/ -q
```

## Replay + selection (frozen model, juiced prices, vendor timestamps)

```powershell
python production/ops/market_research/juiced_replay_ledger.py           # candidates + report
python production/ops/market_research/select_2025_champion.py           # 36-config LCB selection (2025 ONLY)
python production/ops/market_research/pnl_sensitivity_audit.py          # floors, slip rule, bands, TBF tails
python production/ops/market_research/season_metrics.py                 # 2025 vs 2026 full surface
python production/ops/market_research/monthly_prob_curves.py            # monthly series + prob curve
python production/ops/market_research/confounder_strata_audit.py        # strata + matched pairs + shuffle
python production/ops/market_research/game_cap_audit.py                 # per-game cap menu
python production/ops/market_research/sizing_judgment.py                # sizing bakeoff + September/day-night
```

## Gates (each: gain >= 0.0005 Brier on common subset, else KILL)

```powershell
python production/ops/market_research/ledger_gate_stacker.py
python production/ops/market_research/ledger_gate_glicko.py
python production/ops/market_research/kalshi_overlay_gate.py
python production/ops/market_research/mc_reality_gate.py
python production/ops/market_research/disagreement_signal_probe.py      # signal test (|r| > 0.05)
```

## Calibration + curves

```powershell
python production/ops/market_research/bettable_calibration.py           # taken-set ECE/MCE (the bettor's numbers)
python production/ops/market_research/alt_curve_measure.py              # 0.5-14.5 curve shape
python production/ops/market_research/clv_flavors.py                    # same-book vs cross-book vs consensus
python production/ops/market_research/kalshi_disagreement_audit.py
python production/ops/market_research/september_cohort.py
python production/ops/market_research/monte_carlo_starts.py --n-sims 1000
```

## Data pulls (quota-sensitive — read headers first)

```powershell
python production/ops/market_research/pull_regular_season_closeout.py   # ~600/day, floor 100k, refuse today/future/past-09-28
python production/ops/market_research/pull_kalshi_k_history.py --stage ladders  # free, keyless
```

## Paper (after any manuscript.md edit)

```powershell
python docs/paper/make_figures.py
python docs/paper/render_pdf.py
python docs/paper/render_resume_summary.py
```

## Cloud (post-9/27)

`production/cloud/README.md` — token → secrets → volume → deploy → 7 parallel
days → cutover → teardown. Redeploy after EVERY src/production change
(code snapshots at deploy; state is live-shared).
