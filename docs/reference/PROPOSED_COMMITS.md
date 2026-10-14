# PROPOSED_COMMITS - repository preservation inventory + bounded commit plan (2026-10-13)

**Status:** EXECUTED 2026-10-13 - three bounded LOCAL commits on `main`
(docs -> research harness -> logger), created by agent in the order below.
NOT pushed: push happens only after chat 2 clears public-content review
(command at the end of this file). Recipe/predictions untouched; no large
parquet/npy/pkl is committed. This file is part of commit 1, so the SHAs of
commits 2-3 are not printable here; read them from `git log --oneline -3`.

- **Repo:** `Cbkaplinger/MLB-Props` - **PUBLIC** (determinable; treat as such
  when committing: no keys, no large data).
- **Worktree:** `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\main-active`, branch `main`.
- **Remote status (measured 2026-10-13 at the pre-repair final checkpoint,
  HEAD = `b28c58b5056b9615d7eaf7ac47c6d8339d6d2101`; compared SHAs recorded,
  no hardcoded stale counts):**
  - vs `origin/main` @ `31e9891e88842680f5cddc07c7ea841cabf29425`:
    `git rev-list --left-right --count origin/main...main` = `0 28` -
    main is 28 ahead of origin/main, 0 behind (unpushed).
  - **Local review-branch push source:** branch `main` @
    `b28c58b5056b9615d7eaf7ac47c6d8339d6d2101` (= HEAD at measurement).
    There is NO local branch named `review/pa-remediation-2026-10-09`; the
    push maps `main:review/pa-remediation-2026-10-09`.
  - **Origin review-branch tip:**
    `origin/review/pa-remediation-2026-10-09` @
    `3b7fe3421dc6549f8fc695efb37962eda293f92a`.
  - `git rev-list --left-right --count origin/review/pa-remediation-2026-10-09...main`
    = `0 5` - main is 5 ahead of the origin review tip, 0 behind, so the
    push is a fast-forward.
  - The doc-accuracy and repair commits dated 2026-10-13 (this commit and
    the following repair commits) land AFTER this checkpoint and increment
    the ahead counts by their number with 0 behind. Re-measure before
    pushing:
    `git rev-list --left-right --count origin/main...main; git rev-list --left-right --count origin/review/pa-remediation-2026-10-09...main`
  **Push destination: origin `review/pa-remediation-2026-10-09` + PR #1**
  ("PA research closure: aggregation remediation + adapter + BF
  reconstruction/preflight/A-B forecast runners", DRAFT).
- **External archive:** `C:\Users\ckaplinger\MLB-Props-Research\` (not a git repo; preservation = hashes below + the commits proposed here).

## 1. Repository inventory (worktree, branch main @ b0897c0)

### Tracked-modified (1)
| File | Note |
|---|---|
| `tests/test_pa_aggregation_abc.py` | owner-modified; NOT in the proposals below (no owner instruction) |

### Untracked (3)
| File | Proposal |
|---|---|
| `docs/reference/mlb-strikeout-forecasting-roadmap.md` | docs commit (1) |
| `research/offseason_2026/run_bf_ab_score.py` | not proposed (superseded by v2/v3; owner decision) |
| `research/offseason_2026/run_bf_ab_score_v2.py` | not proposed (v3 already committed at b0897c0; owner decision) |

### Ignored (never commit)
`.hypothesis/`, `.pytest_cache/`, `artifacts/`, `data/`, `models/*/__pycache__/`,
`production/**/__pycache__/`, `research/offseason_2026/**/__pycache__/`,
`scripts/__pycache__/`, `src/**/__pycache__/`, `tests/__pycache__/`

### Recent commit head (for the preservation record)
`b28c58b` research(logging): prospective-logging-v1 append-only hash-chain
logger (= HEAD at the 2026-10-13 final-checkpoint measurement; the
inventory above was taken at `b0897c0`, which was HEAD at that time).

## 2. External deliverable inventory (`C:\Users\ckaplinger\MLB-Props-Research\`)

Preservation table. "Key file sha256" truncated to 12 hex in the table; full
hex in section 4. Review status: R = chat2-review-overnight-20261013 verdict
exists; S = seal receipt; - = no independent review record found.

| Deliverable | Location (under external root) | Size | Key file | Key sha256 (12) | Commit/branch binding | Review |
|---|---|---|---|---|---|---|
| seal-package-preflight | same | 0.08 MB | SEAL_RECEIPT.json | `8c9a7547cfe1` | bound to repo commit `b054014` (seal_manifest) | S, R |
| bf-bundle-2026-corr-20261012_132811 | same | 0.03 MB | bf_bundle.pkl | `c7ff78b104a8` | cited by seal_manifest + DEV_STANDARD_RECIPE | S, R |
| bf-ab-score-2026 | same | 0.01 MB | scoring_report.json | `93b4338d2608` | scored against b054014 lineage | superseded by v2/v3 |
| bf-ab-score-2026-v2 | same | 0.01 MB | scoring_report_v2.json | `b5bf8dd5880c` | - | superseded by v3 |
| bf-ab-score-2026-v3 | same | 0.01 MB | scoring_report_v3.json | `26c0a24744f4` | runner committed in repo @ b0897c0 | R (v3 review) |
| overnight-p1 | same | 0.10 MB | morning_report.md | `1cd86ec9dfcc` | - | self-reported only: S0/S5/S6 outputs are the run's own morning_report.md/scripts; no independent reviewer record exists |
| overnight-p2 | same | 56.81 MB | morning_report_v2.md + fit_ledger.json | `a295214add2c` / `485b29e11300` | run_identity frozen in recipe | R (p2_review, p2_attrib) |
| p0-data-card | same | 0.04 MB | data_card_v2.json | `2798a03d657b` | - | - |
| p1-harness (v1) | same | 20.39 MB | EVIDENCE_PACKET.md | `e1ce0ab0312d` | p1 lane | R (p1_revised) |
| p1-harness-v2 | same | 23.31 MB | reports/manifest.json + scripts | `28431311e6fc`, `a072d82b6bce`, `b17748ef40d0`, `4180e7d3655f` | eval_key_identity `da1d29d4...` (recipe section 8) | R (p1v2_foundation_verdict) |
| pregame-state-v1 | same | 3.30 MB | DEV_STANDARD_RECIPE.md + report_v2.json | `295474e7bd05` / `ab18353fbf29` | preregistration.json hash-pinned in recipe | R (pbs_review) - reviewed; remediation pending |
| prospective-logging-v1 | same | 0.11 MB | logger.py + test_logger.py | `0ab0fe92684f` / `f1f6cc2da09d` | DESIGN + SKELETON, target 2027 | - |
| handoff-v3 | same | 0.02 MB | run_bf_ab_score_v3.py | `949e43526317` | identical byte-for-byte to repo copy @ b0897c0 (verified) | R |
| bf-workload-v1 | same | 7.82 MB | report_v2.json + DIAGNOSTIC_DEFINITIONS.md | `fb3e6878c890` / `29afdf5bc2eb` | kcount_combiner pinned in recipe | R |
| (root) correction_note.md | external root | 0.01 MB | itself | (in file) | canonical pointer for the milestone-Brier v2 correction | R |

Untracked repo runners `run_bf_ab_score.py` / `run_bf_ab_score_v2.py` are the
v1/v2 scoring runners whose external archives exist at
`bf-ab-score-2026-v2/runner_executed_v2_archive.py`.

## 3. Proposed commits (NOT executed)

### Naming mappings (flagged)
- **"bf-closure-record"**: RESOLVED - the canonical closure record EXISTS
  in-repo and is committed at b0897c0 as
  `docs/reference/reports/bf-closure-record-2026-10-13.md` (it carries the
  v1/v2 scoring supersession statuses in its "v3 scoring correction
  delivered" section: v1 DELIVERED-suspected, v2 DELIVERED-superseded).
  Review status per the record itself: a dated point-in-time documentation
  record, not an independent review verdict. The external root
  `correction_note.md` (BF workload + pregame milestone-Brier v2 correction
  receipt) stays external-only, hash-recorded in the inventory above; no
  in-repo duplicate is created.
- **"scoring-vs-actual-K test" separability decision (2026-10-13):** the
  owner-modified block appended to `tests/test_pa_aggregation_abc.py`
  (+91 lines) is NOT separable for commit. Its
  `test_scoring_actual_K_keyed_per_pitcher` imports the UNTRACKED
  `research/offseason_2026/run_bf_ab_score_v2.py` (explicitly not
  proposed), so committing the test alone would ship a broken import;
  extracting only the three v3 tests would require editing their sys.path
  assumptions and duplicates owner-modified code with no owner
  instruction. The tracked-modified `tests/test_pa_aggregation_abc.py`
  therefore stays OUT of all three commits (left untracked-modified in the
  working tree); scoring-vs-actual-K coverage ships via the byte-identical
  `bf-workload-v1/tests/test_milestone_correction.py` instead.
- **KNOWN_ISSUES.md**: does not exist under `prospective-logging-v1`. The
  only known-defect disclosure in the external archive is
  `overnight-p2\KNOWN_ISSUES.md` (run-identity and manifest disclosures).
  Preserved byte-identical (sha256 `3a21dc8c...987d492`) in the docs commit
  as `docs/reference/reports/known_issues_overnight_p2_2026-10-13.md`
  (dated-report convention) rather than misfiled under
  `prospective_logging/`. The logger's own gap/defect list lives inside
  `LOGGING_SPEC.md`, copied verbatim. Supersession records for the BF
  scoring chain (v1/v2 superseded by v3) live in the committed
  bf-closure-record.
- **P1 tests live beside the scripts, not in `tests/`:** all three P1 test
  files use `HARNESS = Path(__file__).parent; sys.path.insert(HARNESS /
  "scripts")`, so co-locating them with the scripts under
  `research/offseason_2026/p1_harness/` (as in the external artifact) keeps
  them runnable with zero content edits and preserves byte hashes for the
  provenance precondition (DEV_STANDARD_RECIPE 9.1 item 3). They run via
  `python -m pytest research/offseason_2026/p1_harness`.
- **Logger** goes to `research/offseason_2026/prospective_logging/`
  (research, non-production; `tools/` does not exist in this repo).

### Commit 1 - docs (roadmap + overnight-p2 known-issues disclosure + this proposal)
Executed 2026-10-13 as:
```powershell
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\KNOWN_ISSUES.md" "docs\reference\reports\known_issues_overnight_p2_2026-10-13.md"
git add docs/reference/mlb-strikeout-forecasting-roadmap.md
git add docs/reference/reports/known_issues_overnight_p2_2026-10-13.md
git add docs/reference/PROPOSED_COMMITS.md
git commit -m "docs(preservation): 2026 forecasting roadmap + overnight-p2 known-issues disclosure + executed preservation commit plan (pregame-state-v1: reviewed, remediation pending; local main vs origin review-branch SHAs recorded)"
```
The bf-closure-record itself was already committed at b0897c0 and is
referenced, not duplicated. `correction_note.md` stays external-only.

### Commit 2 - P1 harness scripts + tests (byte-identical copies, no data)
Executed 2026-10-13. Two additions beyond the original recipe, both
byte-identical copies required for the committed tests to run:
`bf-workload-v1\scripts\run_kcount_comparison.py` (imported at module load
by `run_kcount_correction_v2.py`) and `bf-workload-v1\report.json` +
`report_v2.json` (small JSON reports read by the unchanged-metrics test).
```powershell
New-Item -ItemType Directory -Force "research\offseason_2026\p1_harness\scripts" | Out-Null
New-Item -ItemType Directory -Force "research\offseason_2026\bf_workload_v1\scripts","research\offseason_2026\bf_workload_v1\tests" | Out-Null
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\p1-harness-v2\scripts\build_features.py"  "research\offseason_2026\p1_harness\scripts\"
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\p1-harness-v2\scripts\build_pa_table.py"  "research\offseason_2026\p1_harness\scripts\"
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\p1-harness-v2\scripts\fit_models.py"      "research\offseason_2026\p1_harness\scripts\"
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\p1-harness-v2\test_harness_guards.py"     "research\offseason_2026\p1_harness\"
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\p1-harness-v2\test_log5_identities.py"    "research\offseason_2026\p1_harness\"
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\p1-harness\test_feature_contract.py"      "research\offseason_2026\p1_harness\"
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\scripts\run_kcount_comparison.py"     "research\offseason_2026\bf_workload_v1\scripts\"
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\scripts\run_kcount_correction_v2.py" "research\offseason_2026\bf_workload_v1\scripts\"
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\report.json"            "research\offseason_2026\bf_workload_v1\"
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\report_v2.json"         "research\offseason_2026\bf_workload_v1\"
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\tests\test_milestone_correction.py"  "research\offseason_2026\bf_workload_v1\tests\"
git add research/offseason_2026/p1_harness research/offseason_2026/bf_workload_v1
git commit -m "research(p1): durable provenance commit of P1 harness v2 scripts + guard/log5-identity/feature-contract tests + bf-workload-v1 kcount correction runner/tests (byte-identical to external p1-harness-v2 / p1-harness / bf-workload-v1 artifacts; data parquets excluded, stay external)"
```
Test state at commit time (python -m pytest, 2026-10-13): guards +
log5-identity + milestone-correction + logger suites = 67 passed, 1 failed.
The 1 failure (`test_v2_aggregate_brier_equals_direct_recompute_from_parquet`)
and all 4 `test_feature_contract.py` cases need the external-only data
parquets (`bf-workload-v1\data\start_metrics_v2.parquet`,
`p1-harness-v2\data\*.parquet`), which stay external and are never
committed - expected, per the provenance precondition. The milestone
correction test's hardcoded HELPERS path points at the main-active
worktree `research\offseason_2026` (kcount_combiner import) - documented,
not edited.

### Commit 3 - prospective logger (non-production research tooling)
Executed 2026-10-13 as:
```powershell
New-Item -ItemType Directory -Force "research\offseason_2026\prospective_logging" | Out-Null
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\prospective-logging-v1\logger.py" "research\offseason_2026\prospective_logging\"
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\prospective-logging-v1\test_logger.py" "research\offseason_2026\prospective_logging\"
Copy-Item "C:\Users\ckaplinger\MLB-Props-Research\prospective-logging-v1\LOGGING_SPEC.md" "research\offseason_2026\prospective_logging\"
git add research/offseason_2026/prospective_logging
git commit -m "research(logging): prospective-logging-v1 append-only hash-chain logger (2027 pregame capture spec; no live calls, no scheduler, no production-path change)"
```
`replay_demo.py` was not requested and stays external. Logger suite passes
in-repo (included in the 67-passed run above).

### Explicitly NOT committed
- All `.parquet` / `.npy` / `.pkl` / `.pyc` / `.pytest_cache` artifacts
  (external-only; hashes recorded above and in the manifests).
- `tests/test_pa_aggregation_abc.py` modification (owner-modified; scoring
  tests not separable - see the separability decision above; left
  tracked-modified and unstaged).
- Untracked `run_bf_ab_score.py` / `run_bf_ab_score_v2.py` (superseded by
  committed v3 at 7d0e8c8; owner decision required).
- `prospective-logging-v1\replay_demo.py` (not requested).
- `correction_note.md` (external root; canonical pointer is the committed
  bf-closure-record).
- Recipe/predictions: no changes anywhere in this plan.

### Push destination (owner runs; never pushed by agents)
```powershell
git push origin main:review/pa-remediation-2026-10-09
```
Then update PR #1 (`Cbkaplinger/MLB-Props`) with these commits.
