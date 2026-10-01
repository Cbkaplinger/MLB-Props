# ADR-0007: Research-only MLflow tracking mirror

- **Status:** Accepted (owner decision 2026-09-30; implementation NOT STARTED)
- **Date:** 2026-09-30
- **Acceptance record:** Owner approved the research-mirror boundary as specified;
  implementation remains separately gated (no install, adapter, import, or rerun
  authorized by this ADR). Filename retained as `PROPOSED-mlflow-research-mirror.md`
  because the backlog Session Snapshot, FORWARD item, and the Phase 8.5 truth-sync
  report already reference this path; renaming would churn three cross-session
  references for no semantic gain. Production status: NOT USED. Promotion
  authority: NONE. Canonical evidence remains outside MLflow. Next gate: separately
  approved implementation card. Known specification gap carried to implementation:
  same card-and-arm re-import idempotency is implied by the run-identity scheme but
  not stated as an explicit rule (see truth-sync report).
- **Context:** The PA-overhaul program (Phases 4–8) produced seven experiment families tracked
  exclusively through immutable cards, manifests, hashes, predictions, deviations, and durable
  reports. Comparisons are valid but manual: answering "which arm beat which baseline on which
  block" requires opening several JSON files. The owner approved a tracking-mirror decision at
  the Phase 8 checkpoint; MLflow was deferred during Phase 8 (not installed) to avoid
  environment churn before a registered evaluation. Experiment artifacts themselves are
  immutable and hash-pinned; only the *indexing* layer is missing.
- **Decision:** Adopt MLflow as a **research-only, read-mostly tracking mirror** over the
  existing artifact system. Local SQLite backend, explicit local artifact root, one writer.
  Existing cards, dataset/split/feature manifests, hashes, deviations, bundles, and reports
  remain the canonical source of truth; MLflow indexes and displays them. No production
  loading from MLflow, no automatic promotion, no Model Registry, no retrospective reruns.
- **Alternatives:**
  - *Continue with manifests only:* valid but loses cross-run querying and UI comparison as the
    experiment count grows; rejected as insufficient for the count-distribution and 2025
    validation phases ahead.
  - *Hosted MLflow server:* rejected — single-writer personal project, no multi-user need, adds
    auth/ops burden and a network dependency to research.
  - *Model Registry now:* rejected — nothing is promoted through MLflow; production loading
    stays file-pointer-based (`live_krate_ensemble.json`, `artifacts/models/`). Revisit only if
    multi-writer or remote execution arrives.
  - *Weights & Biases / other SaaS:* rejected — external dependency, data egress, account
    requirement; contradicts research isolation.
- **Consequences:** New dependency added to the dev/research extras only (never production
  requirements). `mlflow.db` and the artifact root live outside Git (ignored). Historical
  experiments are imported as metadata-only runs (see mapping below), never re-executed.
  MLflow failure is nonfatal: canonical outputs stand alone. Version pinned at adoption with a
  documented upgrade procedure. If the mirror is later removed, the canonical artifacts are
  unaffected (rollback = delete db + artifacts + dev extra).
- **Evidence (for the decision record; promotion to Accepted requires owner sign-off):**
  - Phase 8 preflight: mlflow absent from environment (verified 2026-09-30).
  - `docs/EXECUTION_BACKLOG.md` FORWARD item 3 (MLflow ADR owner decision).
  - Phase 7/8 output hashes: `experiments/logistic_pa/output_hashes.json`,
    `experiments/tree_pa/output_hashes.json` (verified intact 2026-09-30).
- **Source-of-truth hierarchy:** cards/manifests/hashes/reports > MLflow db. MLflow tags point
  AT canonical files; they never substitute for them.
- **Run identity:** `card_sha256[:12] + arm_id` (e.g. `95b9627d4351-T1`), stored as run name;
  `experiment_id` = experiment family (`TREE-PA-T`, `PA-OVERHAUL`, …).
- **Historical-import policy:** one metadata-only import per existing experiment family, tagged
  `run_origin=historical_import`, `metrics_origin=immutable_artifact`,
  `execution_replayed=false`, `promotion_eligible=false`. Metrics copied from metrics.json;
  prediction/bundle files referenced by path + sha, not copied.
- **Mapping (specification only — not implemented):**

| Existing object | MLflow object |
| --- | --- |
| Experiment family | Experiment |
| Card ID + arm ID | Run name + tags |
| Card parameters (grid, folds, gates) | Params (flat, dotted keys) |
| Dataset/split/feature manifest hashes | Tags (`ds_sha`, `split_sha`, `feat_sha`) |
| 2023 fold metrics | Metrics tagged `block=F1`/`block=F2` |
| 2024 E1/E2 metrics | Metrics `e1_logloss`, `e2_brier`, … |
| Bootstrap intervals | Artifact (paired JSON) + raw/CI summary metrics |
| Prediction parquet | Artifact reference (path + sha tag) |
| Bundle | Artifact reference; never registered for production |
| Deviations | Artifact + tag `deviations=non_substantive`/count |
| Verdicts | Tags (`tree_beats_l3=no`, `blend_justified=no`) |
| Git commit | Tag `git_commit` |
| Dirty-state manifest | Artifact |
| Historical import | Tag `run_origin=historical_import` |

  Nesting: Experiment → arm run → (fold metrics as tags on the same run; no per-fold child
  runs; no per-bootstrap runs — replicates stay inside the paired artifact). Naming: prefix
  every run with the arm token (P3/L1a/L1b/L2/L3/T1/T2/T3) so UI grouping mirrors the ladder.
- **Dataset/artifact lineage:** input sha table (hashes.json) logged as tags; parquet bodies
  referenced, not duplicated. Artifact root: `research/offseason_2026/mlflow_artifacts/`
  (gitignored) with the db at `research/offseason_2026/mlflow.db` (gitignored).
- **Writer policy / backup:** single agent writer per session; db is disposable — disaster
  recovery = re-run the metadata import (fast, deterministic from canonical artifacts); no
  separate backup regime needed.
- **Failure behavior:** any MLflow exception is caught, logged, and ignored by experiment
  runners; canonical outputs must be complete and hash-consistent before the mirror step runs.
- **Production boundary:** zero imports in `src/Python/` or `production/`; no schedule, cron,
  ledger, policy, or model-pointer change; production rollback target unchanged
  (`live_krate_ensemble.json` + `artifacts/models/`).
- **Security and secrets:** no credentials in MLflow (local file db, no server); no 2025/2026
  outcome data logged as params/metrics beyond what canonical artifacts already contain.
- **Revisit triggers:** multi-writer research, remote execution, or a promotion path that needs
  registry-style lineage → revisit Model Registry and/or hosted backend as a NEW ADR.
- **Rollback/removal:** `pip` uninstall (dev extra), delete `mlflow.db` + artifacts dir, drop
  the FORWARD item. Canonical experiment evidence untouched.
- **Related code:** none (research tooling only, when implemented:
  `research/offseason_2026/mlflow_mirror/`).
- **Related experiments:** PA-OVERHAUL Phases 4–8; all future experiment families
  (count-distribution, 2025 validation) would log natively.

## Amendment A1 (Phase 8.7, owner-ordered): acceptance modifications

### Deterministic run identity

Canonical run identity = `sha256(program | card_id | arm_id | dataset_manifest_hash |
split_definition_hash | feature_manifest_hash | model_spec_hash)[:16]`, rendered as
`<card_short_sha>-<arm_id>` for display. All seven fields must be present; any missing
field fails the import closed (no run created). The identity is recomputable by any
session from canonical artifacts alone.

### Duplicate-import idempotency

Importing an identity that already exists must create no duplicate logical run: return
the existing mirrored record after re-verifying its hashes (no-op reconciliation). If
canonical hashes disagree with the stored mirror, fail closed with an explicit
mismatch report — never overwrite conflicting data silently.

### Read-only historical imports

Historical import reads canonical artifacts only. It never runs training, scoring,
bootstrap, calibration, aggregation, or policy code. Every historical run carries
`run_origin=historical_import`, `execution_replayed=false`, `promotion_eligible=false`.
No historical import may create, modify, or delete any file under an experiment
directory — violations fail the import.

### Canonical reconciliation command

The implementation must expose one reconciliation entry point (adapter function or CLI)
that, per mirrored run, checks: run identity recomputation, card hash, all manifest
hashes, logged params vs card, logged metrics vs metrics files, artifact references vs
paths+hashes on disk, import metadata completeness. Output: PASS/FAIL per check with
the offending digest on failure. No implementation path is invented here; the interface
above is the requirement the implementation card must satisfy.

### Portable export format

Export = one JSON document per run (schema version `mlflow-mirror-export/v1`): run
identity, tags, params, metrics, canonical artifact references (path + sha256),
import metadata, export timestamp, exporter version. Export is a disaster-recovery and
audit convenience; it does not replace canonical experiment artifacts and must never
be re-imported as a substitute for them.

Status after amendment: **ACCEPTED (implementation NOT STARTED; production usage NONE;
registry authority NONE; promotion authority NONE).** This ADR must not be marked
IMPLEMENTED until the mirror passes import, reconciliation, and export tests on a
metadata-only smoke run.
