# BF reconstruction / A/B preflight closure record (2026-10-12/13)

> Point-in-time record of the bounded BF reconstruction, preflight, and A/B
> forecast-artifact work. SUPERSEDED only by a newer dated record.

## Completed (all local unless noted; no pilot outcomes ever accessed)

1. **Aggregation remediation** (commits c0805be, 33e1f63, a671e7a):
   baseline renamed I1_ref; CORRECTION-1 note; A_v1 sensitivity arm
   (B-A_v1 -0.0292*; denominator effect -0.0038 n.s.); Gate A corrected
   (support truncation root cause, not scipy/dtype; frozen 1e-9 gate passes
   all 4,446 rows; elementwise diff <=7.3e-14; scores unchanged).
2. **Adapter D1-D4 closure** (b2d7140, dee0c5a): confirmed-only default,
   pinned latest-snapshot rule (no older-revision substitution),
   canonical team-code delegation, tz-aware cutoffs, malformed-timestamp
   fallback, mixed-status fallback, D1 cutoff-basis labels.
3. **BF reconstruction** (5f66d516... runner): single frozen fit, 9,712
   starts (2023+2024; 2022 history-only per frozen builder deviation note),
   213,162 risk rows, option-A fallback amendment (mean_bf 21.9259 from
   frozen derive_fallback_2022), converged 57 iters; bundle
   c7ff78b1...6fcd; fit-to-reload parity exact (probe max diff 0.0).
   Two FAILED_POPULATION bundles preserved (missingness dropped rows).
4. **Preflight** (0913a37f...): frozen tail contract (P(N>=37) geometric
   redistribution 37..60); 134/142 probable rows matched; confirmed-only
   11 usable-B / 123 fallback / 8 null-probable excluded.
5. **A/B forecast artifact** (921f7e5e... runner; cand5/final artifacts):
   deterministic team binding (fixed game_pk-only collision both sides),
   keyed intermediates dumps, fail-closed revision inventory, mandatory
   pre-load bundle identity guard, computed reconciliation receipts,
   cycled-prefix mean-gate vs independent target. Arrays:
   A 16c31bfb...f116, B ceb1dca3...f9e1d; bundle identity guard tested
   (missing/tampered/approved).
6. **CI publication** (review branch review/pa-remediation-2026-10-09,
   PR #1): commits b212ffb + 56e2799. Line-ending normalization mapping
   documented (working pins 921f7e5e/0e0607ac vs LF blobs 7f1baac9/dd3316c7
   - content-identical). Bundle-guard test skips when the repo-external
   artifact is absent.

## OPEN (blocker to CI green)

- tests/test_odds_board_lines.py::test_heal_stale_slate_thresholds fails
  deterministically on ubuntu CI ("assert 4 == 5", line 616) but passes
  locally on Windows: environment/tz-dependent pre-existing production
  test, unrelated to BF files. Needs owner-authorized fix (suspected
  date/timezone handling); CI gates on it.

## Frozen artifacts (external, MLB-Props-Research)

- Approved BF bundle: bf-bundle-2026-corr-20261012_132811 (bundle
  c7ff78b1...6fcd; producing runner 5f66d516...226a recorded in manifest).
- Candidate A/B forecasts: bf-ab-forecast-2026-cand5 (+ cand1-4, diag/fix
  attempts preserved; all non-candidates marked non-sealable).
- 11 usable-B / 123 fallback is an integration pilot, NOT promotion
  evidence; pilot outcomes remain locked pending seal.

## Next steps

1. Owner-authorized fix or ruling on the odds_board CI failure; rerun CI.
2. Seal package (row ledger, arrays, bundle, hashes, scoring plan).
3. Outcome join + frozen scoring after independent seal verification.
4. Roadmap execution (docs/reference/mlb-strikeout-forecasting-roadmap.md):
   P0 data card -> P1 challenger harness -> P2 ladder.

## Correction (2026-10-13, dated)

- Earlier CI was green but OMITTED negative guard coverage: the original
  bundle-guard fixture skipped entirely on CI runners (external artifact
  absent), so missing-file and wrong-byte rejection were never exercised
  there. The split (commit 1c17ba7) restores always-running negative
  coverage: missing-file -> OSError at the hash-read stage (rejection
  before deserialization; loader never invoked), wrong-bytes -> explicit
  MechanicalFailure identity-mismatch on synthetic non-approved bytes;
  approved positive check remains a conditional-skip integration test.
- Note: missing-file raises OSError (hash-read) rather than
  MechanicalFailure; the production guard was not changed (runner-logic
  change not authorized).

## CI evidence closure (2026-10-13, dated - observed results only)

- Reporting-enabled revision b0540143909c11696d756c6d4c9ea3dae9a70350
  (branch review/pa-remediation-2026-10-09, pushed; event pull_request,
  attempt 1) - run 38340106215, job test-and-validate: success.
- Node results from JUnit artifact (sha
  ca766f67a28b93f6df5159cf9ae6584820cb78122455362b454a16a3feaff815):
  test_bundle_guard_missing_file_rejected PASSED;
  test_bundle_guard_wrong_bytes_rejected PASSED;
  test_bundle_guard_approved_bundle_positive SKIPPED (external approved
  bundle absent on CI runner - positive integration leg only; negative
  legs unconditional). Totals: 748 passed, 10 skipped.
- Earlier statement corrected: only the approved-positive leg is
  skip-gated; negative bundle-guard tests ran unconditionally in CI.
- Seal package binding advanced from 0e8ab7b to b054014 (reporting-only
  workflow edit); producing-code and artifact identities preserved.
