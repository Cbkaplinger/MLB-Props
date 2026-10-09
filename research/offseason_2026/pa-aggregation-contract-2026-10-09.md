# PA aggregation milestone contract (2026-10-09) — A/B/C arms, frozen

> **Status: FROZEN after gates B and C passed.** One canonical scored run
> authorized on top of this contract. Log5 fixed as the PA reference; no
> classifier fitting/tuning; no workload retraining; I3b untouched.

## Question

Does using batter-specific PA strikeout probabilities improve the pitcher's
full strikeout-count distribution versus one average log5 probability?

## Gates already passed (receipts)

- **B (workload compatibility)**: `pa-workload-lineup-check-20261009_164651`
  — 4,446/4,446 canonical kcount-integration eval starts matched to
  pa_completed_v1; 4,442 diff = 0; the 4 nonzero diffs are all ≤1 and
  reason-coded by the known row classes (truncated/mixed/incomplete/
  baserunning/mid-PA); K diff = 0 on 4,445/4,446. The I3b workload target
  and the v1 opportunity concept are compatible; every BF support value n
  indexes a v1 completed-PA sequence of length n. No ratio correction;
  I3b unchanged.
- **C (lineup availability)**: mode-3 ORACLE realized initial lineups
  (`batter_games.is_initial_lineup` + `lineup_slot`, no pregame timestamp
  archive 2023-2025) — 4,446/4,446 starts have a full 9-slot ordered
  lineup. **Arms B/C are therefore ORACLE-LINEUP DIAGNOSTICS;
  non-deployable; no deployment claims.**

## Arms (identical rows, identical BF PMFs, identical pa_completed_v1 priors)

- **A — canonical I3b**: existing scalar log5 p* + existing BF hazard PMF +
  binomial mixture (existing kcount machinery, reproduced on the eval rows).
- **B — matchup-mean binomial**: for each BF support n, take the first n
  opportunities of the cycled 9-slot ordered lineup; p_bar_n = mean(p_i);
  Binomial(n, p_bar_n); mix over the identical BF PMF.
- **C — matchup Poisson-binomial**: same p_1..p_n sequence and BF PMF;
  PB PMF via exact DP (P(K=k), support 0..n); mix over BF.

p_i = shrunk log5 (w=150, per-origin league rate, pa_completed_v1 priors)
for the forecast pitcher vs the lineup batter at opportunity i; identical
formulas to the corrected PA lane arm A; same pitcher probability for all
i (no TTO/fatigue term — declared simplification); repeated encounters
retain the same probability. Opposing STARTER's identity never enters the
sequence (only the batting order does). Cycled order for n > 9; overflow
BF bucket (>36) uses a representative n=37 sequence (declared).

## Comparisons and multiplicity

Family of 3 primary paired count-RPS comparisons: {B−A, C−B, C−A},
slate-date clustered bootstrap (2000, seed 20261001), Holm at 0.05.
Expected mechanism check (mechanical): Var_PB <= Var_Binom(n, p_bar) with
equality iff all p_i equal; C−B isolates shape at equal conditional mean
E[K|n] = sum(p_i).

## Metrics

Primary: paired count-RPS (canonical I3b RPS convention, support 0..24 with
>=23 absorbing bucket, matching the kcount-integration prereg). Secondary:
count log score (floor 1e-12), xK MAE/bias, milestone Brier
(K>=6/8/9/10/12), PIT diagnostics, coverage/floor-hits, slices (short
outings <9 PA, debut, sparse history, September). All evidence
developmental; oracle-lineup labeling on every B/C claim.

## Mechanical tests (required green before scoring)

PB == Binomial when all p_i equal (1e-9); every conditional PMF and
mixture sums to 1; B and C have equal E[K|n] for every n; BF mixing
preserves mass; opposing-starter invariance (changing the opposing
STARTER cannot change this pitcher's sequence); outcome-mutation and
future-append invariance; preflight ledger gates (unique PA identity,
snapshot uniqueness, pitcher ownership, cardinality) run in the actual
runner; no negative probabilities or silent truncation.

## Files

Own: this contract, `run_pa_aggregation_abc.py`, `tests/test_pa_aggregation_abc.py`,
backlog receipt. Reuse (read-only): kcount_combiner, kcount-integration
canonical artifacts (BF PMFs, eval rows), pa_lgbm_scaffold priors,
provenance machinery. Preserve failed attempts; stop on correctness
problems; no commit after execution without authorization.

## Amendment 1 (pre-scoring) — canonical support + frozen decision rule

1. **Support convention (copied, not reinterpreted)**: the scored count
   vector is `combine_count(bf_pmf_ext, p_bar, k_max=24)` from
   `kcount_combiner.py` — exact categories 0..22 plus a final bucket
   absorbing K >= 23 (length 24); BF input = the EXTENDED 1..60 vector
   (`bf_pmf_from_37` applied to the stored 37-vector); RPS = summed
   `count_rps`; log score floor 1e-12.
2. **Equal-mean assertion on UNCOLLAPSED conditionals**: for every BF
   support n, B's conditional (Binomial(n, p_bar_n)) and C's conditional
   (PB over p_1..p_n) are compared on the 0..n support BEFORE any
   absorbing-tail transformation; E[K|n] must agree within 1e-9.
3. **Frozen decision rule (declared before scores exist)**:
   - B−A count-RPS = lineup-derived conditional-mean effect;
   - C−B count-RPS = unequal-probability distribution-shape effect;
   - C−A count-RPS = total oracle-lineup aggregation effect;
   - pass = 95% CI entirely below 0 after Holm within the frozen family
     of exactly these 3 comparisons; no comparisons added or removed after
     seeing results; no promotion: ORACLE-LINEUP RESULTS CANNOT AUTHORIZE
     PRODUCTION PROMOTION.
4. **C−B must not change pre-collapse E[K|n]** — if it does, that is an
   implementation error and the run is invalidated.
