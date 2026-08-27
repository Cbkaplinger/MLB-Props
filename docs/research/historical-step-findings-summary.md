# Historical Step Findings Summary (Steps 1, 3, 4, 5, 8, 9)

This file consolidates legacy step-level research notes into one compact
reference. It preserves key decisions and quantitative outcomes while reducing
documentation sprawl.

> This is a historical process record. For current winner metrics and deployment
> champions, use `docs/reference/governance_metric_stack.md`.

## Scope and status

- Consolidated docs: Step 1, 3, 4, 5 (PA-weight, binomial, beta-binomial), 8, 9.
- Still canonical for current freeze: `step11_discipline_registry_freeze.md`.
- Companion freeze retained: `step10_p1_registry_freeze.md`.

## Decision timeline

| Step | Decision kept | Quant signal retained |
| --- | --- | --- |
| 1 | Dual registry policy kept: tree registry + Ridge VIF companion. | Legacy freeze lineage retained; Ridge companion 73 features. |
| 3 | Opponent lineup family confirmed as load-bearing. | LightGBM `drop_lineup` mean delta MAE about `+0.00254`; Ridge about `+0.00231`. |
| 4 | Mean-window thinning logic accepted for tree backbone. | `P3/P5` window policy beat full `P3/P5/P10` in the targeted screen. |
| 5A | PA weighting closed as non-promoted diagnostic. | LightGBM unweighted MAE about `0.0789` vs PA-weighted `0.0793`. |
| 5B | Binomial GLM challenger not promoted. | Binomial GLM MAE about `0.0878` vs LightGBM `0.0789`; NLL also weaker. |
| 5C | Beta-binomial challenger not promoted. | Under LightGBM means, kappa pushed to binomial limit; no deployment benefit. |
| 8 | No additional family drop from the 185 freeze under strict both-fold rule. | Greedy prune dropped zero families; bake-off unchanged. |
| 9 | Per-metric window sweep informed Step 10 P1 swap, but did not justify broad re-freeze alone. | Rates-only thin near noise-scale; targeted P1 swap fed Step 10/11 lineage. |

## What changed in production because of these steps

1. The large contraction happened in historical freeze lineage:
   `248 -> 185 -> 180 -> 184`.
2. Step 11 added four lineup-discipline features on top of the 180 spine.
3. Step 5 challengers remained historical diagnostics and were not promoted.
4. Current execution stack uses sparse-set governance + decision-lane controls
   (isotonic calibration, parity lock, execution/research gate split), while
   preserving this lineage for auditability.

## Reproduce historical evidence

- Step 5 beta-binomial runner:
  `models/Strikeout-Model/research/beta_binomial_nested_compare.py`
- Step 9 metric/window sweep:
  `models/Strikeout-Model/research/step9_metric_window_select.py`
- Step 8 keep/drop runner:
  `models/Strikeout-Model/research/step8_keep_drop.py`

These runners and artifact outputs remain available for auditability.
