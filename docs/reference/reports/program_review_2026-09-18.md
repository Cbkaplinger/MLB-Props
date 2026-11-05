# Program review 2026-09-18 — timeline, scorecard, surface, forward plan

Point-in-time synthesis. Cousin brief: Perplexity (planning voice) sees
conversation summaries, not the repo — every claim below was checked against
disk (`git log`, file existence, test suite, Modal API) this session.
Live state it records: deploy **v31** current, rollback **v30**, heartbeat
green; 9/19 three-gate proof pending. Backlog remains the work queue; this
file is evidence, not a second queue.

## 1. Phase-tagged timeline (verified)

| Phase | What shipped | Evidence on disk |
|---|---|---|
| GC 0–1 | Baseline (284M/14D/35??), skill `.agents/skills/repo-garbage-collector/` (8 files), 5 specialist reports, evidence CSVs (temp, removed) | skill dir, `tests/test_gc_population_truth.py` (5 green) |
| GC 2 | Contradiction matrix; 7 doc surfaces fixed to rebuilt-panel truth (README, manuscript T3 row, diagrams 00/04, golden pointer, model-card WS1c pointer) | files current; stale-claim grep clean except intentional disclosures |
| GC 3–6 | Canonical modules named (`market.py`, `odds_ledger.py`, `prob_calibration.py`); 8 notebooks retained with wiring reasons; secrets audit clean (env-only) | code as cited; no secret values in tree |
| GC 7 | 844 = book-filter impostor (deleted + regression test), 485/558 superseded, 460/505 disk truth | `champion_2026_grade.json`, `select_2025_report.json`, truth tests |
| GC 8–9 | Doc batch only (zero deletions); independent verifier; temp artifacts removed | git history |
| Phase 10 | 8 census workstreams → `pipeline_registry.json` (9 pipelines, 10 schedules, 6 datasets, 12 gaps, 42 answers) + canonical-map catalog/DAG | registry (27 KB), map section |
| TEST-1 | 5 invariants → 6 tests (order proof+pin, double-settle, denominator, pregame-nine, book filter) | `tests/test_safety_invariants.py` |
| OBS-1 | `run_manifest.py` (statuses, no-bet codes, idempotency-key groundwork) + guarded drift/alert wiring | module + `tests/test_run_manifest.py` |
| OPS-1A | 5 Modal Crons → explicit `America/New_York`, local rewrites; 9 schedule tests; README/registry updates; deployed v29/v30; heartbeat image-e green | `modal_app.py` consts, `tests/test_modal_schedules.py`, history v29/v30 |
| Property | Hypothesis 6.168 pinned (dev); 12 tests (11 sweep + 1 pin) over `market.py`/`odds_ledger.py` | `tests/test_properties.py`, pyproject line |
| Train | T-A..T-G as `1b70d9a`..`3ffda61` via replay-onto-HEAD staging (git-apply broken by CRLF blobs — diagnosed); pushed `b2140c0..3ffda61` to main | git log; remote main |
| Smoke+fix | 3 gates graded (board PASS, manifest RED, paging RED); flips-only + manifest wiring + drift re-point built; RG hourly rescrape verified already-live | `tests/test_flips_only.py`, wiring diffs |
| Deploy | `a2ed3af fix(ops)` committed; closure audit; deployed **v31** 12:10 ET; 12:20 sweep image-f green | history v31, heartbeat 124 lines |

Backlog cross-check (scoped): every DONE claimed by THESE turns has its file
above. Older backlog DONE items were not re-audited this pass. Known
anomalies, all disclosed in commit messages or backlog: T-B committed a
truncated `modal_app.py` ENV block (repaired inside `a2ed3af`; production
never ran it — deploys build from worktree); hook stash cycles poison mtimes
(content diffs rule); manuscript judge-row hunk excluded (concurrent paper
work); ~104 dirty lines remain (T-H + concurrent, explicitly uncommitted).

## 2. Scorecard (disk + deploy, today)

| Dimension | Grade | Evidence |
|---|---|---|
| Stability | green | heartbeat all-ok across images d→e→f; exit codes honest |
| Metric integrity | green | canonical modules; 460/505 truth, dedupe, void, CLV-scale, property tests |
| Observability | amber | manifests emit (serve+settle files exist); content wired but first real emission pending; SLOs pending |
| Freshness safety | red | tag-only, no fail-closed gate; DATA-1A queued |
| Alert hygiene | amber | flips-only + drift re-point deployed-unproven; drift RED was stale-check class |
| Reproducibility | amber | registry + manifests + pins exist; tree partially uncommitted; ledger volume-only |
| Deploy traceability | amber | closure audits ×2, history to v31, rollback v30 known; deploys ship dirty tree |
| Test quality | green | 60 files, 158 green last full run, hook green per commit, sweep+pin pairing; mutation pending |
| Docs currency | amber | canonical set on rebuilt truth; manuscript hunk pending paper session; claim sprawl remains |

State labels: v31 = deployed-unproven (one sweep); `a2ed3af` = committed-unpushed;
manifest content + flips-only + drift re-point = built-unverified-in-prod;
invariants + schedules + properties = verified.

## 3. Unexamined surface (ranked by value-now)

1. **Laptop scheduler fallback** (`setup_automation_tasks.ps1` present, tasks disabled since cutover): re-enable path untested; value = survival if cloud dies. Probe at cutover decision, not now.
2. **P7 replay forks** (fair harness, governance sims): duplicate ROI/Sharpe/CLV math; value unlocks at EVAL-1/SIM-1. Next after DATA-1A.
3. **Batter lake** (11M rows, ignored bulk, zero tracked files): value unlocks at PROP-1. Do not mine before outs proves the contract.
4. **P9 publication assets** (manuscript, figures, `model_results_story.ipynb`): value at PUBLISH; judge-row hunk waits on paper session.
5. **Research notebooks** (`src/Notebooks/*`, stabilization/EDA): superseded explainers; NB-1 cleanup only.
6. **Archives** (`leaky-baseline-2026-07-23`, `pre-pipeline-v6`): history; keep, zero action.
7. **P3-TRAIN** (`train.py` ×2, frozen by doctrine): do not touch before offseason.

## 4. Forward plan (backlog holds the ordered IDs)

VERIFY (9/19): three-gate v31 proof → close smoke or rollback-call. HARDEN:
DATA-1A enforcing + kill switch → OPS-1B ownership → EVAL-1 → SIM-1.
MEASURE: SLO recorder (folded, record-only) → capped mutation baseline.
EXPAND: outs contract → shadow. PUBLISH: paper pipeline on paper-session
close. DEFERRED: branch protection, CI deploys, uv/lockfile, batter mining.
Each item's dependency, acceptance, 60-day cost-of-skipping, and scorecard
dimension live with its backlog ID — see EXECUTION_BACKLOG FORWARD PLAN.
