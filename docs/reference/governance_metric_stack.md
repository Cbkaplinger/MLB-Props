# Governance Metric Stack (High-Signal, Low-Bloat)

This is the canonical metric set for model + policy governance tracking.

Use this stack to keep monitoring consistent across:

- `production/notebooks/model_governance.ipynb`
- `production/notebooks/results_gate_policy.ipynb`
- `production/notebooks/results_kpi_monitor.ipynb`
- `production/notebooks/results_recommendation_audit.ipynb`

Important context:

- Because production features, calibration, and edge floors changed materially in recent weeks, treat full-history aggregates as regime-mixed.
- For decisioning, always compare full-history vs recent-window views (e.g., last 30/60 settled bets).

## Current Selection Status (2026-08-21)

Current winners are tracked by objective and evaluation lane:

- **MAE winner (single-model ablation):** `ridge` on `production_sparse72` (tie with `production_sparse72_monotone`), `mean_expected_k_mae=1.7621`.
- **Profit-first ensemble winner (legacy non-deduped lane):** blend `0.70 * production_sparse72_monotone + 0.30 * production_final58_consensus`, `isotonic`, `edge_floor=0.08`.
- **Deduped transfer winner (current manual lane):** blend `0.00 * production_sparse72 + 0.60 * production_sparse72_monotone + 0.40 * production_final58_consensus`, `isotonic`, `edge_floor=0.12`.
- **Small local tune winner (LGBM/RF/HistGBR subset):** `lightgbm` on `production_sparse72_monotone` for MAE among tuned-small candidates.
- **Open-snapshot counterfactual winner (full 2025-2026 open universe, skill-gated):** `production_sparse72`, `isotonic`, `edge_floor=0.12`.

Legacy profit-first ensemble checkpoint (non-deduped replay):

- `roi=0.8121`, `sharpe=1.4609`, `sortino=0.8344`
- `brier_skill_vs_market=0.1382`, `logloss_skill_vs_market=0.1076`
- `n_bets=107`

Current decision guidance:

- Treat the deduped transfer winner above as the **active manual-lane champion**.
- Treat `production_sparse72 + isotonic + edge_floor=0.12` as the **open-universe skill champion** until next challenger cycle clears gates.
- Interpret expected-K MAE and ensemble ROI/skill as different objective lanes: the current ensemble sweep artifact is ranked on decision metrics (ROI/risk/skill), while expected-K MAE leadership is tracked in the single-model ablation lane.
- Keep MAE claims in chronological model-evaluation lanes (2023–2024 WF/CV and
  2025 holdout protocol). Use open/manual lanes for market and decision metrics only.
- Live scoring now supports an explicit k-rate ensemble config at `production/ops/live_krate_ensemble.json` (with single-model fallback).
- Keep single-model challengers live:
  - `ridge` (`production_sparse72`)
  - `lightgbm` (`production_sparse72_monotone`)
  - `xgboost` (`production_sparse72`)

Open-snapshot counterfactual checkpoint (all snapshots, no dedupe):

- opportunity rows with outcomes: `24,576`
- chrono test slice: `7,462`
- winner metrics: `roi=0.1138`, `n_bets=538`, `brier_skill_vs_market=+0.00013`, `logloss_skill_vs_market=+0.00019`
- side-floor profile `over=0.10, under=0.08` remains a monitored challenger lane, not current default.

### 1/16 Kelly Operating Translation (Unit = $50)

For the current ensemble winner replay slice:

- total stake: `$10,613.55` (`212.27u`)
- total profit: `$8,619.27` (`172.39u`)
- average stake/bet: `1.98u` (`~$99`)
- average profit/bet: `1.61u` (`~$81`)

If bankroll is `$2,000` (`40u`), replay-equivalent bankroll path is:

- starting bankroll: `40u` (`$2,000`)
- ending bankroll: `212.39u` (`$10,619`)
- net: `+172.39u` (`+$8,619`)

This assumes replay turnover/stake cadence is comparable; realized live path can differ.

## 1) Forecast Quality (Probability + Calibration)

- `brier` (lower is better)
- `logloss` (lower is better)
- `ece` (lower is better)
- `mce` (lower is better)
- `brier_skill_vs_market` (higher is better)
- `logloss_skill_vs_market` (higher is better)

Use for: checking if model probabilities beat market baseline quality, not just realized PnL.

Hard gate:

- Promotion decisions must pass `brier_skill_vs_market > 0` and `logloss_skill_vs_market > 0` on chrono-safe evaluation.

## 2) Core Decision Value (Realization)

- `roi`
- `clv_mean_pp`
- `pct_positive_clv`
- `expectancy_per_bet`

Use for: whether value signal is monetizing and whether price improvements remain positive.

## 3) Path Risk and Survivability

- `geo_growth_log_mean`
- `mc_prob_bankroll_floor_breach`
- `mc_prob_drawdown_breach`
- `max_drawdown_abs`
- `max_drawdown_pct`
- `max_recovery_bets`
- `cvar_95`
- `sortino`
- `calmar`
- `profit_factor`

Use for: sizing safety and volatility tax (a strategy can have positive expectancy but negative path quality).

## 4) Stability and Regime Robustness

- `turnover_stability`
- `tbf_sensitivity_mae_delta`
- segment dispersion by:
  - side
  - market
  - line band
  - odds band

Use for: detecting fragile gains concentrated in narrow slices.

Required window views for all promotion memos:

- full history
- last 60 settled
- last 30 settled

## 5) Edge Realization Diagnostics

- edge-decile lift:
  - `mean_edge` by decile
  - `roi` by decile
  - `mean_clv_pp` by decile

Use for: validating that higher modeled edge produces better realized outcomes.

## 6) Execution Quality (Post-Mortem)

- slippage decomposition:
  - `open_to_bet_pp`
  - `bet_to_close_pp`
  - `open_to_close_pp`
- report overall and by side/book.

Use for: separating signal quality from execution quality.

## Recommended “Quick Read” Panel

For a fast daily context panel, track:

1. `roi` (recent 30/60 + full)
2. `clv_mean_pp` (recent 30/60 + full)
3. `brier_skill_vs_market`
4. `ece` and `mce`
5. `geo_growth_log_mean`
6. `mc_prob_drawdown_breach`
7. `max_drawdown_pct`
8. `max_recovery_bets`
9. edge-decile slope (ROI from low to high decile)
10. slippage `bet_to_close_pp`

This provides quality, money, risk, and execution context without dashboard bloat.

## Feature Testing: What Still Matters

Continue:

- Small, hypothesis-driven feature edits (single family/stem changes) with strict challenger replay.
- Window-level refinements only if they improve open-skill first, then risk-adjusted policy metrics.
- Periodic challenger refresh to test drift resilience.

Stop (for now):

- Broad feature-count frontier sweeps as default workflow (high compute, low incremental lift recently).
- Promoting candidates based only on internal search objective without final open-skill gate.
- Re-running large searches without a predeclared falsifiable hypothesis.

## Next Tuning Queue (Highest Priority)

1. `lightgbm` full Optuna on:
   - `production_sparse72`
   - `production_sparse72_monotone`
2. Optional third lane:
   - `production_final58_consensus`
3. Secondary family tuning (after LGBM completes):
   - `xgboost`
   - `random_forest`
   - `histgbr`

After each tuning wave, rerun:

- single-model champion table
- ensemble sweep
- open-skill gate (`brier_skill_vs_market > 0`, `logloss_skill_vs_market > 0`)
- risk gate (drawdown/CVaR/Sortino)

## Free-Tier Production Additions

Two lightweight operational upgrades are now available:

- Model lineage logging:
  - `production/ops/log_model_lineage.py`
  - appends immutable run metadata (dataset hash, feature set, params, git SHA, decision).
- Two-stage monitoring cycle:
  - `production/ops/run_monitoring_cycle.py`
  - runs `t=0` input/open-market diagnostics and `t+1` realized quality checks.

Recommended daily cadence:

1. scoring run
2. lineage append
3. monitoring cycle run
