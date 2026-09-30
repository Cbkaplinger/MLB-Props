# Phase 8 — Constrained Tree Challenger (TREE-PA-T)

Executed 2026-09-30. Card sha256 95b9627d... (hashed before fitting; three pre-evaluation
construction fixes logged in deviations.md: park_team derivation, 2023 P3 construction matching
the Phase 7-registered P2-style baseline, monotone-constraint vector length). Writer boundary:
this directory only. Production untouched. No 2025/2026 read.

## Preflights

1. **MLflow: DEFERRED.** Not installed; installing mid-phase risks environment churn before a
   registered evaluation. Adopt post-tree as a read-only SQLite mirror over existing
   cards/manifests/hashes; cards remain authoritative; MLflow failure nonfatal.
2. **Projected-lineup replay: NOT READY** (`lineup_replay_audit.json`): 6 snapshots, 1,278 rows,
   2026 only, no MLBAM IDs, single fetch per file, ~1-2 true pre-tip days. Lane D deferred to
   2027 lineup-version logging.

## Design

- T0 = L3 (immutable bundle). Inputs identical to the validated L3 feature build:
  F1-F5 (16 cols) + trip/index (4) + logit(P3) baseline input; F6 rest excluded.
- T1: 32-config LightGBM grid selected on 2023 folds F1/F2 only.
- T2: monotone-increasing constraints on 10 K-tendency rate inputs, best T1 config.
- T3 blend gate: 2023 OOF corr <= 0.85 AND blend beats better single arm > 0.0002
  (proxy: P3-log5 residuals; fold-fitted L3 models were not serialized — labeled deviation).

## 2023 selection (only evidence used for choices)

- T1 best: leaves 7, depth 3, min_data 500, ff 0.8, lambda 1.0 -> mean fold logloss 0.516918.
- T2 monotone: 0.517279 (worse) -> NOT used.
- Blend gate: corr = 0.9965 (tree residual is ~a rescaled P3 residual); best blend 0.517019
  vs single 0.517279 -> improvement 0.00026 > 0.0002 BUT corr gate fails decisively.
  **BLEND: NOT MET.**

## 2024 evaluation (one shot, paired vs T0=L3)

| Block | L3 logloss | tree logloss | paired delta | 95% CI | fav |
|---|---|---|---|---|---|
| E1 | 0.513641 | 0.513663 | +0.000022 | [-0.00038, +0.00042] | 0.473 |
| E2 | 0.516707 | 0.516666 | -0.000042 | [-0.00037, +0.00027] | 0.582 |

Brier deltas equally indistinguishable (E2 fav 0.830, CI crosses 0). Calibration beta: tree
0.933/0.957 vs L3 0.977/1.010 (tree slightly underconfident but in registered range).

## Interpretation

- Family ablations (2023 folds): F2 batter discipline +0.000915, L3 terms +0.001369 dominate;
  F4 history negative (redundant with baseline).
- Grouped permutation (2024): same ordering; park ~0.
- Oracle aggregation: MAE differences at the 4th decimal (E1 -0.00054, E2 -0.00011), CIs
  straddle 0. Bias shifts but no net gain.

## Verdict

**TREE BEATS L3 AT PA LEVEL: NO** (registered gate requires both blocks + preferred 100%
direction; ties are the stop condition). **TREE SIGNAL SURVIVES AGGREGATION: NO.**
**BLEND JUSTIFIED: NO.** Per the registered stop rule: complexity escalation stops; the
development PA baseline remains **L3 (logistic)**. The additive-logistic structure has fully
absorbed the available signal in these features; nonlinear/interaction capacity adds nothing.
This is a strong negative result that strengthens the case for L3 as the frozen development
baseline entering 2025 validation.

## Next authorization (owner)

Count-distribution work (Poisson-binomial vs Poisson) and the pregame xK replay lane remain the
next frontiers; neither is started automatically.
