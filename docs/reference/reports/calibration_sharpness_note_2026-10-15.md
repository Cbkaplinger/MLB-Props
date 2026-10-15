# Research note — calibration vs sharpness for BF/count diagnostics (2026-10-15, Chat 3)

Bounded note, assigned by coordination 2026-10-15. Framework source: Gneiting &
Raftery (2007), "Strictly Proper Scoring Rules, Prediction, and Estimation,"
JASA 102(4):359-378 (also the 2007 JRSS-B version cited by coordination).
Application target: the BF/count diagnostic and market-eval reporting this
program already uses. **No new experiment; no data touched.**

## The two axes, stated plainly

Under a strictly proper scoring rule, a probabilistic forecast is rewarded for
two separate qualities:

- **Calibration (consistency):** averaged over many cases, events declared to
  have probability p happen about a fraction p of the time. Gneiting-Raftery
  call the achievable ideal "compatibility" with the true conditional
  distribution; the empirical check is reliability.
- **Sharpness (concentration):** how tight the predictive distribution is. The
  principle: **maximize sharpness subject to calibration.**

They are not interchangeable and a model cannot trade one for the other in a
score that is proper: any gain from extra concentration is only real if
calibration is preserved; concentration without calibration makes a proper
score **worse** (overconfidence is penalized).

## What this program already does right

- Count outcomes (K per start) are scored with **RPS / Brier / log loss on
  ordinal 24-bucket PMFs** — RPS is strictly proper for ordinal targets, Brier
  proper for binary/multiclass reformulations. Primary/secondary metric choices
  in the frozen contracts are consistent with properness.
- Comparisons are **paired slate-date bootstraps with Holm correction** over a
  preregistered contrast family. This controls the *comparison* claim; it does
  not by itself characterize either candidate's calibration.
- Diagnostic slices (short outings, September, milestone Brier) disclose where
  a challenger helps/hurts.

## What the framework adds to future BF/count diagnostic reports

1. **Report calibration and sharpness as separate columns, never only the
   proper score.** Concretely, per arm per block:
   - reliability: mean predicted P(K in bucket) vs realized frequency across
     buckets (or a PIT histogram for the full count PMF);
   - sharpness: mean predictive standard deviation of the K distribution (or
     mean 90% interval width);
   - the proper score (RPS) as the headline, with the two columns beside it.
2. **Use the Murphy decomposition of Brier** (reliability - resolution +
   uncertainty) when a Brier number moves: it distinguishes "better calibrated,"
   "better resolution," and "different base rate mix" — the last one being the
   row-population trap this program has hit before (join/cardinality incidents).
3. **Interpret PMF-divergence attributions on both axes.** The 2026-10-14
   pilot-diagnostic attribution (max abs PMF diff 0.2766/0.2756) is a
   sharpness-relevant fact (PMFs differ in concentration); whether either PMF is
   *better* depends on the calibration axis, which that diagnostic did not and
   could not measure (synthetic labels). Reports should say which axis each
   number speaks to.
4. **Guard the estimand when comparing arms with different spread.** A more
   concentrated arm with equal mean can win RPS while being miscalibrated in
   the tails; milestone/tail slices (already in use) are the right check.
   Keep them in the preregistered family, not post-hoc additions.
5. **Equivalence language stays as-is.** Crossing-zero CIs mean "no demonstrated
   difference," per the standing owner correction (2026-10-09). The
   calibration/sharpness split does not change that reading.

## One-line summary for report authors

A proper score is the headline; beside it, one calibration column (reliability
or PIT) and one sharpness column (predictive spread), per arm per block — so a
win is attributable to concentration only when calibration held.

## References

- Gneiting, T. & Raftery, A. E. (2007). Strictly proper scoring rules,
  prediction, and estimation. JASA 102(4), 359-378.
- Murphy, A. H. (1973). A new vector partition of the probability score.
  J. Applied Meteorology 12, 595-600 (Brier decomposition used in item 2).
- Program conventions this note must not override:
  `docs/EXECUTION_BACKLOG.md` (master), frozen contracts under
  `research/offseason_2026/specs/`, `docs/reference/golden_metrics.md`
  (cite, do not recompute).
