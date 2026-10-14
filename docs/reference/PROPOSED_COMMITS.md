# PROPOSED_COMMITS - repository preservation inventory + bounded commit plan (2026-10-13)

**Status:** EXECUTED 2026-10-13 - bounded LOCAL commits on `main`
(docs -> research harness -> logger -> accuracy pass -> collection repair ->
portability lane), created by agent in that order.
NOT pushed: push happens only after chat 2 clears public-content review
(command at the end of this file). Recipe/predictions untouched; no large
parquet/npy/pkl is committed.

- **Repo:** `Cbkaplinger/MLB-Props` - **PUBLIC** (determinable; treat as such
  when committing: no keys, no large data, no private absolute paths).
- **Worktree:** the `main-active` worktree of this repo, branch `main`
  (local path withheld from this public file - it embeds the OS username).
- **External archive:** the owner-local research archive root
  (hashes below pin its contents; local path withheld for the same reason).

## 0. Accuracy record of this file

- 2026-10-13 accuracy pass (commit 36955ff): ahead/behind recomputed at the
  pre-repair final checkpoint with compared SHAs (hardcoded stale counts
  removed); overnight-p1 review mark corrected to self-reported-only;
  bf-closure-record claim confirmed against the committed record.
- 2026-10-13 repair pass: import/collection repair + private-path scrub +
  artifact-skip guards landed in the harness/bf-workload files; this file
  updated to match the exact repaired commands/files (see "Repair pass"
  under commit 2 and the deviation notes).

## 0a. Remote status (measured 2026-10-13 at the pre-repair final checkpoint,
HEAD = `b28c58b5056b9615d7eaf7ac47c6d8339d6d2101`; compared SHAs recorded,
no hardcoded stale counts)

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
- The accuracy/repair commits dated 2026-10-13 land AFTER this checkpoint
  and increment the ahead counts by their number with 0 behind. Re-measure
  before pushing:
  `git rev-list --left-right --count origin/main...main; git rev-list --left-right --count origin/review/pa-remediation-2026-10-09...main`

**Push destination: origin `review/pa-remediation-2026-10-09` + PR #1**
("PA research closure: aggregation remediation + adapter + BF
reconstruction/preflight/A-B forecast runners", DRAFT).

## 1. Repository inventory (worktree, branch main @ b0897c0 at inventory time;
HEAD at the final pre-repair checkpoint = b28c58b)

### Tracked-modified (1)
| File | Note |
|---|---|
| `tests/test_pa_aggregation_abc.py` | owner-modified; NOT in the proposals below (no owner instruction) |

### Untracked (3)
| File | Proposal |
|---|---|
| `docs/reference/mlb-strikeout-forecasting-roadmap.md` | docs commit (1) |
| `research/offseason_2026/run_bf_ab_score.py` | not proposed; provenance established 2026-10-13 (see 1a); publication excluded (owner decision) |
| `research/offseason_2026/run_bf_ab_score_v2.py` | not proposed; provenance established 2026-10-13 (see 1a); publication excluded (owner decision) |

### 1a. Provenance finding: run_bf_ab_score.py / run_bf_ab_score_v2.py (2026-10-13)

Measured against the external archive (bf-ab-score-2026, bf-ab-score-2026-v2)
and git history:

- `run_bf_ab_score_v2.py` is **byte-identical** to the archived executed
  runner `bf-ab-score-2026-v2/runner_executed_v2_archive.py`
  (both sha256 `6b8cecf24a2463463d98e94e84b0bdab146d55cb6d29382c4955eb4cdb24bc4a`).
  It IS the historical executed v2 source, not a reconstruction.
- `run_bf_ab_score.py` is **line-for-line identical** to the archived
  `bf-ab-score-2026/scoring_code_used.txt` ("scoring code used" record,
  64/64 lines equal modulo trailing whitespace); it differs from that file
  only in line endings (LF in the working file vs CRLF in the archive txt).
  The v1 archive contains no runner `.py`, so v1 is historical-source-
  equivalent by content, with the line-ending caveat recorded.
- Git evidence: `git log --all -- <both files>` is EMPTY - neither file was
  ever tracked in any branch's history. The v3 runner
  (`run_bf_ab_score_v3.py`) was committed at 7d0e8c8 and is byte-identical
  to `handoff-v3/run_bf_ab_score_v3.py` (verified in the bf-closure-record).
- Conclusion: both are the historical pre-fix sources (v1 content-equivalent,
  v2 byte-exact); NOT later reconstructions. Publication status: excluded
  from the commits (owner decision outstanding); this finding closes the
  provenance disclosure gap flagged in the 2026-10-13 publication review.

### Ignored (never commit)
`.hypothesis/`, `.pytest_cache/`, `artifacts/`, `data/`, `models/*/__pycache__/`,
`production/**/__pycache__/`, `research/offseason_2026/**/__pycache__/`,
`scripts/__pycache__/`, `src/**/__pycache__/`, `tests/__pycache__/`

## 2. External deliverable inventory (external research archive root)

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

## 3. Proposed commits (executed record)

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
  therefore stays OUT of all commits (left tracked-modified in the
  working tree); scoring-vs-actual-K coverage ships via the
  `bf-workload-v1/tests/test_milestone_correction.py` file.
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
- **P1 tests live beside the scripts, not in `tests/`:** the three P1 test
  files resolve `scripts/` relative to their own file location
  (`HARNESS = Path(__file__).resolve().parent`), so co-locating them with
  the scripts under `research/offseason_2026/p1_harness/` (as in the
  external artifact) keeps them runnable and preserves the harness layout
  from the external artifact. They run via
  `python -m pytest research/offseason_2026/p1_harness`.
- **Logger** goes to `research/offseason_2026/prospective_logging/`
  (research, non-production; `tools/` does not exist in this repo).

### Commit 1 - docs (roadmap + overnight-p2 known-issues disclosure + this proposal)
Executed 2026-10-13. Two file additions (byte-identical copies from the
external archive) plus this file; the bf-closure-record itself was already
committed at b0897c0 and is referenced, not duplicated. `correction_note.md`
stays external-only. Follow-up accuracy pass landed as commit 36955ff.

### Commit 2 - P1 harness scripts + tests (provenance copies, no data)
Executed 2026-10-13. Committed set (10 files):
`research/offseason_2026/p1_harness/` = scripts\build_features.py,
scripts\build_pa_table.py, scripts\fit_models.py, test_harness_guards.py,
test_log5_identities.py, test_feature_contract.py;
`research/offseason_2026/bf_workload_v1/` = scripts\run_kcount_comparison.py,
scripts\run_kcount_correction_v2.py, tests\test_milestone_correction.py,
report.json + report_v2.json. The two report JSONs (small text) are read by
the unchanged-metrics test; `run_kcount_comparison.py` supplies the exact
v1 machinery imported (lazily) by `run_kcount_correction_v2.py`.

**Repair pass (same day, additive commit; supersedes byte-identity for the
edited files only).** The publication review flagged: import-time execution
of the v1 comparison runner (guaranteed collection fragility), hardcoded
`C:\Users\...` helper paths (username disclosure + broken collection on a
clean checkout), and missing skip guards on data-pinned tests. Repairs
applied to 5 of the 10 files; the other 5 stay byte-identical to their
external sources:

| File | Deviation from external source |
|---|---|
| `bf_workload_v1/scripts/run_kcount_comparison.py` | HELPERS resolved relative to the file (`parents[2]`); P2 preds dir via `BF_P2_PREDS_DIR` env override with `Path.home()`-based default (no literal username); `import os` added |
| `bf_workload_v1/scripts/run_kcount_correction_v2.py` | HELPERS resolved relative to the file; v1 comparison module loaded LAZILY via `_load_v1()` (importing the module executes nothing); `main()` binds the v1 constants locally |
| `bf_workload_v1/tests/test_milestone_correction.py` | HELPERS resolved relative to the file; parquet test skips with explicit reason when the external `data/start_metrics_v2.parquet` is absent; `import pytest` added |
| `p1_harness/test_feature_contract.py` | STALE v1-era mirror of the feature assembly replaced with the executed v2 `main()` assembly (league_daily fixed-prior semantics, v2 src_type derivation, null-date fills) - (a)/(b) are synthetic and now actually pass; (c)/(d) skip with explicit reason when the external parquets are absent; `import pytest` added |
| `p1_harness/scripts/build_pa_table.py` | RAW_DIR default resolved repo-relative (`<repo>/data/Savant-Data/regular`), env override chain `P1_RAW_SAVANT_DIR` -> `MLB_PROPS_SAVANT_DATA_DIR` (no literal username) |

Skip-guard convention: skips are granted ONLY for missing external
artifacts (private-lake parquets), each with an explicit reason naming the
file; every required file is checked before reading; synthetic guards,
log5 identities, the (repaired) feature-contract mirror, and logger tests
run without the private lake; when the artifacts exist, malformed data or
failed assertions FAIL - never skip.

Commit 3 - prospective logger (non-production research tooling): executed
2026-10-13 as three byte-identical copies (logger.py, test_logger.py,
LOGGING_SPEC.md) to `research/offseason_2026/prospective_logging/`.
`replay_demo.py` was not requested and stays external.

### Explicitly NOT committed
- All `.parquet` / `.npy` / `.pkl` / `.pyc` / `.pytest_cache` artifacts
  (external-only; hashes recorded above and in the manifests).
- `tests/test_pa_aggregation_abc.py` modification (owner-modified; scoring
  tests not separable - see the separability decision above; left
  tracked-modified and unstaged).
- Untracked `run_bf_ab_score.py` / `run_bf_ab_score_v2.py` (provenance
  established in section 1a; v2 byte-exact executed source, v1 content-
  equivalent; superseded by committed v3 at 7d0e8c8; publication excluded
  pending owner decision).
- `prospective-logging-v1\replay_demo.py` (not requested).
- `correction_note.md` (external root; canonical pointer is the committed
  bf-closure-record).
- Recipe/predictions: no changes anywhere in this plan.

### Test state after the repair pass (python -m pytest, 2026-10-13, focused
suites: p1_harness + bf_workload_v1 + prospective_logging)
69 passed, 3 skipped, 0 failed. The 3 skips are exactly the
external-artifact tests with explicit reasons (features.parquet,
eval_predictions.parquet, start_metrics_v2.parquet - private lake, never
committed). Baseline before repair: 67 passed, 5 failed (the stale v1
feature-contract mirror failed its two synthetic tests; the three
data-pinned tests failed on absent parquets).

### Portability lane
- Default lane (CI): synthetic fixtures only must run - harness guards,
  log5 identities, repaired feature-contract (a)/(b), milestone identity
  tests, logger suite. Verified green with zero external artifacts.
- Integration lane (explicit, full-artifact): `pytest -m integration` over
  the two directories; the three artifact-pinned tests carry the
  `integration` marker (registered in pyproject) plus their skip guards.
  No catch-all skipping: a present-but-malformed artifact still FAILS.

### Push destination (owner runs; never pushed by agents)
```powershell
git push origin main:review/pa-remediation-2026-10-09
```
Then update PR #1 (`Cbkaplinger/MLB-Props`) with these commits.
