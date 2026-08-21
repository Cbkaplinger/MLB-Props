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

## Current Selection Status (2026-08-20)

- Current winner for this cycle: `production_sparse72` with `isotonic` calibration.
- Current operating floor from deterministic sweep: `edge_floor=0.075` (7.5%).
- Frontier broad-search winner (`production_frontier42_aug20`) did **not** beat sparse72 on final apples-to-apples open-skill and governance comparisons.
- Keep confidence language conservative: open-skill advantage is positive but thin on current holdout; require rolling-window confirmation before long-horizon overconfidence.

Decision guidance:

- Treat this as the active champion for deployment testing and monitoring.
- Keep champion/challenger comparison live against:
  - `production_sparse72_monotone`
  - `production_final58_consensus`
  - `production_frontier42_aug20` (for drift checks only)

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
