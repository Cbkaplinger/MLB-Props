# lgbm-equal-info-v1 - prep card (amendment-1 executable freeze)

**Date:** 2026-10-15. **Status:** FROZEN - NOT EXECUTED (amendment-1; PREP-COMPLETE, synthetic only).
**Freeze:** `research/offseason_2026/specs/count-eval-v2-spec/harness/freeze_lgbm_equal_info_v1.json`
(amended config sha256 `b33e2a845c929f5f6dafba9c0adfcab49b4ee26655ed42e4f09428d9a2a100cf`;
original registration `8dec7352...f294` preserved verbatim in `historical_registrations`).
No real-data execution has happened or is authorized by this card; the readiness gate is unchanged.

## What this batch is

DEVELOPMENT-ONLY LightGBM equal-information comparison: `P2_lgbm_equal_info` (frozen single
config, 8 both-EW features) vs the both-EW logistic reference `P1_H3_incumbent_refit`, on the
three registered dev folds, RAW Brier primary, CAL separate, explicit baseline-bound contrast
`C_lgbm_vs_both_EW_logistic`. confirm_2025H2 EXCLUDED - NOT SCORED; 2026 rows CLOSED.

## D-1 - shared tracking wrapper (TRACKING IN EXECUTION)

One shared wrapper now owns the whole chain; the frozen command invokes it and no code path
hand-replicates logging calls anymore.

- **Location:** `research/offseason_2026/specs/count-eval-v2-spec/harness/track_and_verify.py`
  (byte-identical lake mirror `MLB-Props-Research\count-eval-v1\track_and_verify.py`).
- **Chain:** compare (exactly once) -> save (`metrics.json` + config artifact, write-once,
  canonical outputs finalize) -> log (MLflow params/metrics/artifact) -> verify (fresh
  `MlflowClient` retrieve + exact metric round-trip + artifact byte-hash).
- **Frozen-command invocation:** `run_lgbm_equal_info.py` (registered in the freeze, same
  harness dir) calls `track_and_verify.track_and_verify(...)` after the wrapper itself finalizes
  the canonical outputs; the adapter's `mlflow_synthetic_roundtrip` is DELEGATED to the same
  wrapper.
- **Failure contract (injected-failure tests):** an MLflow failure (monkeypatched logging
  failure, genuinely unreachable tracking store, or verification mismatch) SURFACES to the
  caller as `TrackingFailure` (CLI exit nonzero); the computed canonical outputs are preserved
  untouched (byte-verified against a reference compare in the tests); `tracking_status.json`
  records `status: "tracking_failed"` in the run dir so the batch is never reported fully
  successful; and an upload failure NEVER triggers a refit (the tests assert compare ran exactly
  once).

## D-2 - amendment-1 executable freeze (registered identities)

- **Literal command (registered in the freeze; NOT EXECUTED):**

  ```text
  python research/offseason_2026/specs/count-eval-v2-spec/harness/run_lgbm_equal_info.py --freeze research/offseason_2026/specs/count-eval-v2-spec/harness/freeze_lgbm_equal_info_v1.json --tracking-uri sqlite:///C:/Users/ckaplinger/MLB-Props-Research/mlflow.db --i-accept-real-data-execution
  ```

  `--i-accept-real-data-execution` is the `--i-accept-outcome-scoring` equivalent (the batch
  scores realized outcomes on the registered dev folds); without it the runner refuses (exit 2)
  and reads nothing.

- **Registered identities (full sha256s, verified by the wrapper BEFORE any fitting via
  `verify_registered_identities`; fails loud on the first mismatch):**

  | Identity | sha256 (first 16) |
  | --- | --- |
  | pa_table `p1-harness-v2\data\pa_table.parquet` | `e30d8561d8d0fbb9` |
  | features_v3 `overnight-p2\data\features_v3.parquet` | `163ad43356e66649` |
  | start_metrics outcome source `bf-workload-v1\data\start_metrics_v2.parquet` | `af6814ec7ea73b4a` |
  | adapter `lgbm_equal_info_adapter.py` (lake) | `fab4658c8e90a8ad` |
  | adapter frozen config (`LGBM_EQUAL_INFO_CONFIG`) | `f7e3726a5259920e` |
  | builder-worktree harness `comparison.py` | `947517cd67770538` |
  | tracking wrapper `track_and_verify.py` | `859527b5755c6ce9` |
  | frozen runner `run_lgbm_equal_info.py` | `dde03d1273803082` |

  `start_metrics_outcome_source` is REGISTERED-PATH-ONLY: registered for a LATER registered
  join; it is NOT read and NOT joined by the frozen command (no join now).

- **Historical preservation:** the previous registration (config sha256
  `8dec7352957b8d4f09073a8b296450f69ae551a2d27e758da3c1bf2fdac6f294`) is preserved verbatim in
  `historical_registrations[0]` with a SUPERSEDED annotation; its config object hash-verifies
  byte-identically (asserted in `test_amended_freeze_registration_integrity`).
- **Amended config hash (recomputed after the final code + command were fixed):**
  `b33e2a845c929f5f6dafba9c0adfcab49b4ee26655ed42e4f09428d9a2a100cf`.

## D-3 - FINAL-FIT DECLARATION

PREDICTIONS USE `best_iteration` - `predict_raw` calls
`booster.predict(X, num_iteration=booster.best_iteration)`
(`lgbm_equal_info_adapter.predict_raw`), and `best_iteration` is recorded per fold in the
comparison output. There is **NO refit on the full training fold** anywhere in this batch: each
fold fits once on its own base_train (early stopping on the inner base_train carve-out ONLY),
the reviewed per-fold procedure is UNCHANGED from the original registration, and there is no
full-data refit, no refit on dev-assessment rows, and no second fitting pass. Declared in the
freeze (`config.final_fit_declaration`) and in this card.

## Tests (all synthetic; no real data, no canonical MLflow store)

| Suite | Result |
| --- | --- |
| harness `test_comparison.py` + `test_null_centered.py` | 40 passed |
| harness `test_auto_tracking.py` (repo mirror) | 7 passed (wrapper round-trip fresh-process, 3 failure-injection, 2 identity incl. real-freeze on-disk verification, 1 frozen-command end-to-end) |
| lake `test_lgbm_equal_info_adapter.py` + `test_auto_tracking.py` (byte-identical mirrors) | 15 passed (8 adapter + 7 tracking) |

## Destination + execution state

- Output destination `C:\Users\ckaplinger\MLB-Props-Research\lgbm-equal-info-v1` remains
  ABSENT (write-once never executed; asserted by the integrity test).
- No real-data execution; the readiness gate (PENDING) and the standing conditional
  authorization after READY are unchanged.
