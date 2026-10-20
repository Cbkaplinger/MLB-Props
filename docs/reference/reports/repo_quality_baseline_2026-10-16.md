# Repository Quality Baseline — 2026-10-16 (Chat 3, report-first)

Point-in-time baseline from `origin/main` @ `1927c8c8c8a4ae72af5be848dea865ce59bd5866`.
**No PR opened; no code changes.** Each section is evidence-backed; each proposed
action carries owner/risk/disposition and awaits an owner-approved task slice.
Companion data: per-file inventory at `docs/reference/reports/` level of detail in
the Chat 3 session records (inventory.json / entries.json snapshots, 2026-10-15).

## 1. Open-PR inventory (live-verified this pass)

| PR | Head | Behind main | Ahead | Draft | CI on head | Stale-base? | Depends on |
|---|---|---|---|---|---|---|---|
| #2 paired uncertainty repair | `2c4d9bb2` | 2 | 1 | no | pass (38609636794) | YES (merge-base `72d7923`) | none; first in merge order |
| #3 market-eval v2 + B0/B1 + closeout | `3de017a1` | 2 | 49 | yes | pass | YES | B1 closeout + count registration + Chat 2 READY |
| #8 results index | `59092c80` | 2 | 1 | yes | pass (38954481993) | YES | Chat 2 verdict |
| #10 PR handbook | `2547cdb7` | 2 | 1 | yes | pass (38959439465) | YES | #8 verdict (then wording refresh for #11) |
| — role-card PR | prepared, not created | — | — | — | — | — | #8 verdict |

**Merged:** #1, #11 (CI optimization, post-merge main `1927c8c`).
**Closed:** #7 (superseded by #8; branch `research/results-index-v1` retained).

Stale-base impact: every open PR predates the #11 workflow change. Expected
effect on refresh: near-zero for #2/#8/#10 (their changed paths do not touch
`.github/`), zero-conflict expectation for #3's 49 commits (workflow file is not
in its diff). GitHub `mergeable` showed UNKNOWN during post-merge recomputation;
re-check at each merge moment.

**Merge order (unchanged, re-confirmed):** #2 → #3 (after closeout+READY) → #8
→ #10 (with #11 wording refresh) → role cards. `beb146b` after #3.

## 2. Documentation inventory and canonical-source map

809 tracked files, 27.4 MB. Doc-bearing roles (from the 2026-10-15 inventory):
current-docs 69, dated evidence reports 24, historical evidence 26, work-state 1,
plus README-class files in 33 directories.

Proposed classification (every markdown file gets exactly one):

| Class | Rule | Current examples |
|---|---|---|
| Canonical living | updated when its source of truth changes | `README.md`, `AGENTS.md`, `CONTEXT.md`, `repo_canonical_map.md`, `current_state_2026-10-16.md` (on PR #4) |
| Runbook/operational | updated only when ops behavior changes | `production/README.md`, `INDEX.md`, `RUNBOOK.md` |
| Frozen experiment packet | never edited retrospectively; corrections append | `research/offseason_2026/experiments/*/card.*`, prereg docs |
| Historical evidence | retained; errata only | `docs/reference/reports/*`, `docs/archive/*`, `docs/research/*` |
| Superseded | forward pointer, then archive/delete after inbound-link + owner check | 34 files already carry SUPERSEDED markers |
| Duplicate/orphan | removal proposal with reference list + destination | `expanding-training-prereg-draft.md` == final; `pa-k-baseline-prereg-draft.md` == final |

## 3. Links, dead references, stale references, duplicates (evidence)

- **Broken relative markdown links: 0** across all 809 tracked files (two full scans, 2026-10-15).
- **Truly dead notebook references (7 files):** `results_gate_policy.ipynb` in
  `production/RUNBOOK.md`, `docs/diagrams/01+03`, backlog, `run_daily_operator_flow.ps1`
  (= Issue #5); `Strikeouts.ipynb` in `src/Python/reliability.py` (= Issue #9);
  `feature-understanding.ipynb` in `docs/CLEANUP_LOG.md` (historical, benign).
- **Unrooted-but-resolvable refs (~14):** bare notebook names in historical docs
  that exist under `src/Notebooks/` or `production/notebooks/` — path-drift only.
- **Duplicate content (7 groups):** 2 intentional (`.cursorignore`==`.clineignore`),
  2 draft==final prereg pairs (owner hold), 1 within-experiment oddity
  (`pitcher_prior/calibration.json`==`metrics.json`, owner hold), 2 intentional rerun copies.
- **Duplicate filenames (26):** benign (READMEs, SKILL.md, `__init__.py`); 2
  naming collisions verified as distinct tools (`odds_board.py` pair — no action;
  `prune_artifacts.py` pair — canonicality needs owner ruling; canonical map
  references the `scripts/` copy).
- **Stale PR/SHA references on main: none** (`PR #1` x3 only — merged; zero
  references to superseded main SHAs). Stale references exist only inside dated
  PR-branch reports, where they are correct point-in-time records.

## 4. End-to-end architecture map (with ownership boundaries)

```text
INGEST          collection (baseball + odds arms)            Chat 1 lane (production/ops, Modal crons)
  |             statcast / lineups / SharpAPI live / OddsAPI lake
  v
FEATURES        L1 games -> L2 rolling -> L3 training         frozen pipeline; src/Python protected
  |
  +--> PA LANE  P(K|PA): logistic representative            CLOSED family (LightGBM equal-info retired)
  |             count-eval-v2 harness (PR #3)               Chat 1 build / Chat 2 review
  +--> BF LANE  B0 audit PASSED; B1 ACCEPT-WITH-LIMITATION  one pending authorized count run
  |             B1 = Ridge-recentered B0 PMF (217/4866      limitation permanently attached
  |             flagged boundary cases, 4.5%)
  +--> COUNT    combiner seam: P(K=k) = sum_n P(N=n)P(K=k|N=n)   I3b retained benchmark
  |             registered one-shot B1-vs-I3b comparison    READY-gated by Chat 2
  +--> MARKET   de-vig benchmark, ledger, CLV, policy       frozen champion; closed to PA/BF claims
  v
TRACKING        MLflow execute-first-import-after; D-1       recovery deviations documented
MONITOR         notebooks (kpi/pnl/calibration/cohort)       operator flow: Issue #5 defect open
```

Evidence anchors: `CONTEXT.md` lifecycle, `repo_canonical_map.md` pipeline
catalog (P1–OPS), `docs/diagrams/06` harness diagram, backlog closeouts.
No maintenance claim crosses lane boundaries; metrics never cross lanes.

## 5. CI/CD audit (post-#11) and hardening backlog

Current (verified on main @ `1927c8c`): single job `test-and-validate`, pip wheel
cache keyed on `pyproject.toml`, per-ref concurrency (main never cancelled),
30-min timeout, single-process `compileall`, full suite byte-identical, JUnit
uploaded `if: always()`. No path filters. Suite runtime ~60–75s end-to-end.

Report-only findings (each needs its own authorized PR; none urgent):

| # | Finding | Risk | Proposed disposition |
|---|---|---|---|
| C1 | **No `permissions:` block** — job runs with default (potentially write) token | Medium | Add `permissions: contents: read` (workflow is read-only) |
| C2 | **Cache key excludes the 5 explicitly installed extras** (`scipy joblib scikit-learn lightgbm statsmodels` are not hashed) — silent version drift possible between cached restores | Medium | Add a lockfile or list the extras in a hashed requirements file |
| C3 | Actions version-tagged, not SHA-pinned (`checkout@v4`, `setup-python@v5`, `upload-artifact@v4`) | Low-Med (supply chain) | Pin SHAs deliberately, or document the accepted risk |
| C4 | Artifact retention at default (90 days) for pytest reports | Info | Set explicit `retention-days` if reports are used as receipts |
| C5 | No pytest annotations/matcher — failing test requires reading the log | Info | Optional; low priority |
| C6 | No Python matrix (single 3.11) | Info | Intentional; matches the single supported runtime — keep |
| C7 | Docs/index determinism: guarded by `tests/test_results_index.py --check` **once #8 lands** | Info | Ensure any future generated doc gets the same guard |

Explicitly deferred (per standing rule): test sharding, path filtering, autoformat-on-merge, automatic dependency upgrades.

## 6. Test and artifact-retention inventory

- **84 test files** under `tests/` + harness test dirs (`p1_harness/`,
  `market_eval/tests/`, `bf_workload_v1/tests/`, `count-eval-v2` harness tests on PR #3).
- Coverage pattern (name-mapped, report-only): ledger/registry/bet lifecycle
  (pre-commit fast trio: `test_odds_ledger`, `test_real_bets`, `test_registries`),
  PA research harnesses, market research utilities, ops automation, ingestion
  contracts. Untested-entry-point candidates for a future plan: ops `.ps1`
  chains (Issue #5 class), notebook surfaces (execution checks only via
  `scripts/check_notebook_artifacts.py`).
- **Artifact policy (current, working):** lake outputs + forecasts + bootstrap
  arrays stay OUT of Git; Git carries manifests/receipts/hashes (B1 closeout
  pattern). Ignored-but-tracked exception: `data/Pitcher-Starts-2023-2025-Data/README.md`
  (intentional negation — document). Tracked generated files: 79 model artifacts,
  10 notebook-output files, figures under `docs/paper/figures/` — all provenance
  records; retention = keep.

## 7. Proposed sequence of small, non-overlapping maintenance PRs

Each = one task, one owner (Chat 3), one branch off current main, one PR,
exact-head CI, Chat 2 verdict, post-merge main-SHA recording.

| Seq | PR (one slice each) | Blocked on |
|---|---|---|
| 1 | Role cards `docs/agent_roles/` + AGENTS.md pointer + handbook §10 #11-wording fix | #8 verdict |
| 2 | PR #2/#8/#10 base refresh (merge main into each; no content change) | their own merge moments |
| 3 | CI hardening slice: `permissions: contents: read` + explicit artifact retention | owner approval (C1/C4) |
| 4 | CI cache-key slice: hash the installed extras (C2) | owner approval |
| 5 | Superseded-pointer pass (RUNBOOK + diagrams 01/03 → Issue #5/bettable cohort; SUPERSEDED banners from classification table) | #8 verdict + B1 gate closure |
| 6 | Draft==final prereg duplicate disposition (archive/pointer, owner-approved slice) | owner |
| 7 | `prune_artifacts.py` canonicality note after owner ruling | owner |
| 8 | Notebook census + archival proposal | owner approval of scope |

**Disposition of this report:** delivered at exact SHA on branch
`maintenance/quality-baseline-20261016` (no PR). Awaiting owner-approved task
slices; each slice then becomes its own narrow PR per the anti-collision rules.
