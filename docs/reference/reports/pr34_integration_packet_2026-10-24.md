# PR #34 integration packet — pregame-pa-ext-v2 lane
# (prepared 2026-10-24; code SHA 9804da4; 138 tests green, 0 failed)

## 1. Current-head test results

12 test files, 138 tests, 0 failed, 0 skipped:
- test_attach_order_invariance.py (4): order-invariance regression
- test_pregame_pa_adapter.py (20): adapter contract tests
- test_market_eval_k.py (24): market-eval identity + deterministic
  selection + conflict rejection
- test_ablation_features.py (6): ablation harness
- test_lineup_diagnostic.py (4): lineup runner + control
- test_m0_multiclass.py (23): four-class model + taxonomy
- test_m0_verifications.py (6): M0 verification machinery
- test_m0_integration.py (7): M0 end-to-end
- test_count_agg_eval.py (8): count aggregation runner
- test_count_aggregation_exact.py (6): exact PB machinery
- test_count_aggregation_separation.py (9): separation tests
- test_exposure_profile.py (19): C-B1 + diagnostic runner

## 2. Changed components (vs the pre-audit state at ~421ae0b)

| component | change | nature |
|---|---|---|
| adapter.py:attach_prior_features | sort(long) before first as-of join | defect repair |
| market_eval_k.py | verified_odds_for_start, full-key consensus, deterministic tie-break, conflict drop-counting | defect repairs |
| m0_multiclass.py | CLASS_NAMES corrected, descriptive-stage walrus + metrics-attach fixes, M0 v2 rescore wiring | defect repairs |
| ablation_count_rps.py | NEW canonical runner (v2: actual-max-date cutoffs, registered frozen PMFs, keyed outputs, mutually exclusive drops) | new |
| exposure_profile.py | C-B1 runner (closed; no change to frozen baseline) | new |
| lineup_diagnostic.py | 2×2 runner (control invariant FAILED; interpretation stopped) | new |
| feature_request_p0.py / feature_request_p0_v2_audit.py | P0 audit + corrected audit | new |
| morning_vs_close_run.py | frozen morning-vs-close runner | new |
| 12+ result/record files | canonical documentation | documentation |

## 3. Canonical artifacts (lake, write-once, hashes verified)

| artifact | purpose | key hash / receipt |
|---|---|---|
| ablation_count_rps_canonical_v2_recovered2/ | canonical ablation count-RPS (4,823 starts) | metrics `97620ac5…` |
| morning_vs_close_v2_tie_v2/ | morning + near-close v2 (2,109 starts) | metrics `53b4d93e…` |
| morning_close_cohort_v1/ | published 2,109-start cohort keys | `aef4055b…` |
| attach_full_population_v1/ | full 64,215-slot compatibility check | `fb434e33…` |
| match_audit_v1/ | event-matching candidate audit | `17541d2d…` |
| m0_multiclass_v2_attempt2/ | M0 v2 execution (EP1+EP2 PASS) | `aca95253…`/`0d7decdf…` |
| cb1_exposure_v2_attempt2/ | C-B1 close (LOST by +0.086 RPS) | `1d125e6f…` |
| morning_provenance_v1_run4/ | morning quote-timestamp provenance | availability_check.json |

## 4. Invalid historical results (preserved, superseded)

| Invalid historical result | Defect class | Replacement |
|---|---|---|
| Pre-repair market comparisons (morning/close mixed) | D1: opposing-starter quote mixing | full-key repaired market eval |
| Pre-repair morning v1 (tie-sensitive) | D1 residual + nondeterministic ties | morning_vs_close_v2_tie_v2 |
| Ablation count-RPS 1.29880/1.28419 | D2: realized-PA slot conditioning (277-start defect) | ablation_count_rps_canonical_v2 |
| Lineup-diagnostic interaction −0.0087 (4,477-key) | D3: control invariant FAILED (feature-path divergence) | interpretation stopped; resolution options documented |
| "Batter features hurt count-RPS" (277-start) | D2 artifact | retracted; count ordering agrees with per-PA on the correct population |
| "150-row different history source" | audit-side fan-out (game_pk+slot not unique) | retracted |
| M0 descriptive count-RPS "edge" | market-comparison artifact (identity defects) | quarantined; close is the verified benchmark and it wins |

## 5. Accepted results

| result | metric | values |
|---|---|---|
| Ablation count-RPS (canonical v2) | count-RPS, 4,823 starts | PITCHER 1.33457, FULL 1.31744; FULL − PITCHER = −0.01712 CI [−0.0249, −0.0092] |
| Ablation vs frozen binary | count-RPS, same 4,823 keys | FULL 1.31744 vs frozen 1.31761; diff −0.00017 CI [−0.00037, +0.00003] (includes zero — no improvement established; FULL has the slightly lower observed RPS) |
| Ablation PA log loss | multiclass LL, 82,817 PAs | LEAGUE 1.2376, PITCHER 1.2319, FULL 1.2231 |
| M0 EP1 | K-marginal LL delta | −0.0000073, CI upper +0.0000061 (PASS) |
| M0 EP2 | multiclass LL vs baselines | 1.2241 < 1.2263 (log5) < 1.2377 (league) (PASS) |
| Market baseline (2025H1 T-5, v3 tie fix) | LL vs close, n=2,109 | model +0.0227 CI [+0.0139, +0.0317] |
| Morning baseline (T-5h, unchanged by v3 tie fix) | LL vs morning, n=2,109 | model +0.0225 CI [+0.0139, +0.0305] |
| C-B1 exposure profile | count-RPS delta | +0.0859 CI [+0.0719, +0.0997] (LOST, closed) |

## 6. Remaining limitations

- Historical-availability: the lineup artifact carries no per-row
  publication timestamp; morning-input availability is asserted by
  construction, not timestamp-verified.
- The 2024 "close" snapshots are prior-evening lines (T-17..25h);
  no 2024 true-close data exists in the held archive.
- The frozen binary's count-RPS (1.31761) is marginally HIGHER than
  FULL's (1.31744) — FULL has the slightly lower observed RPS. The
  CI [−0.00037, +0.00003] includes zero, so no improvement over the
  frozen binary is established. The direction is consistent across
  both dev blocks.
- The 150-slot P0 history-source mismatch (4.8%) is resolved at the
  outcome level (0 mismatches after the order repair) but the root
  cause of the original 150-row discrepancy was an audit-side artifact,
  not a pipeline defect.
- Kalshi data is 2026-only; no dev-period exchange benchmark exists.

## 7. Parked proposals (NOT in this integration)

- Morning-market originator-style analysis (deprioritized: no
  aggregate advantage demonstrated)
- I3b/I4/I5 decision-logic re-audit (optional; BF builder verified)
- 2026 holdout (untouched; protocol defined, not run)

## 8. Calibration experiment card (standalone, pre-specified, NOT executed)

A standalone card is at `card_count_pmf_calibration_2026-10-24.md`.
Runner: `count_pmf_calibration_runner.py` at `af9cbb8`.
Shared module: `count_pmf_calibration.py`.

Key design (owner-reviewed):

- Layer: count-PMF (not PA-level).
- Method: one-parameter linear CDF recalibration — clipped mapping
  F_cal(k) = clip(1 - a(1-F(k)), 0, 1); PMF via F_cal differences;
  monotone by construction; F_cal(23) = 1 automatic.
- Comparator: identity (a = 1).
- Fit: block_2024H2 (2,314 starts) — chronological, out-of-sample.
- Evaluate: block_2025H1 (2,509 starts) — disjoint, later.
- Calibration/evaluation cohort hashes verified against predeclared
  expected values in receipt_initial.
- Primary: paired count-RPS (slate-date bootstrap).
- Acceptance: upper paired 95% CI bound < 0.
- Secondary: calibration diagnostics (threshold probabilities vs
  observed frequencies); own-line LL/Brier; MAE/RMSE of point summary.
- NOT EXECUTED — requires registered gate + owner authorization.
