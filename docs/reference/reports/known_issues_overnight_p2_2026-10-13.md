# KNOWN ISSUES — overnight-p2 (recorded 2026-10-13)

Add-only documentation. Manifests are NOT regenerated (a manifest that lists
itself cannot be made self-consistent, and regenerating would churn hashes for
cosmetic reasons). Two cosmetic errors in `morning_report_v2.md` were fixed in
place the same day; see item 3.

## 1. Run-identity derivation gap

`run_identity.json` records a composite `run_identity_sha256 =
6a62d8edf60ec0951d30a3114ac3603da7d5296d52a1c1ea800dc1dff7c6def2`, but no
script or recorded procedure derives that composite from the component hashes
listed in the same file. It is an asserted label, not a recomputable value: a
reader cannot verify it, and nothing downstream should try to. The component
hashes (scripts, data, config) ARE individually recomputable and were verified
on 2026-10-13.

Additional coverage gap in the same file: the `scripts` map lists only the
seven scripts that existed when the identity was frozen. Scripts added later
(`export_executed_keys.py`, `make_run_manifest.py`, `run_log5_ew.py`, and the
2026-10-13 addendum scripts) are not covered by the run identity, even though
they produced artifacts referenced by it.

Verification performed 2026-10-13 (all PASS):

- All 7 listed script hashes match the current files.
- `pa_table.parquet` = `1d3be629…846aff`, `features_v3.parquet` =
  `163ad433…7e8f8`, `experiment_config.json` = `6958b536…0863` — all match.
- `run_identity.json` file hash `780402d6…28d24` matches its entry in
  `run_manifest.json`.

## 2. run_manifest.json self-hash quirk

`run_manifest.json` contains an entry for itself:

    "run_manifest.json": "d9546753730cc24520cabed7220999d2071f148b98f22773b948298e67cbd3c3"

A file cannot contain its own hash: writing the hash into the file changes the
file, so the recorded value can never match. The actual file hash (verified
2026-10-13) is `fb0f1768fb1e75cd4fc1afa0c70b048ec3fc7b0587b24f184057a0e6075821d5`.
The recorded value appears to be from a pre-finalization write made by
`scripts/make_run_manifest.py` (which globs every root `*.json`, including the
manifest it is about to write). Expected quirk, not tampering. Every other
entry in the manifest refers to a different file and is verifiable.

## 3. morning_report_v2.md corrections (fixed in place, 2026-10-13)

- Per-block assessment date counts were wrong (stale values from the
  superseded pre-v3 run): 177/165/172/161 corrected to 95/88/98/86, and the
  pooled dev header now states 281 dates. Sources:
  `reports/ladder_results.json` (`blocks.<block>.dates.assessment`) and
  `reports/pooled_comparison.json` (277,623 rows / 281 dates).
- The `experiment_config.json` hash citation read `264174d0…2ca3`; the actual
  hash (per `run_identity.json` and direct recomputation) is
  `6958b536788b37127debfc1deb7643e216846c9c575abe35272ec890d17b0863`.
  Corrected in place.

No numbers, CIs, tables, or conclusions in the report were affected by either
error; both were citation/cosmetic only.
