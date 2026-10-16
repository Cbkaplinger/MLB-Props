# Results Index Design (v1)

**Status:** draft for review. This index is **not a source of truth** until
Chat 2 reviews it. The canonical artifacts it points to remain authoritative.

**Generator:** `tools/generate_results_index.py` (stdlib + polars only)
**Outputs:** `docs/RESULTS_INDEX.md`, `docs/RESULTS_INDEX.csv`,
`docs/RESULTS_INDEX_COVERAGE.md`
**Tests:** `tests/test_results_index.py`

## What it does

Builds one machine-generated index of declared run metadata across the repo
experiment lanes and the research lake. One row per registered entry
(14 registered: 5 repo experiments, 9 lake lanes), with:

- batch/run ID + status (from recorded status fields only)
- code/config/input identity (hashes where the metadata records them)
- population/estimand, candidate/reference
- principal metric + contrast (from declared JSON paths, with provenance)
- independent-review status, taken from recorded review artifacts/verdicts;
  `MISSING` where none is recorded
- artifact path/hash pointers
- result class: development-only / confirmation / diagnostic /
  eligible-for-promotion / nonconforming / superseded

## Scan scope (declared, exhaustive)

Only these metadata sources are read; nothing else is globbed or discovered:

- `research/offseason_2026/experiments/*/card.json` + `metrics.json` +
  `paired_comparisons.json` (repo experiments)
- lake `first-run-v1` and `recency-batch-v1` write-once frozen run dirs
  (`run_manifest.json`, `metrics.json`) plus their recorded status/review
  JSONs (`ablation_row_v3_status.json`, `lake_mirror_status_v2.json`,
  `reconciliation_c1_c4.json`)
- `lgbm-equal-info-v2/execution_receipt.json`
- `bf-lane-v1/MANIFEST.json` + `b1_registration.json`
- `pregame-pa-ext-v1/manifest.json` + `report.json` (+ review marker file)
- `count-eval-v1/EXECUTION_MANIFEST.json` + `freeze_lgbm_equal_info_v1.json`
- `market-eval-v1/outputs/score_v2/score_manifest.json` + `confirm_metrics.json`
- `seal-package-preflight/seal_manifest.json` + `SEAL_RECEIPT.json`
- `bf-2026-predictor-seal-v1/seal_manifest.json` + `seal_prep_report.json`

## Rules

1. **Declared extraction, recorded provenance.** Every value is copied from a
   declared file at a declared JSON path. The CSV `provenance` column records
   `file_role:json.path` for each extracted field. Nothing is scraped from
   prose; markdown files are used only as declared verdict *markers* (e.g.
   `REVIEW_SUPERSESSION.md` sets review status SUPERSEDED for that card's
   scope; the numbers inside it are not extracted).
2. **MISSING is a value.** Absent metadata is recorded as `MISSING`, never
   defaulted or guessed. Two honest gaps this surfaces: 8 entries have no
   recorded independent-review verdict artifact, and 6 entries carry no
   principal metric (frozen-not-executed registrations, seal preps with
   outcome access none, and runs whose metric files sit outside the declared
   scan set).
3. **Coverage is closed.** Every registered entry is INDEXED or EXCLUDED with
   a reason in `RESULTS_INDEX_COVERAGE.md`; registry integrity is tested.
4. **Result classes carry evidence.** Each class assignment cites the recorded
   structured field that justifies it (`result_class_evidence` column).

## What it intentionally does NOT do

- **Not a source of truth.** It copies recorded metadata; Chat 2 must review
  it before anything downstream may rely on it.
- **No results from prose.** No metric is extracted from any markdown file.
- **No undeclared scanning.** It does not glob experiment directories, run
  outputs, MLflow stores, or the rest of the lake; undeclared artifacts
  (e.g. `bf-2026-eval-v1-outputs/report.json`, corrected-RMSE reports) are
  pointed at, not parsed.
- **No judgment.** Review status MISSING means "no verdict artifact
  recorded", not "not reviewed" or "rejected". Result classes restate
  recorded classifications; the index makes no new eligibility calls.
- **No live-path change.** Docs/tooling only; no production scorer, policy
  JSON, schedule, or ledger is touched.

## Scope deviations (recorded, not repaired)

- Repo cards are `card.json`; no `card.md` exists in the declared experiments
  directory.
- `run_manifest.json` exists only inside the executed batches' frozen run
  dirs; it is scanned there.
- No repo `freeze_*.json`; frozen registrations in scope are lake-side.
- `lgbm-equal-info-v1` (frozen, never executed) is reachable only through
  `count-eval-v1`'s freeze file and is not a separate indexed run.

## Regenerate

```powershell
python tools/generate_results_index.py
# optional overrides:
python tools/generate_results_index.py --repo-root . --lake-root C:\Users\ckaplinger\MLB-Props-Research --out-dir docs
python -m pytest tests/test_results_index.py
```

The lake root defaults to `C:\Users\ckaplinger\MLB-Props-Research` and may be
overridden with `--lake-root` or `MLB_PROPS_RESEARCH_LAKE`; when it is absent
(CI), lake entries are excluded with a reason and the tests still pass.
