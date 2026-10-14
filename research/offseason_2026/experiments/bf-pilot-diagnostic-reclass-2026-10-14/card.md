# Card: bf-pilot-diagnostic-reclass-2026-10-14

**Date:** 2026-10-14. **Scope:** reclassification + membership
enforcement + PMF divergence attribution for
bf-2026-pilot-diagnostic-v1. NO real-outcome scoring (all label data
used is SYNTHETIC, seeded, temp-dir only); NO new fits; NO 2026
outcome reads.

## What was done

1. **RECLASSIFICATION.** The diagnostic is renamed
   "REBUILT-RECIPE DIAGNOSTIC ON INSPECTED PILOT COHORT" in
   `<lake>\bf-2026-predictor-seal-v1\PILOT_DIAGNOSTIC_COMMAND.txt` +
   the new `<lake>\bf-2026-predictor-seal-v1\DIAGNOSTIC_CLASSIFICATION.md`:
   NOT value-level pilot reproduction, NOT confirmatory evidence.
2. **PMF DIVERGENCE (predictor-only).** `pmf_divergence_compare.py` ->
   `pmf_divergence_report.json`: rebuilt vs original pilot PMFs,
   row-aligned (order/key sets/cutoffs identical). Max abs diff over
   the 134 keys: arm_A 0.2766, arm_B 0.2756; every row diverges
   (per-row max min/median: A 0.0121/0.0448, B 0.0059/0.0466);
   usable-B(11) max A 0.0656 / B 0.0630; fallback(123) max A 0.2766 /
   B 0.2756. Pilot fallback B==A bitwise verified (123/123); rebuilt
   payload has 0 such rows. Attribution: multiple documented
   construction differences (PA checkpoint confirm_2025H2 vs pilot-era;
   CAL column usage; projected-batter-state v2 vs realized/oracle pilot
   batter inputs; BASE empirical BF vs pilot bundle; H3/logistic arm
   definitions vs pilot I1_ref/lineup-mixture arms), each applying to
   all 134 rows; individual contributions NOT isolated - this is a
   co-occurrence listing, not a per-difference decomposition. No
   unexpected mismatch; no STOP.
3. **MEMBERSHIP ENFORCEMENT (executed path).** Chat 2's finding
   confirmed: the scorer read usable-B membership from payload arm
   flags with no enforcement. Closed in
   `research/offseason_2026/run_bf_ab_score_cohort.py` (version
   cohort-aware-2): `--membership-file` REQUIRED in score mode;
   one-to-one (game_pk, pitcher) join against the ORIGINAL pilot
   membership; fail-loud on duplicates / missing / unexpected extra
   keys / unknown statuses / wrong partition (`--expect-usable-b 11`
   pins 134/11/123); payload re-stamped flags ignored
   (`payload_arm_flags_ignored: true`); PMFs never modified (payload
   sha256s recorded in the report). Staging side
   (`pilot_membership_join.py`) hardened: duplicate-key rejection in
   both packages, known-status check, explicit 134/11 asserts,
   array-equality PMF check, seal-flag partition recorded as ignored.
4. **STEP 1 EXECUTED** (metadata only): staged diagnostic root written
   with the exact 11/123 partition; staged PMFs byte-identical to the
   seal pins (receipt `staging_receipt.json` sha256
   9df7e4cf07e8de58c6aaee05e0ca191cfb8c9b628b8c913098a806e2a0966e8b).
5. **SYNTHETIC-LABEL VERIFICATION.** Seeded synthetic parquet
   (default_rng 20261014, temp dir) -> score mode emits
   population_all n=134 (11 slate dates) and population_usable_B n=11
   (2 slate dates), unmatched 0. Demo suite re-run 3/3 PASS after the
   scorer change. Enforcement checks: positive control + 7 negative
   tests, all fail-loud as expected (see
   `enforcement_checks/enforcement_verification.json`).

## Key hashes

| Item | sha256 |
| --- | --- |
| run_bf_ab_score_cohort.py (modified) | d8e26eefb50181e56e9eb27d09047d2e1a8840bdba1d0fcc5af67e2ced22b53a |
| pilot_membership_join.py (modified) | 3805776062e4dc53102c16cecb261da94f9659c4c2a6262f86410dd541270e33 |
| run_bf_cohort_mode_demo.py (modified) | 5c5277c6aa4328dca30bcb3ae4fc2dd31a0ae03732ee2a7930c1f1fdba41761a |
| pinned_manifest_pilot134.json (unchanged) | 8e455146f8a06ed8486a4be0564a7c62881ef80ce59f71a911780f7eaa18a708 |
| membership (pilot row_keys.json) | 1d4c74965a52f38a7b3b209f3ce0185ba42f961706bd01ed29393a565a95361f |
| staged payload row_keys.json | 1d4c74965a52f38a7b3b209f3ce0185ba42f961706bd01ed29393a565a95361f |
| staged payload arm_A_pmf.npy | ae6b754bb7a931e92a4bd164ed06cafeef2a79bedccab1b93474b89304b99119 (== seal pin) |
| staged payload arm_B_pmf.npy | 2cd2fecb50bfb8a35e4fbcb4949f18d6a7600d80ae93d2969f3e26fb3d30b349 (== seal pin) |
| pmf_divergence_report.json | d6a17eaa5109a9c9506f8deadf760a14e5e91f956a0e87b3f53a252c636e438c |
| synthetic_label_run/cohort_scoring_report.json | db324df3987a4f9f424898a87385094eb7b7f4337a5fd25ef1c35e57a9346b3c |
| enforcement_checks/enforcement_verification.json | 064763c8ea8d66b5bb903ee753436e0a348668abd5e0888f766e1298ff71d639 |

Full ledger: `hash_ledger.json`.

## Deviations

None from the frozen recipe or the no-2026-tuning rule. The scorer and
join script changes are additive research-side enforcement; no live
scorer, policy JSON, schedule, or ledger touched. Real-outcome STEP 2
remains gated on owner approval.
