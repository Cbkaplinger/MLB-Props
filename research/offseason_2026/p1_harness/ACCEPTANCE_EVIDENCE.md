# ACCEPTANCE EVIDENCE - p1 harness repair + artifact-root lanes (2026-10-13)

All commands run with the repo venv Python 3.11.9 / pytest 9.1.1 /
polars 1.43.0. Suite = the three focused suites
(`p1_harness` + `bf_workload_v1` + `prospective_logging`), the same
population as the 2026-10-13 publication-repair baseline (69 passed /
3 skipped). External lake: `<external-lake>\`.
No 2026 scoring, no deployment, no model/policy changes.

## 1. Portable lane, artifacts absent (main-active checkout)

    python -m pytest research/offseason_2026/p1_harness \
        research/offseason_2026/bf_workload_v1 \
        research/offseason_2026/prospective_logging -q

    72 passed, 3 skipped, 4 warnings

Delta vs the 69/3 baseline: +3 = the new import-resolution guards
(one per harness test module). The 3 skips are exactly the three genuinely
artifact-dependent tests, each skipping on file existence only (before any
read) with a reason naming the missing file:

- `test_feature_contract.py::test_c_executed_artifact_source_dates_strictly_precede_game_date`
  -> data/features.parquet absent
- `test_feature_contract.py::test_d_eval_prediction_key_sets_identical_across_candidates`
  -> data/eval_predictions.parquet absent
- `test_milestone_correction.py::test_v2_aggregate_brier_equals_direct_recompute_from_parquet`
  -> bf_workload_v1 data/start_metrics_v2.parquet absent

## 2. Isolated-checkout run (no main-active fallback)

    git worktree add <temp>\p1-portable-wt 474cd86
    # copy ONLY the four repaired files into the worktree's p1_harness/
    cd <temp>\p1-portable-wt
    python -m pytest research/offseason_2026/p1_harness \
        research/offseason_2026/bf_workload_v1 \
        research/offseason_2026/prospective_logging -q

    collected 75, 72 passed, 0 failed, 0 errors, 3 skipped

Exact module paths executed (inside the worktree checkout, asserted by the
new import-resolution tests):

    <temp>\p1-portable-wt\research\offseason_2026\p1_harness\test_feature_contract.py
    <temp>\p1-portable-wt\research\offseason_2026\p1_harness\test_harness_guards.py
    <temp>\p1-portable-wt\research\offseason_2026\p1_harness\test_log5_identities.py
    <temp>\p1-portable-wt\research\offseason_2026\p1_harness\conftest.py
    imported build_features -> <temp>\p1-portable-wt\research\offseason_2026\p1_harness\scripts\build_features.py
    imported fit_models     -> <temp>\p1-portable-wt\research\offseason_2026\p1_harness\scripts\fit_models.py

Worktree removed after the run (`git worktree remove --force`). No path
under the main-active checkout was on sys.path; the module-`__file__`
guards would have failed any fallback.

## 3. Artifact-equipped run on this machine (repaired a/b included)

    $env:P1_HARNESS_ARTIFACT_ROOT = "<external-lake>\p1-harness-v2"
    python -m pytest research/offseason_2026/p1_harness \
        research/offseason_2026/bf_workload_v1 -q

    27 passed, 4 warnings

(a)/(b) now exercise the full declared v2 production schema (21 columns:
features + lg_n_prior + pitcher_role + source dates/types + split), with
independent league-rate recomputation (fixed-prior day-1 semantics),
source-type/support agreement, and cold-start fallback-to-lg_rate checks;
(c)/(d) read the sha256-pinned executed artifacts (all four hashes in
conftest.py match the private lake byte-for-byte).

## 4. Required-artifact INTEGRATION lane, lake present

    $env:P1_HARNESS_ARTIFACT_ROOT = "<external-lake>\p1-harness-v2"
    python -m pytest research/offseason_2026/p1_harness \
        research/offseason_2026/bf_workload_v1 -m integration -q

    3 passed, 24 deselected

(The third integration test reads the canonical
`bf-workload-v1\data\start_metrics_v2.parquet`, sha256 af6814ec...bb4817fde,
verified and dropped into the gitignored `bf_workload_v1\data\` -
never committed.)

## 5. Missing-input FAILURE (required-artifact mode)

    $env:P1_HARNESS_ARTIFACT_ROOT = "<empty dir>"
    python -m pytest research/offseason_2026/p1_harness -m integration -q

    FAILED test_c_... - Failed: required artifact file is missing:
        <empty dir>\data\features.parquet (declared under
        P1_HARNESS_ARTIFACT_ROOT; INTEGRATION lane)
    FAILED test_d_... - Failed: required artifact file is missing:
        <empty dir>\data\eval_predictions.parquet (declared under
        P1_HARNESS_ARTIFACT_ROOT; INTEGRATION lane)
    2 failed, 18 deselected

Hash-mismatch also FAILs (demonstrated with a one-byte-tampered
features.parquet copy):

    Failed: artifact hash mismatch: <tampered>\data\features.parquet
    sha256 5a05415c...f2be23 != declared
    b2ec8c90...f457e9b98 (wrong or stale bytes; failing in every lane)

Parsing/schema/assertion failures can never become skips: the skip
decision lives solely in `require_artifact` (conftest.py) and is made on
file existence only, before any bytes are read; the sha256 check precedes
reading and FAILS on mismatch in every lane.
