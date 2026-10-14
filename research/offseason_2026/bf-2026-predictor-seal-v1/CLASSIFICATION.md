# CLASSIFICATION - bf-2026-predictor-seal-v1 payload

**Date:** 2026-10-14. **Classification: PILOT-REPRODUCTION.**

## What this package is

The current 134-row payload in this directory (`row_keys.json` +
`arm_A_pmf.npy` + `arm_B_pmf.npy`) is the **reproduction of the sealed
2026 A/B pilot population**, rebuilt under the accepted frozen recipe
(unique-batter v2 projected-batter state + BASE BF PMF + confirm_2025H2
frozen ladder checkpoints). It is NOT a new prospective forecast payload
and NOT the full-season registered cohort.

## Hashes preserved (payload NOT modified by this classification)

- `row_keys.json` sha256 `cece35faae57c04b91be3a86601bed81f633d394bd940249f7c7acb1314cba14`
- `arm_A_pmf.npy` sha256 `ae6b754bb7a931e92a4bd164ed06cafeef2a79bedccab1b93474b89304b99119`
- `arm_B_pmf.npy` sha256 `2cd2fecb50bfb8a35e4fbcb4949f18d6a7600d80ae93d2969f3e26fb3d30b349`
- `seal_manifest.json` sha256 `e3db6f018472aea3c9831e38a3133edb39f3bb1724da5e7f29ff32a3a86b1f16`

This classification file is additive metadata only. No payload file in
this directory was modified, re-written, or re-hashed.

## Population identity

- 2026 captured eligible cohort: 142 captured team-games, 8
  null-probable excluded, 134 forecast rows; both arms on identical
  rows. Key set + forecast cutoffs are IDENTICAL to the pilot package
  (`seal-package-preflight/row_keys.json`, 134 = 134, 0 symmetric
  difference; 51 distinct cutoffs spanning 2026-07-28..2026-08-22 UTC).

## Pilot membership metadata: source of record

The original pilot usable-B membership partition belongs to the PILOT
arm lineage and comes from the PILOT package
(`seal-package-preflight/row_keys.json`):

- **11 usable-B** rows (`arm_B_status = "ok_confirmed"`,
  `arm_B_equals_A = false` in the PILOT package), and
- **123 fallback** rows (`arm_B_status` startswith `A_fallback`;
  B == A bitwise in the PILOT package).

This seal payload RE-STAMPS all 134 rows as `ok_confirmed` /
`arm_B_equals_A = false` under the NEW builder's arm identities. Those
re-stamped flags are NOT the pilot membership partition and must never
be read as one. Any future usable-B view (the registered secondary
metric view) MUST take the 11-row membership from the pilot package (or
a scorer-side rule keyed to it), never from this payload's
`row_keys.json` metadata.

## Consequences (per PREREGISTRATION_2026.md sections 8-9)

- These 134 rows ARE the previously touched pilot population (outcomes
  already observed and scored in the pilot's scoring_report_v3.json).
- They cannot count as confirmation anywhere and are excluded from any
  pooled headline number; they are reported only under their own
  separated header.
- 2026 outcome scoring against this payload remains forbidden until
  the owner seals the payload.
