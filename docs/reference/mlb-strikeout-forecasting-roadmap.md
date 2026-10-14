# Professional MLB Strikeout Forecasting Roadmap (future plan)

> Status: PLAN ONLY. No frozen model code, forecasts, scoring rules, sealed
> artifacts, or current closure work are modified by this document.

## P0 — Governance and data card

- Canonical grain/key contract for pitch, PA, start, game, lineup snapshot,
  odds snapshot, forecast, and settled-bet tables (PA identity = game_pk +
  at_bat_number + batter; start identity = game_pk + pitcher + side).
- Counts by season: pitches, PAs, starts, games, pitchers, batters.
- Eligibility waterfall and missingness/availability by feature family.
- Point-in-time feature registry: source, cutoff, lag, grain, support count
  (n_pitches/n_PAs behind every aggregate), null policy, leakage risk.
- Join cardinality and anti-fanout tests (declarative, at declared grains).
- Purpose: unlocks rational model choice and effective-sample-size honesty
  (pitch rows cluster within PAs/games/pitchers/dates).
- Acceptance: data card reproduces from one command; counts reconcile to raw
  sources; known duplicate grains documented.
- Complexity: M. Depends on: current sealed-pipeline conventions.

## P1 — Challenger/evaluation harness

- Expanding-window chronological folds with separate calibration windows.
- Identical-row paired comparisons across all candidates.
- Metrics: PA log loss/Brier; BF and K count RPS/log loss; xK MAE/RMSE/bias.
- Calibration intercept/slope, reliability curves, PIT, interval coverage.
- Paired block bootstrap (declared unit: slate date; pitcher-cluster
  sensitivity) for evaluation uncertainty.
- Slice reporting (hand, month, cold-start, support decile, BF decile, line,
  lineup status) with minimum-practical-improvement gates.
- Immutable manifests for code, data, features, models, predictions, scores.
- Purpose: one command = identical folds/predictions/scores/manifests for
  every candidate. Acceptance: harness reproduces the frozen I1_ref and
  reconstructed-BF baselines bit-for-bit on the sealed protocol.
- Complexity: L. Depends on: P0.

## P2 — Baselines and statistical challengers (in order)

1. League and empirical-Bayes pitcher/batter baselines (learned shrinkage
   inside training folds — tests whether fixed w=150 is appropriate).
2. Current fixed log5 baseline (retained).
3. Generalized-log5 logistic challenger (learned pitcher/batter/league
   coefficients; registered matchup interactions).
4. Hierarchical logistic PA challenger (partial pooling by pitcher, batter,
   handedness, season, support).
5. LightGBM PA classifier (native numerical missingness; must match
   train/serve missing-value semantics).
6. CatBoost PA challenger (categorical players/teams/contexts).
7. Calibrated ensemble only if component errors are complementary.
- BF lane stays separate; BF challengers compared on count RPS/log loss.
- No deep/sequence model until these are exhausted.
- Promotion gate: paired count-RPS improvement, Holm within the declared
  family, stable across temporal folds; retain incumbent otherwise.
- Complexity: L. Depends on: P1.

## P3 — Pitch/arsenal features

- Preserve support: every aggregate carries n_pitches and recency weights.
- Families (registered, not swept): usage; shape (velocity, IVB/HB, VAA,
  extension, release); location (edge/heart/waste/chase); whiff/CSW/chase;
  count-conditioned usage; TTO; consistency; in-start degradation;
  pitch-pair separation/tunneling.
- Mechanistic interactions only as registered families (hand x hand;
  usage x batter weakness; velocity x VAA; zone x chase profile).
- Complexity: L. Depends on: P2 ladder running.

## P4 — Plus metrics and visualization (post-seal, read-only)

- Pitcher K+, Matchup K+, Lineup K-Susceptibility+, Lineup Exposure Index
  (100 x E[K_B]/E[K_A]), Workload+, Projection K+ — each with denominator,
  reference population, era, handedness scope, cutoff, shrinkage, support,
  direction label, and uncertainty interval.
- Charts from keyed saved artifacts only: BF bars (xTBF, median, intervals),
  A/B K bars with actual-line probabilities, joint BF-K heatmap, calibration
  reliability by line/bin, fan charts. Overflow bucket always labeled "23+";
  xK from uncollapsed support with the collapsed lower bound labeled.
- Complexity: M. Depends on: P1 + sealed artifacts.

## P5 — Market and risk layer (last)

- Timestamped open/close odds from named books; frozen de-vig method;
  availability, limits, rejection records; push/void/SP rules.
- Shadow bets with frozen conservative-edge thresholds (posterior-lower-
  quantile probabilities, not raw points).
- Fractional Kelly with uncertainty haircut, exposure caps, correlated-bet
  groups (no same-event independence), drawdown/ruin stress tests.
- Metrics: CLV, net EV, turnover ROI (stake-weighted; pushes in settled
  turnover, voids excluded but counted), bankroll return kept separate,
  Sharpe/Calmar, risk of ruin, capacity.
- Complexity: L. Depends on: P2 gate PASS + odds infrastructure.

## Explicit non-goals

- No current forecast regeneration; no outcome access before seal.
- No unregistered feature sweep; no tuning on the evaluation period.
- No profitability claim from the 11 confirmed-lineup pilot.
- Monte Carlo only for parameter uncertainty, substitutions, correlated
  wagers, and bankroll stress — never where the finite mixture is exact.
