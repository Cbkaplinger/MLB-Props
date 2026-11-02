# Workload personalization experiment card

## ID

`workload_personalization_w0v1`

## Question

Holding strikeout skill estimates, lineup reconstruction, aggregation,
and assessment population fixed, does pitcher-specific workload
forecasting improve the final K-count distribution beyond a pooled
league BF control that uses the same history policy, cutoff rule,
smoothing, support, and tail conventions?

## Status

DRAFT — not executed. Requires one authorized run implementing the
shared fixed-recipe fit/inference step (to generate keyed PA
probabilities and both BF variant vectors) and the cohort restriction.
No new model family, feature family, taxonomy expansion, or calibration.

## Registered cohort

2,509 starts (hash `f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7`),
from the count_agg_eval_v1 block_2025H1 eligible population.

## Arms

| Component | W0 (pooled control) | W1 (existing workload) | Shared? |
|---|---|---|---|
| BF probability source | Pooled empirical BF37 from ALL eligible starter outings strictly before the same forecast cutoff, add-one smoothing over 37 categories, registered tail conversion (`bf_pmf_from_37`, cap 60, geometric tail) | Registered bf-workload-v1 pitcher-specific PMFs (unchanged; >=10 prior starts else pooled league fallback) | — |
| BF history window | `2023-01-01 ≤ historical game_date < forecast cutoff` for both arms, using the same validated starter-outing population | Same | ✓ |
| Starter/opener definition | **First pitcher of record per (game_pk, side), opener-inclusive, no starter filter** — matching W1's registered construction (bf-workload-v1 report_v2.json) | Same | ✓ |
| Short-outing inclusion | Included (same as W1's underlying counts) | Same | ✓ |
| Smoothing | Add-one over 37 categories | Same | ✓ |
| Support / overflow | 37 categories, overflow bucket 36, registered tail conversion | Same | ✓ |
| PA probabilities | Identical keyed values from a shared fixed-recipe fit/inference step (see below) | Same | ✓ |
| K aggregation | `ad.start_count_pmfs(p9, p9, bf37)` — identical registered implementation | Same | ✓ |
| Assessment cohort | Registered 2,509 starts | Same | ✓ |
| Primary metric | Paired count-RPS difference | Same | ✓ |

**History-policy symmetry:** W0 and W1 use the SAME expanding
strictly-prior completed-starter-outing history:
`2023-01-01 ≤ historical game_date < forecast cutoff` for both arms,
using the same validated starter-outing population (first pitcher of
record per game-side, opener-inclusive). Earlier warm-up information
must not silently become additional W0 BF observations. At each
forecast cutoff, W0 pools across all eligible starter outings in the
history; W1 selects the pitcher's own starts.

**The ONLY difference:** whether the per-start BF37 probability vector
is pitcher-specific (W1) or pooled across the training population (W0).

## Shared PA model (fit/inference step)

The keyed PA probabilities from the accepted baseline run were
constructed in-memory but NOT serialized as a standalone artifact.
Before the workload comparison can run, one shared fixed-recipe
fit/inference step must:

1. Fit the multinomial logistic model on the declared training rows
   (same features, same coefficients recipe, same class order).
2. Generate keyed PA probabilities for the registered assessment starts.
3. Serialize: fitted coefficients, scaler parameters, feature order,
   class order, and the keyed (game_pk, side, pitcher, slot, batter)
   probability table.

This is ONE shared step producing a single keyed forecast table
consumed by both W0 and W1. It is not a workload-specific step; it is
the PA-model inference that both workload arms need as a fixed input.

A reconstruction check MUST verify that W1 (using the registered
bf-workload-v1 BF forecasts) reproduces the accepted baseline's
per-start count-RPS within a predeclared numerical tolerance when all
inputs and settings match. The proposed tolerance is max per-start
absolute RPS difference ≤ 1e-12 (the same tolerance used in the
Stage-A reconciliation). Any mismatch is diagnosed before proceeding;
it is not tuned away.

## Direct BF diagnostics

Both arms' BF forecasts are scored against observed BF totals per start
(where an approved observed-BF source is available):

| Diagnostic | Definition |
|---|---|
| BF distribution score | Discrete RPS over the 37-category BF support, using the correctly bucketed observed BF (the observed BF count maps to its category index; the overflow bucket absorbs BF ≥ 37 but is NOT scored as exactly 37 BF — the full extended distribution is used for means and interval calculations) |
| Point MAE | (1/n) Σᵢ |E[Nᵢ] − Nᵢ^obs| where E[Nᵢ] is computed from the declared extended distribution (not the truncated 37-category representation) |
| Mean BF error | Signed difference: predicted E[BF] − observed BF, using the extended distribution's mean |
| Interval coverage | % of starts where observed BF falls within the predicted 50% and 90% central intervals of the extended BF distribution |

Subgroup diagnostics (early-hook, deep-start) are omitted from v1;
they require preregistered definitions with unit justification before
inclusion.

## Primary metric and acceptance criteria

Δ = RPS(W1) − RPS(W0) per start on identical assessment keys, scored
with the registered slate-date bootstrap (2,000 draws, seed 20261001).

Three separate conclusions are drawn from the result:

**Statistical direction:**
- Entire CI below zero: pitcher-specific workload improves count
  forecasts (statistically established under the registered resampling
  procedure).
- Entire CI above zero: pooled control outperforms personalization.
- CI overlapping zero: inconclusive; do not treat as equivalence.

**Practical magnitude:** the proposed engineering threshold |Δ| < 0.005
count-RPS marks a difference too small to justify the complexity of
personalization, regardless of statistical direction. This threshold is
an engineering decision, not a demonstrated minimum detectable effect;
its rationale (approximating the overhead cost of maintaining
per-pitcher workload state) should be stated before scoring.

**Promotion decision:** both conditions must hold — statistical
direction established AND practical magnitude above the declared
threshold — for the workload arm to be retained in the pipeline.

## Outputs (planned)

| File | Content |
|---|---|
| workload_comparison_report.json | Both arms' mean count-RPS, paired Δ + CI, BF diagnostics, coverage accounting |
| workload_per_start_v1.parquet | game_pk, side, pitcher, realized_k, realized_bf, rps_w0_pooled, rps_w1_pitcher, bf_mean_err_w0, bf_mean_err_w1, rps_diff |
| keyed_pa_probabilities.parquet | (game_pk, side, pitcher, slot, batter, class-label probability vector) — from the shared PA model inference |
| bf_pmf_w0_pooled.parquet | per-start pooled BF37 probability distribution (37 categories) |
| bf_pmf_w1_registered.parquet | per-start registered bf-workload-v1 BF37 probability distribution (37 categories) |
| k_pmf_w0.parquet | W0 per-start K PMF (24 buckets) |
| k_pmf_w1.parquet | W1 per-start K PMF (24 buckets) |
| model_artifact.json | fitted coefficients, scaler, feature order, class order, settings |
| receipt_initial.json | immutable; code identities, expected input hashes, config |
| receipt_final.json | receipt chain + acceptance + output hashes |

BF37 probability files contain BF probabilities (37 categories);
K-PMF files contain K probabilities (24 buckets). These are distinct
distributions over different supports; neither is a re-binned version
of the other.

## MLflow logging

Artifact-only logging through the shared `track_and_verify.py` wrapper
after the run completes. Label: "Logged from accepted saved artifacts;
original scientific execution occurred earlier." The MLflow run records
computational identities, data/cohort hashes, metric denominators, and
links to diagnostics. Raw private datasets are not uploaded.

## Limitations

- Development evidence only; not a production or betting claim.
- Does not test the frozen incumbent (binary checkpoint).
- Does not test calibration, new features, or taxonomy expansion.
- The BF-vs-outcome relationship is observational; no causal claim
  about removal dynamics or bullpen management.
- Both arms share the same smoothing and support conventions; the
  comparison isolates personalization, not smoothing policy.
- Neither arm is restricted to the coefficient-training window; both
  see the same eligible pre-cutoff history, so the comparison does not
  conflate recency with personalization.
- The fitted coefficients from the shared PA model inference are
  serialized for reproducibility; they are NOT re-tuned or recalibrated
  by this experiment.
