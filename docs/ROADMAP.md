# ROADMAP — research cycle to 2026-12-31

**Status:** architect-authored 2026-10-21. Supersedes `docs/adr/PROPOSED-prd-research-shipping-cycle.md`
(its March-2027 deadline was an unconfirmed assumption; the owner's scope is **end of 2026**).
Frozen registrations, pins, hashes, and pre-registered protocols outrank this file.

## Finish line (2026-12-31)

1. M0 verdict (multiclass PA model: pass, fail, or stop) with valid provenance.
2. 2027 production policy written down: frozen stack plus the cold-start handling for pitchers
   with no history (research default: league-rate prior, flagged `cold_start_league_prior`).
3. One coherent documentation set (story, state, roadmap, decisions) replacing the short-file sprawl.
4. Project in maintenance mode so the owner can start other projects.

## Where we are (2026-10-21)

| Item | Result |
| --- | --- |
| Batter-history challenger (R60/m30) | REJECTED. Paired log-loss delta +0.00062, CI excludes zero. Baseline retained. Scope: this recipe only. |
| Question A (exact Poisson-binomial) | Count-RPS -0.000333 (CI -0.000419 to -0.000245) on 4,823 dev starts. An earlier unreceipted exploratory decision-flip calculation is unverified (reported: 1 flip in 19,292 start-lines; max abs change in P(K>=line) under 0.004). No accepted decision-flip execution result is established by that calculation. The registered diagnostic requires its own reviewed execution evidence. |
| Question B (workload dependence) | Design card only. On hold behind M0. |
| Abstentions (59 starts) | Handle with the league-rate prior, reported separately from starts with history. |
| Production | Unchanged. |

Pattern across three experiments: effects at the count layer sit at the noise floor. Further
count-layer micro-experiments need a predicted effect larger than 0.01 in P(K>=line) before they are
worth a card.

## Plan

| ID | Experiment | Owner | Target | Gate | If pass | If fail |
| --- | --- | --- | --- | --- | --- | --- |
| M0 | Softmax version of L3 on the same features and folds | Chat 1 builds, Chat 2 reviews | Result by 2026-11-14 | K-vs-not-K log loss non-inferior to L3 at a declared margin; multiclass log loss beats league-constant and log5 baselines; per-class reliability reported | Go to M1 | Freeze binary model; stop multiclass; record |
| M1 | K head through the count layer; count-RPS vs Question A challenger | Chat 1 | 2026-12-05 | Non-inferior count-RPS | Record; M2 stays 2027 | Record; no change |
| P1 | 2027 production policy note (frozen stack, cold-start handling, flags) | Architect drafts, owner approves | 2026-11-30 | Owner approval | Register | Revise |
| D1 | Documentation consolidation (see below) | Chat 3 | 2026-11-21 | Link check green, CI green, no frozen path touched | Merge | Revert cluster |
| F1 | Final report and handoff | Architect | 2026-12-20 | All above closed | Maintenance mode | Carry open items to a dated list |

Buffer: 2026-12-21 to 2026-12-31. Nothing new starts after 2026-12-05.

## Deferred (not 2026)

- M2 other markets from non-K heads (outs, walks, hits); needs market data and its own cards.
- M3 game-state process so pitcher exit is endogenous (structural answer to C-B2).
- M4 history extension toward 2015 (changes cumulative inputs for all players).
- Question B C-B1 (exposure-index heterogeneity): first check what it adds beyond the trip dummies and
  starter_pa_index already in L3; only then decide whether it earns a card.
- Profit replay of any challenger (prices, sizing); marcel age curve; external projection floors.

## Pivot rules

1. A card is run once. A stop condition that triggers closes the question; no rescue variants.
2. A failed gate ends that stage and moves the calendar forward. Nothing is retried to fit the calendar.
3. If M0 has not reported by 2026-11-21, stop and freeze the binary model.
4. The confirmation block is not spent on marginal effects.

## Card checklist (every new card)

One primary contrast and sign convention; effect-size budget computed from persisted artifacts
before the card is written; practical-significance threshold; non-inferiority margin if the claim is
"no worse"; stop condition; committed run script and entry point (no uncommitted wrappers);
consumed versus context inputs; a card of two pages or less.
