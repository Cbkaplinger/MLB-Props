# SEQUENCE DEVIATION -- first-run-v1 (packet first-run-v1-e59da946da21)

Written: 2026-10-15T13:19:51Z (UTC). Author: research agent, per owner
instruction. This is the standing record for the first-run-v1 canonical
candidate run; it is a work-state record, not a retraction of any artifact.

## What happened

The canonical first-run-v1 scoring run was executed in the lake
(`C:\Users\ckaplinger\MLB-Props-Research\first-run-v1\0cda7bdd4b9edbdcf395a5cd8d7a96164b066bd71c9d71cc034ff6a5eba19f57\`)
BEFORE Chat 2's exact-SHA READY verdict was issued. Execution should have been
gated on that verdict. The execution therefore lacked pre-execution review
authorization. This is recorded as a ONE-TIME exception granted by the owner;
it does not establish precedent for any future run.

## Established chronology (machine evidence)

| Event | Time (UTC) | Evidence |
| --- | --- | --- |
| Commit b2be3c9c6a3f29d47f44b2c769bd933023491d4e | 2026-10-15T05:13:51Z | committerdate (`git log -1`), branch research/market-eval-v2 |
| Push of b2be3c9 to origin | exact second NOT recorded; bounded to (2026-10-15T05:13:51Z, 2026-10-15T05:19:35Z] | CI run 38686174356 (`pull_request`, head_sha b2be3c9, success) created_at 2026-10-15T05:19:35Z -- https://github.com/Cbkaplinger/MLB-Props/actions/runs/38686174356 |
| Canonical run execution | 2026-10-15T05:20:07.741772Z | in-band `run_manifest.json` created_utc; preds file mtimes 05:20:07Z..05:20:29Z |
| Ablation row generated (builder-side) | 2026-10-15T05:24:21Z | `ablation_row.json` row_generated_utc |
| Remote ref verification (current) | 2026-10-15T13:16:07Z | `git ls-remote origin research/market-eval-v2` returned b2be3c9c6a3f29d47f44b2c769bd933023491d4e |

## Publication chronology -- what is established vs not

- ESTABLISHED: commit (05:13:51Z) and the CI run created by the push
  (05:19:35Z) both PRECEDE the in-band execution timestamp (05:20:07Z). On the
  machine evidence, the code was committed and pushed before the run executed.
- NOT ESTABLISHED: the exact push second (no push timestamp is recorded
  anywhere; reflog and ref dates carry the commit date, not push time). Push
  time is only bounded by the CI run creation time above.
- DISCREPANCY RECORDED: the prior session's asserted execution time of
  "2026-10-14 23:44 UTC" is NOT supported by any first-run-v1 artifact. The
  in-band manifest and file mtimes agree on 2026-10-15T05:20:07Z. The 23:44
  timestamp matches the EARLIER market-eval scoring run (run 108d5ba9, commit
  3fce43d: "executed once at 108d5ba9 (2026-10-14 23:44 local)") and appears
  to have been conflated with this run. Both timestamps are recorded here; the
  2026-10-15T05:20:07Z value is the established one for first-run-v1.
- A remote-ref match verified today (13:16:07Z) proves nothing by itself about
  publication order; it is recorded only as current-state evidence.

## Missing authorization

Execution preceded Chat 2's exact-SHA READY verdict. No pre-execution review
authorization existed at the moment the run started. Owner ruling: one-time
recorded exception; the run is NOT treated as a precedent and the review gate
remains binding for every future canonical run.

## Owner decision

The run is PROVISIONALLY RETAINED as the sole candidate canonical run for the
first-run packet, SUBJECT TO successful independent post-execution
reconciliation. If reconciliation fails, the run loses its provisional status
and the packet must be re-run under the intact review gate.

## Known result exposure

Because the run executed before review, the builder saw the complete results
before any independent reviewer did: all four fold eval-identity hashes
(1b83c74d..., f91cd91c..., 1330d0cd..., da1d29d4...), the pooled-dev and
per-fold metrics, and the paired bootstrap CIs. The ADOPT-SIGNAL decision in
`ablation_row.json` was written by the builder at 2026-10-15T05:24:21Z, before
review. This exposure is the reason the status correction below exists.

## Status correction (versioned, no in-place edits)

- `ablation_row.json` is FROZEN and preserved unmodified
  (sha256 d8540f559ee810557eaefa387ed6e75dd7d58390c0a7ca595ba240a798de605a).
  Its `decision.verdict` value "ADOPT-SIGNAL" is SUPERSEDED-BY-V2-STATUS and
  must not be read as an adoption claim.
- `ablation_row_v2_status.json` (this directory) carries the corrected
  decision: RESULT-PENDING-INDEPENDENT-REVIEW, with a pointer to this record.
- Checked for embedded status: `metrics.json`, `metrics.md`, and
  `derived_lane_check.json` in the run dir contain no decision/verdict text,
  so no versioned reporting-correction file is needed for them.

## Artifacts referenced

- Frozen run dir sha256 of run_manifest.json: 897070f8acc593038a8f37126e1693d3a5f25389ce3e4b7d941592db817711c9
- Frozen run dir sha256 of metrics.json: e0d590870b8a400c341c3da2b0bd12c122b83ae60f8dc5306146495aa08f52e4
- Implementation commit: b2be3c9c6a3f29d47f44b2c769bd933023491d4e (research/market-eval-v2)
- Repo copy of this record: research/offseason_2026/pregame-pa-ext/SEQUENCE_DEVIATION.md (commit-only; not pushed)

## Addendum 2026-10-15: MLflow import completed (non-authoritative)

The post-run MLflow importer ran successfully against the frozen canonical run
(the importer is downstream bookkeeping only; it does not touch the canonical
outputs). Details are in `mlflow_import_record.json` (this directory):
mlflow 3.17.1, experiment `pa-k-probability-v1`, parent run
e2194b6b0f7c4f1da59db2a967af1e2b tagged with the packet run_id, git_sha,
config_hash, harness_run_id, exposure and review_status
(RESULT-PENDING-INDEPENDENT-REVIEW); 20 child runs (candidate x fold x lane)
with params + metrics; idempotency added to the importer and verified by a
second import (no duplicate). Import window: 2026-10-15T13:29:57Z..13:29:59Z.

## Addendum 2026-10-15 (second): post-execution reconciliation pass (non-authoritative)

All work below is downstream bookkeeping over the frozen canonical outputs;
nothing in the frozen run dir was modified (run_manifest.json + metrics.json
hashes re-verified unchanged by OUTPUT_INVENTORY.json). Result status remains
RESULT-PENDING-INDEPENDENT-REVIEW; independent review is still owed.

- AUTHORITATIVE ABLATION RECORD generated mechanically from the frozen
  artifacts: `ablation_record_authoritative.json` (lake: first-run-v1; repo
  mirror: this directory) via `generate_ablation_record_authoritative.py`.
  Field groups: identity / candidate / chronology / population / fitting /
  calibration / scores / comparisons / robustness / decision / evidence.
  decision.verdict is COPIED VERBATIM from ablation_row_v2_status.json =
  RESULT-PENDING-INDEPENDENT-REVIEW (not decided by the generator).
- SUPPLEMENTAL RAW + CALIBRATED metrics from the saved preds parquets:
  `generate_supplemental_metrics.py` -> `supplemental_metrics.json` +
  `supplemental_metrics.md`. RAW lane first verified: recomputation from all
  12 preds parquets reproduces metrics.json BIT-EXACTLY (12/12 checks, max
  |delta| = 0.0 for log loss and Brier; numpy-mean and polars-mean both exact).
  CAL lane computed per fold + pooled dev; P0_log5 CAL lane UNDEFINED (no
  calibrator; pred_cal all null in all 4 folds). CAL is derived point
  estimates only, no CIs; metrics.json remains canonical.
- OUTPUT INVENTORY: `OUTPUT_INVENTORY.json` (lake; repo mirror) - all 15 files
  in the frozen run dir hashed with sizes + mtimes; declared external hashes
  for run_manifest.json (897070f8...) and metrics.json (e0d59087...) both
  MATCH. The original manifest is referenced, not rewritten.
- LAKE MIRROR STATUS: `lake_mirror_status.json` (lake; repo mirror) - the
  canonical run dir exists ONLY in the lake (CANONICAL-ONLY-IN-LAKE); no
  mirrors found anywhere (repo, worktrees, rest of MLB-Props-Research), so
  there are no stale mirrors to mark.
- MLFLOW RECONCILIATION against the SAME canonical run dir:
  `mlflow_reconcile.py` -> `mlflow_reconciliation.json` (lake; repo mirror).
  tracking_uri sqlite:///C:/Users/ckaplinger/MLB-Props-Research/mlflow.db;
  experiment pa-k-probability-v1 (experiment_id 1); parent run
  e2194b6b0f7c4f1da59db2a967af1e2b (FINISHED, tagged run_id / git_sha /
  config_hash / harness_run_id / exposure / review_status). Children: 20 =
  12 raw (3 candidates x 4 folds) + 8 cal (2 fitted candidates x 4 folds;
  P0_log5 has NO calibrator - pred_cal all null in all 4 folds - so its 4
  CAL children do not exist). VERIFICATION: every child's logged log_loss /
  brier / n recomputed from the frozen preds parquets (pred_raw for raw
  lanes, pred_cal for cal lanes; tolerance 1e-9): 20/20 MATCH, 0 mismatch.
  Observed discrepancy recorded, not repaired: artifact URIs are declared in
  mlflow.db but ./mlruns was never materialized on disk (importer logged
  params/metrics/tags only, no artifacts).
- TIMESTAMPS PRESERVED SEPARATELY (three clocks, never merged): execution =
  run_manifest.json created_utc 2026-10-15T05:20:07.741772Z (in-band); MLflow
  import window = parent start/end 2026-10-15T13:29:57.149Z..13:29:59.036Z
  plus mlflow_import_record.json written_utc 13:35:00Z; environment =
  environment_pip_freeze_2026-10-15.txt (pip freeze of the repo venv, captured
  post pyarrow restoration; lake, sha recorded in mlflow_reconciliation.json).
- PYARROW DEPENDENCY CHANGE VERIFICATION (sequence 24.0.0 -> 25.0.1 ->
  restored 24.0.0; the 25.0.1 bump was pulled in by the mlflow 3.17.1 install
  via the streamlit pin, then corrected back; venv confirms 24.0.0):
  (1) `pip check` output: "streamlit 1.61.1 has requirement starlette<1.4.0,
  >=0.46.0, but you have starlette 1.6.0" - this conflict is PRE-EXISTING
  (starlette-1.6.0.dist-info dated 2026-08-14, before the 2026-10-15 mlflow
  install) and was NOT introduced by the pyarrow/mlflow change; no other
  conflicts reported. (2) Parquet round-trip with pyarrow 24.0.0 PASS
  (`parquet_roundtrip_pyarrow24.py`: identical schema + 1000 rows/values incl.
  an all-null pred_cal column, via both polars and pyarrow.parquet).
  (3) Synthetic harness suite PASS: pytest
  research/offseason_2026/specs/count-eval-v2-spec/harness/test_comparison.py
  -> 25 passed in 28.62s.
- REPO MIRRORS of the new records are committed additively in this directory
  (byte-identical copies of the lake files): ablation_record_authoritative.json,
  supplemental_metrics.json, supplemental_metrics.md, OUTPUT_INVENTORY.json,
  mlflow_reconciliation.json, lake_mirror_status.json. Generator scripts
  remain lake-only per precedent (generate_ablation_row.py, mlflow_import.py).
