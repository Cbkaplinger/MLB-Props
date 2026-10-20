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
