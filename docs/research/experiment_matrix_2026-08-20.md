# Experiment Matrix (2026-08-20 cycle)

This matrix is the canonical map of the latest model-comparison runs, with
explicit data windows, market baseline definitions, and policy assumptions.

## Run catalog

| Run | Script | Data window | Baseline | Policy scope | Output |
|---|---|---|---|---|---|
| Open-skill broad compare | `production/ops/compare_feature_set_market_skill.py` | 2025-2026 open opportunities (chrono split) | De-vigged open over/under from open CSV | None (pure probability quality) | `artifacts/odds_log/feature_set_market_skill_compare.csv` |
| Open-skill holdout | `production/ops/compare_feature_set_market_skill.py --eval-start-date 2025-01-01 --eval-end-date 2025-12-31 --output-tag holdout_2025` | 2025 only | De-vigged open over/under from open CSV (12h pre-pitch source lane) | None (pure probability quality) | `artifacts/odds_log/feature_set_market_skill_compare_holdout_2025.csv` |
| Settled replay governance | `production/ops/compare_feature_set_governance.py` | Settled ledger slice (current depth) | De-vigged side prob from ledger `over_price/under_price` snapshots | Balanced policy floor and replay quant-risk stack | `artifacts/odds_log/feature_set_governance_compare.csv` |
| Edge-floor deterministic sweep | `production/ops/edge_floor_sweep_governance.py` | Settled ledger slice | Uses open-skill file from broad compare for primary gate | Edge-floor sweep 0.5%-8.0%, sample gate >=25 | `artifacts/odds_log/edge_floor_sweep_governance.csv`, `champion_challenger_decision.json` |

## Current evidence summary

### A) 2025 open holdout (primary anti-overfit check)

Top row by open-market skill:

- `production_sparse72_monotone` + `isotonic`
  - `brier_skill_vs_market = +0.007018`
  - `logloss_skill_vs_market = +0.005015`
  - `n_eval_rows = 5342`

Interpretation:

- This is the strongest current out-of-time signal among finalists.
- In this 2025 holdout lane, `production_sparse72` isotonic is negative, while
  monotone isotonic is positive.

### B) Settled replay (money/risk policy lane)

- Sparse72-family variants remain at/near top depending on calibration mode and
  policy assumptions.
- Replay sample remains shallow by date depth, so this lane is useful but lower
  confidence than the larger open-opportunity holdout for primary model ranking.

## Data assumptions and caveats

- "Open" baseline in this cycle maps to the preserved open quote dataset
  (`pitcher_strikeouts_early_open_2025_2026.csv`), sourced from 12h pre-pitch
  capture lane.
- Ledger replay baseline is snapshot-based and should not be interpreted as a
  full universal market baseline.
- Recent-window replay slices (`last_30`/`last_60`) currently collapse to the
  same sample when settled-date depth is limited.

## Finalized pre-tuning metric contract

1. Primary model gate:
   - `brier_skill_vs_market`
   - `logloss_skill_vs_market`
2. Secondary policy gate:
   - edge-floor frontier risk/return (`roi`, `sortino`, `max_drawdown_pct`,
     `cvar_95`, `positive_clv_share`, `turnover_stability`, `n_bets`)
3. Stability view:
   - full + recency windows where available.

## Immediate next step

Proceed to targeted tuning with fixed finalist sets:

- `production_sparse72_monotone` (primary)
- `production_sparse72` (secondary challenger)
- `production_final58_consensus` (MAE-oriented challenger)

Acceptance remains based on holdout-first open-skill gates, then policy/risk.

