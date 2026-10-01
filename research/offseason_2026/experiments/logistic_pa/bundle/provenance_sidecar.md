# L3 Bundle Provenance Sidecar (Phase 8.7, 2026-09-30)

Companion to `model_bundle.json` / `model_card.json`. This file may be extended; the
bundle and card it describes are immutable and were NOT modified.

- **Intercept value location:** `model_bundle.json → intercept = -0.33305196362724293`.
- **Intercept provenance: RECOVERED, not serialized at fit time.** Recovered from stored
  2024 L3 predictions plus rebuilt 2024 features (build procedure:
  `bundle/build_bundle.py`): the intercept is the unique constant making
  `sigmoid(intercept + eta_no_intercept)` match stored predictions; constancy across
  rows 1.05e-15 (max spread). Recovery is mathematically unique given fixed features
  and coefficients (monotone link, one scalar degree of freedom).
- **Reproduction:** max |Δp| vs stored L3 predictions = 2.2e-16 (machine epsilon) over
  all 106,267 shared rows. No 2024 outcome labels were used in recovery (predictions +
  features only). Verdict: RECOVERED-REPRODUCIBLE.
- **Scaling constants:** recomputed deterministically from the 2023 frame at bundle
  build (`mu`, `sd` stored in `preprocessing_manifest.json`); frozen thereafter.
  Future bundles must serialize scaler + intercept at fit time instead of recovering.
- **Feature order:** `feature_manifest.json → feature_order` (24 columns: 18 F1–F5 +
  rest + debut + 4 trip/index terms) plus the logit(P3) baseline input.
- **Bundle status:** DEVELOPMENT_BASELINE. **Production status:** NOT APPROVED.
- **Rollback target:** P3-log5 transparent baseline
  (`experiments/pitcher_prior/`, card `pitcher_prior`).
- **`log_pa_prior`: INACTIVE_HISTORICAL_FEATURE.** Constant zero by construction in
  every frame AND fitted L3 coefficient exactly 0.0 (stored metrics). Proven to affect
  no prediction. Preserved in this bundle for historical fidelity; excluded from all
  future manifests unless repaired under a separately registered experiment. No rerun
  is warranted (a constant-zero feature cannot affect predictions).
