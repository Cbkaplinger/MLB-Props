# Champion / Challenger Protocol

This document defines the production promotion process for feature sets,
calibration, and edge-floor policy. It is the canonical contract to use before
any new tuning campaign.

## Scope

- Markets: pitcher strikeout props
- Primary calibration mode for current cycle: `isotonic`
- Current champion candidate: `production_sparse72`
- Current candidate operating floor: `edge >= 0.075`

## Promotion Philosophy

- Open-market probability quality is the primary objective.
- Policy profitability and risk profile are secondary constraints.
- Any candidate that wins an internal search but fails final open-skill gates is rejected.

## Metric Contract (Finalized)

### Tier 1: Primary Quality Gates (must pass)

- `brier_skill_vs_market > 0` on chrono-safe holdout
- `logloss_skill_vs_market > 0` on chrono-safe holdout

### Tier 2: Policy and Risk Gates (must pass)

- `n_bets >= 25` at chosen edge floor
- `roi > 0`
- `sortino >= 0.25`
- `profit_factor >= 1.20`
- `max_drawdown_pct` and `cvar_95` not materially worse than champion baseline

### Tier 3: Stability Gates (must pass)

Evaluate all metrics above on:

- full settled history
- last 60 settled
- last 30 settled

Pass condition:

- same model family remains top-2 across all windows
- no window with simultaneous failure of both Tier 1 gates

## Deterministic Tie-Break Order

When multiple candidates pass all required gates, rank in this exact order:

1. `brier_skill_vs_market` (descending)
2. `logloss_skill_vs_market` (descending)
3. `sortino` (descending)
4. `roi` (descending)
5. `max_drawdown_pct` (ascending)
6. `n_bets` (descending)

## Release Decision Labels

- `PROMOTE`: passes Tier 1/2/3 and wins tie-breaks.
- `HOLD`: fails any required gate, or sample is insufficient.
- `RESEARCH`: promising but does not clear stability requirements.

## Required Artifacts Per Decision

- `feature_set_market_skill_compare.csv`
- `feature_set_governance_compare.csv`
- `edge_floor_sweep_governance.csv`
- `champion_challenger_decision.json`
- `model_freeze_card.md`

## Tuning Readiness Gate

Start a tuning campaign only after:

- metric contract above is unchanged and accepted
- champion baseline artifact set is frozen
- challenger objective is explicit: improve Tier 1 without degrading Tier 2/3

## Notes on Expected Tuning Gains

Yes, gains are still realistic, but the target is constrained:

- tune for better open-skill first (Brier/LogLoss skill vs market)
- keep policy robustness and stability intact
- reject any gain that appears only in one window or one segment

