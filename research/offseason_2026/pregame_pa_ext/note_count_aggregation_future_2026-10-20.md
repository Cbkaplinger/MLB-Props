# Future count-aggregation work - specification note only (2026-10-20)

SCOPE: this note QUEUES two distinct future questions and deliberately
implements NEITHER. No fitting, no predictions, no code changes to the
frozen aggregation machinery. Recorded so the distinction below survives
the batter-history diagnostic.

## Question A - unequal-batter-probability aggregation (construction)

The registered count-PMF construction (adapter.start_count_pmfs ->
cycled_cond_mean) summarizes the nine per-PA slot probabilities as a
CYCLED PREFIX MEAN: pbar_n = mean of the projected nine cycled to n,
n = 1..cap-60. That is an equal-weight treatment of the nine SLOTS: the
mixture over the BF workload implicitly assumes the batter-face sequence
is exchangeable across slots (every PA draws pbar_n from the same cycled
mean regardless of WHICH batters occupy the top of the order twice). The
queued question: does an aggregation that accounts for unequal per-batter
probabilities (e.g., sampling-position-aware pbar, or a weighted mixture
over ordered slots) change the count distributions? Any test must keep
the BF input, the K-rate model, and the evaluation population fixed and
change ONLY the aggregation rule - one registered challenger, same
discipline as the batter-history card (single primary score, no search).

## Question B - workload/performance dependence (coupling)

A different, structural question: the current mixture treats P(N=n) (the
BF workload) and the per-PA K probability p as INDEPENDENT. In reality
both are driven by the same in-game pitching state (a pitcher struggling
or dealing changes both how long he stays in and the per-PA rates), and
pitcher removal is endogenous - see the times-through-the-order selection
literature. Treating workload and K ability as independent can distort
the count tails (k>=18 buckets) even when PA-level probabilities are
well calibrated. The queued test: a dependent formulation (e.g., one
latent game-state variable driving both N and the per-PA rate) compared
against the existing independent aggregation on registered dev folds.

## Why they must not be conflated

- A is an AGGREGATION-SCHEME choice (how the nine probabilities map into
  the count PMF given N) - fixable inside the current architecture.
- B is a DEPENDENCE-MODEL change (whether N and the K process share a
  state) - it changes the generative structure and needs its own
  pre-registered design, evaluation table, and candidate budget.
- Running both changes at once would make any count-distribution
  improvement unattributable (same discipline as the batter-history
  card's isolation rule).

Sequencing: neither starts before the batter-history diagnostic closes;
each requires its own card and owner approval. The registered metric
vocabulary (count-RPS primary, milestone Briers descriptive) carries
over unchanged to both.

## Initial synthetic separation tests (2026-10-20)

Delivered: tests/test_count_aggregation_separation.py (9 tests,
synthetic-only, frozen aggregation code UNCHANGED) with a test-local
exact Poisson-Binomial oracle. Findings - the assumptions the current
code ACTUALLY makes:

1. **Homogenization (Question A):** given N=n, the n PAs are modeled
   i.i.d. Binomial(k; n, pbar_n) with pbar_n = mean of the first n slot
   probabilities. Exact at n=1 and under lineup homogeneity; for
   heterogeneous prefixes the averaged binomial OVERSTATES both tail
   masses and understates the middle. SOFTENED (2026-10-20): the analytic
   tail-gap formula ((p1-p2)/2)^2 each is PROVEN FOR n=2 ONLY; for n>=3
   the overstatement is demonstrated EMPIRICALLY by the separation tests
   (Var(current) > Var(exact) (Jensen) for every heterogeneous n=2..9
   tested; measured max per-PMF gap on a realistic spread: < 0.05).
2. **Order sensitivity (implicit, Question A):** pbar_n is order-aware
   through the cycling - the same nine batters in different batting
   orders produce different PMFs below n=9 and identical PMFs at n=9.
   Implicit assumption: batters faced follow batting order from slot 1.
3. **Linearity in the workload (Question B).** SOFTENED (2026-10-20):
   the count PMF is LINEAR in the BF distribution (PMF(a*BF1+(1-a)*BF2) =
   a*PMF(BF1)+(1-a)*PMF(BF2)) - this linearity is a STRUCTURAL
   RESTRICTION of the mixture form (what the model CAN express), NOT a
   demonstration or proof that the workload is statistically independent
   of performance; the dependence question remains open.
4. **Within-n correlation is outside the model class (Question B):** a
   within-game correlated joint outcome (0.40/0.20/0.40 on K=0/1/2 at
   n=2) differs from ANY i.i.d.-given-n answer (>0.1 gap); the current
   machinery returns exactly the i.i.d. answer - no parameter expresses
   within-n correlation.
5. **Endogenous workload coupling is structurally absent (Question B):**
   pbar_n is constrained to prefix means of the nine slot probabilities,
   so a performance-exposure decline (e.g., 0.3 to 0.1 in long-outing
   states with slot probs all 0.3) cannot be represented - the queued
   dependent-formulation question would have to change this constraint,
   not merely a point estimate.

These findings bound the two questions separately; neither has a
remedy implemented, and each needs its own registered card.
