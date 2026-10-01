# MLflow Mirror Implementation Card (DRAFT — NOT AUTHORIZED FOR IMPLEMENTATION)

Status: **DRAFT**. Parent decision: ADR-0007 (ACCEPTED, Amendment A1).
Prerequisite: C2–C5 shared documentation corrections landed. Do not implement from
this draft without owner card review plus the acceptance gates at the end.
Implementation: NOT STARTED.

## Purpose

Create a read-only, reproducible MLflow mirror of existing canonical PA experiments.
MLflow is a convenience index and UI, not the source of truth and not a replacement
for Git-tracked cards, manifests, hashes, metrics, or durable experiment records.

## Location

- Adapter code (when authorized): `research/offseason_2026/mlflow_mirror/`
- Local state: `research/offseason_2026/mlflow.db`, `research/offseason_2026/mlflow_artifacts/`
- `.gitignore` already covers `mlruns/` and `mlartifacts/` but NOT these exact paths:
  the implementation card must add `research/offseason_2026/mlflow.db` and
  `research/offseason_2026/mlflow_artifacts/` to `.gitignore` and the gate review must
  verify it before any import runs.

## Identity (ADR-0007 A1, exact)

`sha256(program|card_id|arm_id|dataset_manifest|split_def|feature_manifest|model_spec)[:16]`,
display `<card_short>-<arm>`. All seven inputs are recomputable from committed
artifacts; any missing input fails the import closed. Never substitute the older
`card_sha[:12]+arm` preview.

Normalization and serialization rules (deterministic across machines; all hashes are
lowercase hex digests of bytes):
- `program`: literal ASCII string (e.g. `PA-OVERHAUL`), no whitespace folding.
- `card_id`: full SHA-256 of the canonical card file bytes (e.g. `tree_pa/card.json`).
- `arm_id`: literal arm token from the card (e.g. `T1`); case-sensitive.
- `dataset_manifest`: full SHA-256 of the dataset manifest file bytes
  (e.g. `datasets/pa_dataset_manifest.json`).
- `split_def`: SHA-256 of the card's split-definition subsection serialized as
  canonical JSON (`sort_keys=True`, `separators=(',',':')`, UTF-8).
- `feature_manifest`: full SHA-256 of the feature-manifest file bytes
  (e.g. `logistic_pa/bundle/feature_manifest.json`).
- `model_spec`: SHA-256 of the frozen arm specification (hyperparameters, coefficients
  reference, seed, determinism flags) as canonical JSON with the same rules.
- Join the seven strings with single `|` (U+007C), encode UTF-8, SHA-256, take the
  first 16 hex characters. Display short = first 12 hex chars of `card_id`.

Worked example (computed 2026-09-30 from committed files, recomputable):
`TREE-PA-T / T1` → identity `5e021b6da4344aaa`, display `95b9627d4351-T1`.
Inputs: program `PA-OVERHAUL`; card sha `95b9627d43…` (`tree_pa/card.json`);
dataset manifest `fcf8603e55…` (`datasets/pa_dataset_manifest.json`); split-def hash
of `fold_design_2023` canonical JSON; feature manifest `faf585df76…`
(`logistic_pa/bundle/feature_manifest.json`); model-spec hash of the frozen T1
configuration (best grid point + lr 0.05 + 200 rounds + seed 0).

## Idempotency

Same identity → locate existing run → recompute and compare all identity inputs and
recorded digests → all agree: verify, then no-op → any disagree: fail closed with the
offending field and expected/actual digest. Never duplicate a same-card/same-arm run;
never overwrite a mismatched run.

## Read-only boundary

May read: cards, manifests, metrics, hash files, small reports, artifact references.
Must never: train, score, recreate predictions, bootstrap, recalibrate, aggregate,
run policy selection, import from `src/` or `production/`, write under canonical
experiment directories, or modify canonical evidence. Required tags on every
historical run: `historical_import=true`, `training_executed=false`,
`canonical_output_modified=false` (plus ADR tags `run_origin=historical_import`,
`execution_replayed=false`, `promotion_eligible=false`).

## Mapping (initial import scope: PA-OVERHAUL families)

| Canonical object | Mirror target |
|---|---|
| Experiment family (`PA-1A`, `PITCHER-PRIOR`, `PA-1B-O`, `LOGISTIC-PA`, `TREE-PA-T`) | MLflow experiment |
| Card ID + arm ID | run name `<card_short>-<arm>` + tags |
| Card grid/fold/gate sections | params (flat dotted keys) |
| Dataset/split/feature manifest shas | tags + identity inputs |
| 2023 fold metrics | metrics tagged `block=F1/F2` |
| 2024 E1/E2 metrics | metrics `e1_logloss`, `e2_brier`, … |
| Bootstrap CIs | artifact (paired JSON) + raw/CI summary metrics |
| Prediction parquets, bundles | artifact REFERENCES (path + sha tag); never copy large Parquets |
| Deviations | artifact + tag |
| Verdicts | tags |

Source commit recorded where available (currently `c58d9cb` lineage for PA evidence).

## Reconciliation

Per run return PASS/FAIL for: identity, card reference, dataset manifest, split
definition, feature manifest, model specification, parameters, metrics,
artifact-reference existence, recorded hashes. Failures name the offending field and
expected/actual digest.

## Export

`mlflow-mirror-export/v1`: one deterministic, diffable JSON record per run (identity,
tags, params, metrics, artifact references + hashes, import metadata, schema version).
Portable and suitable for reconciliation; not canonical evidence; not authority to
rerun; not automatically re-importable as proof.

## Failures (mirror must never corrupt canonical outputs)

Distinguish: import rejected (canonical evidence inconsistent) / MLflow unavailable
after canonical work complete (nonfatal, canonical evidence stands) /
export-reconciliation failure / digest mismatch (fail import closed). MLflow
availability never determines canonical validity.

## Tests (required before acceptance)

Stable identity · same-import no-op · digest-mismatch fail-closed · duplicate
prevention · read-only filesystem guard · forbidden-function/import guard · mapping ·
reconciliation PASS · reconciliation FAIL naming digest · deterministic export ·
nonfatal MLflow-unavailable · gitignore enforcement · no-PA-artifact-change proof.

## Rollback

Remove adapter, ignored SQLite db, ignored artifact dir, optional dependency. Leave
canonical evidence untouched.

## Explicit exclusions

Model Registry, deployment, serving, schedules, retraining, scoring, production
integration, policy selection, 2025-policy work, count-distribution modeling,
large-artifact migration, Git LFS adoption.

## Acceptance gates (implementation may begin only after)

Card review · exact dependency/version decision (mechanism: pinned `mlflow==X.Y` entry
in the `research` extra of `pyproject.toml [project.optional-dependencies]`; never
production requirements; version selected at implementation authorization, not here) ·
gitignore review (`research/offseason_2026/mlflow.db` +
`research/offseason_2026/mlflow_artifacts/` must be ignored; note `.gitignore`
currently covers `mlruns/`/`mlartifacts/` but NOT these exact paths) · identity examples
validated against existing cards (one worked above) · read-only boundary reviewed ·
test plan approved.
