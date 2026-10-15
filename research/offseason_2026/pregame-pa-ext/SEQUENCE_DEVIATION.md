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
