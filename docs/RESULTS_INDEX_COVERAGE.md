# Results Index Coverage Report

Registered entries: 14; indexed: 14; excluded: 0.
Every registered experiment is either indexed below or explicitly excluded
with a reason. Registered = declared in `tools/generate_results_index.py`.

| entry | disposition | reason / detail |
| --- | --- | --- |
| repo:logistic_pa | INDEXED | indexed from declared metadata |
| repo:pa1a_raw_pa | INDEXED | indexed from declared metadata |
| repo:pa1b_oracle_xk | INDEXED | indexed from declared metadata |
| repo:pitcher_prior | INDEXED | indexed from declared metadata |
| repo:tree_pa | INDEXED | indexed from declared metadata |
| lake:first-run-v1 | INDEXED | indexed from declared metadata |
| lake:recency-batch-v1 | INDEXED | indexed from declared metadata |
| lake:lgbm-equal-info-v2 | INDEXED | indexed from declared metadata |
| lake:bf-lane-v1 | INDEXED | indexed from declared metadata |
| lake:pregame-pa-ext-v1 | INDEXED | indexed from declared metadata |
| lake:count-eval-v1 | INDEXED | indexed from declared metadata |
| lake:market-eval-v1-score-v2 | INDEXED | indexed from declared metadata |
| lake:seal-package-preflight | INDEXED | indexed from declared metadata |
| lake:bf-2026-predictor-seal-v1 | INDEXED | indexed from declared metadata |

## Scope deviations (recorded, not repaired)

- Repo experiment cards are `card.json` (no `card.md` exists in `research/offseason_2026/experiments/`); the declared card path is the recorded JSON card.
- `run_manifest.json` exists only inside the write-once frozen run dirs of executed harness batches (first-run-v1, recency-batch-v1); it is scanned there, not at batch top level.
- No `freeze_*.json` files exist in the repo; the frozen registrations in scope are lake-side (`freeze_lgbm_equal_info_v1.json`, `b1_registration.json`, seal manifests).
- Scoring/output reports (`report.json` under run dirs, `bf-2026-eval-v1-outputs/report.json`, corrected-RMSE reports) are outside the declared metadata set; entries whose only metrics live there carry principal_metric = MISSING with a pointer instead of pulling numbers from undeclared files or prose.
- `lgbm-equal-info-v1` (frozen, not executed) is reachable only through count-eval-v1's freeze file; it is not a separate indexed run.

## Known gaps surfaced (not fixed by this index)

- Entries with `review_status = MISSING` have no recorded independent-review verdict artifact; they are flagged, not judged.
- Entries with `principal_metric = MISSING` either did not execute (frozen registrations, seal preps with outcome access none) or keep their metrics in artifacts outside the declared scan set.
