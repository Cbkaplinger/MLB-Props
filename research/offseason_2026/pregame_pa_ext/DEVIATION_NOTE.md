# DEVIATION NOTE - pregame-pa-ext-v1 scoring step

**Card:** pregame-pa-ext-v1 (`research/offseason_2026/pregame_pa_ext`)
**Attempt ID:** full_run-1
**Failed attempt date:** 2026-10-14
**Status:** first scoring execution FAILED; fix applied with regression
tests; the scoring step is to be re-run ONCE with this fix. No registered
quantity was tuned or re-chosen.

## What failed

First execution of `scripts/score_pa_ext.py` crashed with:

    polars.exceptions.ColumnNotFoundError: "uniq_h3_rps" not found

at score_pa_ext.py, in the secondary descriptive bootstrap
(`{tag}_minus_v3uniq_{base}_{metric}` comparisons).

Evidence (preserved, read-only):

- Run log:
  `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v1\outputs\full_run\scoring_run_log.txt`
- sha256: `07410807694f61bd4129ac4ed000164c2c24aa86578968861d333fe0428fcf6f`
- The log is a UTF-16 PowerShell transcript; do not rewrite or re-encode it.

## Cause

The `uniq_{h3,l5}_{rps,logscore}` comparison columns are attached to `cmp`
(the v3 metrics join built inside the machinery-equivalence gate) and are
never propagated to `lab`. The secondary bootstrap's `paired()` helper read
BOTH sides of every comparison from `lab`, so the two `*_minus_v3uniq_*`
comparisons referenced columns that do not exist on `lab`.

## What completed before the crash

The crash preceded ALL output writes; NO result artifacts were written.
The following completed in memory:

- payload sha256 check (PASS, `19511a492767ca06...`, matches manifest);
- label join (7,194 starts; the 7,194-row height assert implies 0
  exclusions);
- per-start metric computations (count-RPS, log score, mean-K squared
  error, milestone Briers, for both registered RAW arms);
- machinery bit-identity gate vs the accepted v3 uniq arms (PASS -- this
  PASS line is what the preserved log displayed; any other displayed
  numeric results are disclosed in the preserved log itself, not
  re-enumerated here).

No `report_scored.json`, `start_metrics_paext.parquet`, or
`scoring_summary.txt` was produced; the output directories are empty.

## Changed code (this fix, commit-scoped)

- `scripts/score_pa_ext.py`:
  - the two secondary comparisons now read the `uniq_*` side from `cmp`
    (new `paired_uniq()` helper alongside the unchanged `paired()`); and
  - `lab` and `cmp` are both sorted on the full start key
    (`game_date, game_pk, side, pitcher`) and an explicit key-alignment
    assert (cmp keys == lab keys, same order) runs before the bootstrap, so
    the raw-arm rows and the uniq_* comparison columns are guaranteed to
    pair start-for-start.
- Unchanged: payload, cohort, labels, arms, per-start metrics, bootstrap
  settings (2000 resamples, seed 20261001, slate-date unit), and all gates
  (including the <=1e-12 machinery bit-identity gate).
- New regression tests: `tests/test_score_pa_ext_regression.py` —
  (a) reproduces the missing-column failure of the old lab-read path;
  (b) exercises the fixed cmp-based pairing with the key-alignment guard
  (both arms resampled over the same slate dates; misaligned cmp rejected);
  (c) runs the FULL scorer end-to-end in a temp directory and asserts
  report.json + start_metrics + scoring_summary all exist and are finite.

## Note on copies

This fix is in the repo copy of the card code. The lake copy
(`C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v1\scripts\score_pa_ext.py`)
is byte-identical to the PRE-fix version and still carries the defect; sync
it from the repo before any re-run launched from the lake tree.

## PROVENANCE CORRECTION - manifest `paext_core.py` hash (recorded 2026-10-14)

**Summary:** `manifest.json` `inputs_sha256["scripts/paext_core.py"]` records
`982782bcf2d82d3622e35f3b047b6374933fe007b7fee9ee7774d7eedb250dd7`, but the
actual reviewed lake file hashes
`e193cd180a29ae3d434b0f545f66ab609a51a00bc750b0f5f2e671deec5bcdde`
(17,851 bytes, LF-only, 410 lines). Reason: the manifest captured a STALE
hash of an earlier working-tree draft of `paext_core.py` and was not
refreshed after the file's final save. This entry is superseded for that
one key; the actual build-time module is proven to be the current
`e193cd18...` file (evidence below). The frozen payload is unaffected.

| item | value |
| --- | --- |
| originally recorded hash (manifest) | `982782bcf2d82d3622e35f3b047b6374933fe007b7fee9ee7774d7eedb250dd7` |
| actual hash (lake + repo + git) | `e193cd180a29ae3d434b0f545f66ab609a51a00bc750b0f5f2e671deec5bcdde` |
| reason | stale hash capture of a pre-final-save draft; not refreshed at manifest write |
| old version recoverable? | NO (see recovery search below) |
| current file produced the frozen payload? | YES (bytecode evidence below) |

### Recovery search (old `982782bc` version NOT recoverable)

- `git rev-list --all --objects` filtered for the path returns exactly ONE
  blob ever committed for
  `research/offseason_2026/pregame_pa_ext/scripts/paext_core.py`:
  `bc7de30ff06adb578cbf8d01966e84e986346262`, whose content hashes
  `e193cd18...` at BOTH 99a0796 and dfd8f17 and is byte-identical to the
  lake copy (17,851 bytes, 0 CR, 410 LF).
- `git fsck --unreachable` (12 unreachable blobs, all hashed): no blob
  matches `982782bc...`. No backup/lake path holds a second version.
- Line-ending artifact excluded: the CRLF variant of the current file
  hashes `7769a0fe64cad412ac3dca676b8a62a3b3899430c788c3dda7e3f8a0568e5c74`
  (18,261 bytes), not `982782bc...`. So the recorded hash corresponds to a
  genuinely different (edited) draft, not a newline re-encoding.

### Equivalence evidence (current file IS the build-time module)

- Build-time bytecode
  `lake/scripts/__pycache__/paext_core.cpython-311.pyc` embeds source
  mtime 1792002142 (= 2026-10-14 18:22:22 UTC) and source size 17,851 --
  both matching the current lake file exactly.
- A fresh `compile()` of the current lake `paext_core.py` produces a
  marshaled code object BYTE-IDENTICAL to the code object stored in that
  build-time `.pyc`. Therefore the module imported/executed during the
  payload build was exactly the current `e193cd18...` file.
- Timeline: the source file was last saved 18:22:22 UTC; the manifest was
  written 18:26:50 UTC but carried the earlier draft's hash -- the hash was
  captured before the final save and not refreshed.
- Build path logic matches the current file: `build_pa_ext.py` (hash
  `d35ad47e08526d9171fd166cf81e7fc7c5a1d7243389bc3e20e813f65384d9d1`,
  matching the manifest) does `import paext_core as core` and copies
  `scripts/paext_core.py` into the build workdir (line 246).
- Frozen payload re-verified untouched:
  `data/predictor_payload.parquet` = `19511a492767ca061f216bf0a1679e94a77706b2737aea4cf1ab93c312b58a96`
  (matches manifest).
- Side observation (out of scope, no action): the build-time
  `build_pa_ext.cpython-311.pyc` records source size 18,541 vs the current
  18,585-byte file, i.e. that script was also touched after the build; its
  manifest hash matches the CURRENT file and the payload hash re-verifies,
  so no payload-provenance impact is claimed from it.

### Preservation

The original `manifest.json` and the full_run-1 failure log
(`outputs/full_run/scoring_run_log.txt`, sha256
`07410807694f61bd4129ac4ed000164c2c24aa86578968861d333fe0428fcf6f`) are
preserved unmodified. NO payload rebuild was performed.

## ATTEMPT-RECORD CORRECTIONS (recorded 2026-10-14, post full_run-2 review)

Two corrections to this note's own attempt records, made during the
full_run-2 post-run review. Both are documentation-only; no code, payload,
or output was touched.

### D-A -- what full_run-1 actually completed and displayed

Correction of the earlier "What completed before the crash" section, which
wrongly said nothing was computed or displayed. Accurate statement:

> Attempt full_run-1 completed the label join, the per-start metric
> computations, and the machinery bit-identity gate in memory before
> failing. No result artifacts were written. The log displayed the
> machinery gate PASS; any other displayed numeric results are disclosed
> in the preserved log
> (`C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v1\outputs\full_run\scoring_run_log.txt`,
> sha256 `07410807694f61bd4129ac4ed000164c2c24aa86578968861d333fe0428fcf6f`).

Rule going forward: absence of output files is NOT evidence of absence of
computation, and "nothing was displayed" must never be claimed without
reading the preserved log. The body section above has been edited to match
this statement; the log itself is untouched.

### D-B -- manifest `paext_core.py` stale source hash (already detailed above)

Concise restatement for the attempt record:

> The manifest recorded `paext_core.py` hash
> `982782bcf2d82d3622e35f3b047b6374933fe007b7fee9ee7774d7eedb250dd7`; the
> actual reviewed committed/lake bytes hash
> `e193cd180a29ae3d434b0f545f66ab609a51a00bc750b0f5f2e671deec5bcdde` --
> a stale source-hash entry. Equivalence checks (pyc size/mtime/compile
> match, detailed in the PROVENANCE CORRECTION section above) found no
> payload change. Original manifest preserved (sha256
> `dbb272e69622e1915873056ac69582aa5dab85ccdefbc9747c96b36a8e499a2e`);
> full hashes recorded here and in that section.

The stale entry is superseded for that one manifest key only; no other
manifest hash was implicated.
