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

| result | defect | replacement |
|---|---|---|
| Pre-repair market comparisons (morning/close mixed) | D1: opposing-starter quote mixing | full-key repaired market eval |
| Pre-repair morning v1 (tie-sensitive) | D1 residual + nondeterministic ties | morning_vs_close_v2_tie_v2 |
| Ablation count-RPS 1.29880/1.28419 | D2: realized-PA slot conditioning | ablation_count_rps_canonical_v2 |
| Ablation count-RPS 1.31602/1.33354 | D2 variant (different training window derivation) | ablation_count_rps_canonical_v2 (1.33457/1.31744) |
| C-B1 lineup-effect interaction | D3: control invariant FAILED | interpretation stopped |
| 277-start "batter features hurt count-RPS" | D2 artifact | retracted; count ordering agrees with per-PA |
| 150-row "different history source" | audit-side fan-out | retracted |

## 5. Accepted results

| result | metric | values |
|---|---|---|
| Ablation count-RPS (canonical) | count-RPS, 4,823 starts | PITCHER 1.33457, FULL 1.31744, frozen 1.31761 |
| Ablation PA log loss | multiclass LL, 82,817 PAs | LEAGUE 1.2376, PITCHER 1.2319, FULL 1.2231 |
| M0 EP1 | K-marginal LL delta | −0.0000073, CI upper +0.0000061 (PASS) |
| M0 EP2 | multiclass LL vs baselines | 1.2241 < 1.2263 (log5) < 1.2377 (league) (PASS) |
| Market baseline (2025H1 T-5) | LL vs close, n=2,154 | model +0.0234 CI [+0.0142, +0.0330] |
| Morning baseline (T-5h) | LL vs morning, n=2,109 | model +0.0225 CI [+0.0141, +0.0307] |
| C-B1 | count-RPS delta | +0.0859 CI [+0.0719, +0.0997] (LOST, closed) |

## 6. Remaining limitations

- Historical-availability: the lineup artifact carries no per-row
  publication timestamp; morning-input availability is asserted by
  construction, not timestamp-verified.
- The 2024 "close" snapshots are prior-evening lines (T-17..25h);
  no 2024 true-close data exists in the held archive.
- The frozen binary's count-RPS advantage over the multinomial model
  is ~0.00017 with CI including zero — no improvement is demonstrated,
  but the direction is consistent across both dev blocks.
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
- Calibration experiment for the frozen K-count PMF (drafted, not
  executed — see below)

## 8. Calibration experiment DRAFT (not executed)

Objective: improve the frozen K-count PMF's count-RPS via a
calibration layer, without changing the PA model or the BF forecast.

Design:
- Fit a calibration mapping on the development blocks
  (chronological, walk-forward; same fit/cal split as the ablation).
- Candidate mappings: temperature scaling on the per-PA K probability;
  isotonic regression on the count-PMF CDF; per-BF-band rate
  adjustment.
- Evaluation: count-RPS (primary) on the identical 4,823-start
  population; calibration diagnostics (reliability buckets) and
  own-line LL/Brier (secondary).
- Constraint: coherent nonnegative normalized PMFs; no selecting
  calibration to maximize the sportsbook gap; the close benchmark is
  reported but never used for selection.
- Stop condition: if walk-forward count-RPS does not improve, close
  without deploying.
