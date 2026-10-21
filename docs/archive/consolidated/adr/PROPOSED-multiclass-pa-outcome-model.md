# PROPOSED ADR — Multiclass plate-appearance outcome model

**Status:** PROPOSED (architect direction, 2026-10-21). Owner direction: the
project is moving toward a model that predicts every outcome of a plate
appearance. This ADR sequences that work. It does not override frozen
registrations, pins, hashes, or pre-registered protocols.

## Context

The research PA lane is binary today: L3 (ridge logistic, K versus not-K) is the
DEVELOPMENT baseline. The count layer aggregates PA strikeout probabilities
over a BF distribution; Question A showed exact Poisson-binomial aggregation
improves count-RPS by a small, statistically resolved amount on the 4,823
development starts. Two open limits remain: workload is exogenous to
performance, and every non-strikeout market (walks, hits, outs, runs) is out
of reach.

## Decision

Target a single multinomial model over PA outcomes: K, BB, HBP, 1B, 2B, 3B,
HR, ball-in-play out (final taxonomy fixed in the M0 card). Strikeout
probability becomes one marginal of a coherent distribution. The model is a
research lane; production is unchanged until a separate promotion gate.

## Stages (one card each; no stage starts before the previous gate result)

| Stage | Question | Gate |
| --- | --- | --- |
| M0 | Does a softmax version of L3 (same features, same fit/eval blocks) match L3 on the K marginal and beat league-constant and log5 baselines on multiclass log loss? | K-vs-not-K log loss non-inferior to L3 at a pre-declared margin (date-clustered, paired); multiclass log loss better than the baselines; per-class reliability reported, rare classes pooled |
| M1 | Does the K head, aggregated with the exact Poisson-binomial machinery, preserve count-RPS against the Question A result? | Count-RPS non-inferior to the Question A challenger on the 4,823 dev starts |
| M2 | Do the non-K heads support a second market (outs, walks, hits) with market data? | Separate card per market, own price-layer evaluation |
| M3 | Can PA outcomes feed a game-state process (baserunners, runs, pitch count) so exit becomes endogenous? | This is the structural answer to C-B2 in the Question B card; its own pre-registration |
| M4 | Does the 2015-2022 history extension help rare classes (3B, HBP, HR)? | Separate registered evaluation; it changes cumulative inputs for all players |

## Why this order

- M0 reuses the existing PA table, folds, and bootstrap; it needs no new data.
- The K marginal must not regress: the binary model is the incumbent for the
  market the project actually bets.
- Rare classes have thin 2023 training counts, so calibration and variance
  are the main M0 risk; M4 exists because of it.
- Multiclass is an enabler, not a proven accuracy gain. Its benefit for K
  specifically is unmeasured until M0 reports.

## Non-goals

No production change, no confirmation access, no betting-layer claim, no
market work before M2, no new feature families inside M0.

## Statistics

The statistics rules in `docs/AGENTS_ROLES.md` (2026-10-21) apply. Primary
endpoints for M0 are two (K-marginal non-inferiority, multiclass log loss),
with Holm adjustment at m=2.
