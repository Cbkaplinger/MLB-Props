# CANDIDATE_MAP — count-eval-v2 registered candidate-ID map

Registered 2026-10-15. Reconciles the candidate-ID namespaces into ONE
registered table so every lane uses the same IDs for the same models.

- **ID namespaces:** `P*` = PA-lane roadmap tiers (COMPARISON_INTERFACE_SPEC.md
  section 5, PA lane). `B*` = BF lane (spec section 5, BF lane). `F*` =
  feature-family ablation lane, registered HERE for the first time (2026-10-15);
  definitions follow the spec section 2 availability contract and align with
  the feature-family vocabulary of
  `docs/reference/pa_feature_lineage_2026-09-30.md` (platoon = lineage F1,
  batter discipline = lineage F2).
- **Statuses:** `NOT-STARTED` (registered only), `IMPLEMENTED-ADAPTER`
  (adapter exists in harness/comparison.py and passes the synthetic suite;
  NO real-data execution), `EXECUTED` (a separately authorized scored run has
  produced outputs), `PLACEHOLDER-NOT-IMPLEMENTED`.
- **Execution gate (spec section 8):** no candidate may touch real data until
  (a) all synthetic tests are green, (b) frozen config hashes are in the
  manifest, (c) owner authorization consistent with the F-4 one-run gate
  discipline is recorded. Nothing in this map authorizes a run.
- **2026 rows remain CLOSED** (no 2026 loads, no 2026 tuning).

## Registered lanes

- **PA-fixed lane:** hold the BF arm FIXED at the incumbent BF artifact
  (B0, frozen bf-workload-v1 PMFs + frozen per-PA arm probabilities) and vary
  the PA model over `P*`/`F*`. Metric grain: PA log loss / Brier per fold +
  pooled dev.
- **BF-fixed lane:** hold the PA arm FIXED at the incumbent PA probabilities
  (P1_H3_incumbent_refit raw lane / P0_log5 identity, exactly as executed) and vary the
  BF model over `B*`. Metric grain: count-RPS, count log score, mean-K error,
  milestone Briers at 6/8/10/12 with the corrected PMF-tail exceedance
  definition (`run_pregame_state_v3.py:107-116`).
- The two lanes are scored SEPARATELY; paired comparisons never cross lanes.

## Registered candidates

| ID | Lane | Namespace source | Definition | Status |
| --- | --- | --- | --- | --- |
| P0_log5 | PA (PA-fixed lane baseline) | spec section 5 (roadmap tier P0) | full log5 identity on w150 priors + lg_rate; no fit, no scaler (`run_ladder.py:77-83`) | IMPLEMENTED-ADAPTER (synthetic tests only) |
| P1_B_logreg | PA | spec section 5 (roadmap tier P1, B-variant) | LogisticRegression(C=1.0, max_iter=1000) + StandardScaler (base_train only) on the 6 frozen B features (`run_ladder.py:172-181`) | IMPLEMENTED-ADAPTER (synthetic tests only) |
| P1_H3_incumbent_refit | PA | spec section 5 (roadmap tier P1, H3 variant) | INCUMBENT-PROCEDURE REFIT: re-executes the frozen H3 fitting procedure (same logistic spec on the 8 H3 features) on the registered folds; NOT proven prediction-equivalent to historical incumbent outputs (pred_H3_raw); equivalence requires a separate real-data comparison requiring authorization. Not a new fit, not a search; claims no new evidence | IMPLEMENTED-ADAPTER (synthetic tests only) |
| P2_lgbm | PA | spec section 5 (roadmap tier P2) | LightGBM binary classifier, same rows/folds, prior-only features with declared availability; monotone-constraint policy frozen in config BEFORE any fit | NOT-STARTED (stub fails loud) |
| B0_bf_frozen | BF (BF-fixed lane baseline) | spec section 5 (BF lane B0) | frozen bf-workload-v1 BF PMFs + frozen per-PA arm probabilities (H3-raw / LOG5-raw lanes exactly as executed); bit-identity gate vs stored start_metrics_v2 | NOT-STARTED |
| B1_ridge_bf | BF | spec section 5 (BF lane B1) | Ridge replacing the BF-PMF-producing model's fit stage, same folds, emits the identical PMF artifact shape | NOT-STARTED (stub fails loud) |
| B2_lgbm_bf | BF | spec section 5 (BF lane B2) | LightGBM regressor in the same seam as B1 | NOT-STARTED (stub fails loud) |
| B3_exit_hazard | BF | spec section 5 (BF lane B3) | discrete exit-hazard over BF 1..36 (hazard vector -> `kcount_combiner.py:27-51` extend_overflow_with_hazard), same folds | NOT-STARTED (stub fails loud) |
| F0_features_control | PA feature-family ablation | registered HERE (first registration) | control: incumbent feature set unchanged (identical inputs to P1_H3_incumbent_refit); no added family | NOT-STARTED (run aliases P1_H3_incumbent_refit) |
| F1_platoon_add | PA feature-family ablation | registered HERE (first registration) | F0 + handedness/platoon prior-only features (aligns with pa_feature_lineage family F1); every added feature declares its availability timestamp source and passes the leakage guard | NOT-STARTED |
| F2_discipline_add | PA feature-family ablation | registered HERE (first registration) | F0 + batter-discipline prior-only rolling rates (aligns with pa_feature_lineage family F2); same availability + leakage rules | NOT-STARTED |

## Placeholders

| ID | Definition | Status |
| --- | --- | --- |
| C_two_shrinkage_placeholder | logistic on w150+w500 rates + supports + cold_start (`p1-harness-v2\scripts\fit_models.py:63-75`); pooling placeholder, not hierarchical; not part of the overnight-p2 ladder | PLACEHOLDER-NOT-IMPLEMENTED |
| H_hierarchical | hierarchical model over the same rows/folds; no concrete definition registered yet | PLACEHOLDER-NOT-IMPLEMENTED (stub fails loud) |

## Superseded IDs

| ID | Superseded by | Reason | Registered | Superseded |
| --- | --- | --- | --- | --- |
| P1_H3_replay | P1_H3_incumbent_refit | the "replay" name invited the wrong reading (that stored incumbent predictions are replayed); the adapter re-executes the frozen H3 fitting procedure (a refit), and no prediction-level equivalence vs the historical incumbent outputs (`pred_H3_raw`) is established. HANDOFF_CAPABILITIES.md section 1 + defect 1 documented the naming defect; fixed by rename 2026-10-15 | 2026-10-15 (commit 5d54264) | 2026-10-15 |

## Executed bit-identity check (2026-10-15, read-only)

`harness/comparison.py` derive_folds + eval_identity_hash run read-only against
the frozen canonical inputs (`overnight-p2\data\pa_table.parquet` +
`features_v3.parquet`) reproduce the EXECUTED overnight-p2 assessment keys
bit-identically for all four folds (`keys_executed_<block>.parquet`, partition
= assessment, 94,458 / 87,808 / 95,357 / 87,569 rows). This pins the fold
construction to the executed ladder. No fit, no score, no outputs written.

## Cross-references

- Spec: `..\COMPARISON_INTERFACE_SPEC.md` (lake:
  `C:\Users\ckaplinger\MLB-Props-Research\count-eval-v2-spec\COMPARISON_INTERFACE_SPEC.md`)
- Feature/fold ground truth: `C:\Users\ckaplinger\MLB-Props-Research\extracted_feature_reality.md`
- Incumbent code: `C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\scripts\run_ladder.py`
  (SUPERSEDES `p1-harness-v2\scripts\fit_models.py`)
