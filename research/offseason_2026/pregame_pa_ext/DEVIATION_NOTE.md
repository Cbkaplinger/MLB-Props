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

The crash preceded ALL output writes; NO metrics were computed or displayed
from the run. Only the following completed, in memory:

- payload sha256 check (PASS, `19511a492767ca06...`, matches manifest);
- label join (7,194 starts; the 7,194-row height assert implies 0
  exclusions);
- machinery bit-identity gate vs the accepted v3 uniq arms (PASS).

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
