# Card: bf-cohort-scorer-mode-2026-10-14

**Bounded preparation - scorer generalization demo. NO 2026 outcome
scoring (synthetic labels only, generated in tempdirs).**

## Question

Can the scoring path execute against a cohort whose size is pinned by a
manifest file instead of the hardcoded `n == 134` in the vendored v2
scorer, while preserving canonical historical pilot-scorer behavior and
all fail-loud checks?

## Method

- New additive module `research/offseason_2026/run_bf_ab_score_cohort.py`
  (lineage: b2fef02 vendored v2 -> this file):
  - validate mode (outcome-free): payload n + exact key set + cutoffs
    validated against a PINNED row-key manifest; unique-key,
    identical-arm-population, 24-bucket PMF validity checks all
    fail-loud (SystemExit on any violation);
  - score mode: metric/bootstrap code copied VERBATIM from the vendored
    v2 compute_stats (same kc.count_rps, same 2,000-resample slate-date
    bootstrap seed 20261001, same secondaries, same (game_pk, pitcher)
    keying); the ONLY semantic change is the cohort gate;
  - hash-verifies the vendored v2 against the pin on every invocation.
- Demo runner `research/offseason_2026/run_bf_cohort_mode_demo.py`.

## Results (demo_report.json - all PASS)

1. **demo1_parity_on_seal_fixture** - the real bf-2026-predictor-seal-v1
   payload (134 rows) is accepted by the cohort-aware validation
   against the committed pinned manifest `pinned_manifest_pilot134.json`
   (derived from seal row_keys.json sha256 cece35fa...); checks
   identical to canonical gating + manifest key-set/cutoff equality;
   zero outcome reads.
2. **demo2_metric_parity_synth134** - canonical
   run_bf_ab_score_v3.py and the cohort-aware scorer produce EXACTLY
   equal statistics (float equality, every statistic in
   population_all / population_usable_B / secondary) on the same
   synthetic 134-row payload + synthetic label parquet.
3. **demo3_non134_acceptance** - a synthetic 40-row payload is accepted
   and scored (n=40) by the cohort-aware mode under its own pinned
   40-row manifest, while canonical v3 (hardcoded 134) fails loudly on
   the same payload - canonical behavior preserved.

## Vendored-pin defect (disclosed)

The b2fef02 commit message and EXECUTION_MANIFEST_2026.json v2 record
the v2 sha256 pin as a 63-character string (one hex digit dropped after
"6b8cecf2"). True sha256 of the vendored file, the executed v2 archive,
and the archived-scoring-sources copy are all the 64-character
`6b8cecf24a2463463d98e94e84b0bdab146d55cb6d29382c4955eb4cdb24bc4a`
(three-way byte identity verified 2026-10-14). Content provenance
intact; only the recorded pin string was mistyped. The new module pins
the corrected 64-character value and documents the defect.

## Files

- `pinned_manifest_pilot134.json` - pinned manifest for the 134-row
  fixture (metadata only: game_pk/pitcher/cutoff/arm-B-stamp rows as
  recorded in the seal payload source)
- `demo_report.json` - full demo receipt

## Deviations

None. Synthetic payloads/labels live in tempdirs (regenerable
deterministically from the demo runner; hashes recorded in
demo_report.json).
