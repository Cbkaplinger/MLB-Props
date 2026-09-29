# Count-metric helpers (experiment-ready spec, no code — audit §§X, AD)

Location when built: workspace `experiments/` (never `src/` until promotion by
extraction PR). All helpers consume `(y, distribution)` with frozen inputs only;
no fitting inside metric code.

1. **Count NLL**: `−mean(log P(K=k))` per start, reported overall + per-line
   cohort + TBF tails (<15 / ≥28). Inputs: realized K + per-start pmf on 0…maxK
   from the distribution arm. Failure: zero-mass at realized k → clip `1e-12`
   with counter (clipping hides model failure; report clip rate).
2. **RPS / discrete CRPS**: `Σ_t (CDF_pred(t) − 1{k≤t})²` over t = 0…maxK.
   Proper for counts; comparable across D0–D4. Report mean + per-xK-decile.
3. **Randomized PIT**: `u = CDF(k−1) + v·pmf(k)`, `v ∼ Uniform(0,1)` with a
   pinned seed from the split manifest; uniformity test (KS/Chisq) + histogram.
   Discrete PIT without randomization is invalid — never use raw PIT.
4. **Coverage**: central-interval hit rates at stated levels (P50/P80) +
   tail rates below 2.5 / above 9.5. Report observed vs nominal with cluster CIs.
5. **Per-line Brier/logloss + ECE/bias**: reuse canonical
   `prob_calibration.scoring_metrics` + `expected_calibration_error` (never fork);
   same-subset rule; WS1c-vs-raw pair always shown.
6. **Push documentation**: K props are half-lines (no push). Any whole-number
   rung prices push-not-loss; map before scoring.

Kill rule: a distribution arm survives only on held-out count-NLL + per-line
Brier/logloss gain vs D0 (pre-reg delta at build; precedent `<0.0005` kills).
xK-MAE never decides. Seeds from split manifest; mass-sum + bounds asserts on
every output.
