# Repository maintenance inventory — 2026-10-15 (Chat 3)

Point-in-time maintenance/integration-prep record. **Not a queue** — work
sequencing lives only in [`../../EXECUTION_BACKLOG.md`](../EXECUTION_BACKLOG.md).
Chat 1 owns harness/LightGBM implementation; Chat 2 owns review; Chat 1 remains
integration owner. Nothing here was merged, pushed, or moved.

## Provenance

| Item | Value |
| --- | --- |
| Maintenance branch | `maintenance/nav-20261015` (worktree `MLB-Props-worktrees/maintenance-nav-20261015`) |
| Base SHA (fetched origin/main) | `72d792349f167cbd82f855287ec2feb023eca73d` (PR #1 merge) |
| PR #2 head inspected | `2c4d9bb2618cdb6ca76a319dd1e431d69ea6be51` (origin; CI green run 38609636794) |
| PR #2 local branch | `beb146b` — 4 commits AHEAD of the open PR, unpushed (see §4) |
| PR #3 head inspected | `9dc01b3b2d4c06426e2226217420bff7af69ca89` (origin; CI green run 38792394966) |
| PR #3 body-stated docs head | `980b886d…` — confirmed ancestor of actual head; 4 commits landed after the body edit |
| Main checkout inspected | `preserve/legacy-pending-20261005` @ `d311b75`, 66 modified + ~50 untracked files, uncommitted |

## 1. Repository map (verified against origin/main @ 72d7923)

Classification protocol and non-targets: [`repo_canonical_map.md`](repo_canonical_map.md).
This is the same partition, re-verified 2026-10-15; no contradictions found.

| Class | Surfaces |
| --- | --- |
| Active code | `src/Python/`, `production/odds/`, `production/ops/` (daily/settle chains), `production/notebooks/` current set, `tests/`, `scripts/`, `.github/` |
| Canonical evidence | `research/offseason_2026/experiments/*/` (cards, manifests), `research/offseason_2026/specs/`, `docs/reference/reports/` (dated), `docs/reference/golden_metrics.md`, `docs/adr/`, `docs/reference/pipeline_registry.json` |
| Historical material | `docs/archive/`, `docs/CLEANUP_LOG.md` (ledger, not instructions), superseded reports (must self-label SUPERSEDED), parked research branches |
| Generated/local | `data/`, `artifacts/`, `.venv/`, `.hypothesis/`, `.pytest_cache/` (ignored; never commit, never glob-discover) |
| Docs/navigation | `AGENTS.md`, `CONTEXT.md`, `docs/EXECUTION_BACKLOG.md`, `docs/reference/repo_canonical_map.md`, `production/README.md` / `INDEX.md` / `RUNBOOK.md` |

## 2. Prioritized cleanup candidates

| # | Candidate | Evidence | Risk | References affected | Proposed action | When |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `MLB-Props-worktrees/repo-review-*` (8 detached review worktrees at `02ce162/1d3b382/33e1f63/6a41dbf/72a99ef/b2d7140/c0805be/dee0c5a`) | All detached HEADs; review snapshots for closed checkpoints (adapter 72a99ef/1d3b382, aggregation c0805be, market-eval pin 02ce162) | Low — commits referenced are recorded in backlog/PRs; only worktree dirs would go | None in tracked files | `git worktree remove` one-by-one after owner confirms no pending review needs them | HOLD — post-gate, owner decision |
| 2 | `repo-review-e4de344` detached at `9dc01b3` | Same SHA as PR #3 tip; redundant with the branch checkout `market-eval-v2` | Low | None | Fold into #1 | HOLD |
| 3 | `%TEMP%\opencode\paextwt` worktree (detached `dfd8f17`) | Lives in Temp dir; detached | Low | None | Remove with temp cleanup | HOLD — confirm `dfd8f17` not needed |
| 4 | Main-checkout uncommitted diff (66 files, ~2,244 insertions ignoring CR) | Verified substantive: e.g. new `hold_pct()` in protected `src/Python/market.py`; also `odds_ledger.py`, notebooks, ops scripts | **High (data-loss risk, not cleanup)** — exists only in the working tree of `preserve/legacy-pending-20261005`, in no PR/branch | Everything it touches | **Not a cleanup target.** Owner + Chat 1 must commit/branch it (or explicitly discard) BEFORE any worktree reset/rebase or PR merge that touches those paths | NOW (owner decision) |
| 5 | CRLF renormalization (`.gitignore` etc. show LF→CRLF warnings) | `git diff --ignore-cr-at-eol` trims 2,341→2,244 insertions, i.e. part of the dirt is line endings | Medium — touches many files, interacts with #4 | Repo-wide | Add/verify `.gitattributes` + renormalize as ONE dedicated commit, off the gate | HOLD — post-gate, owner order |
| 6 | `docs/CLEANUP_LOG.md` | Existing historical cleanup ledger | None | None | Reuse as the ledger for any executed cleanup; do not create a parallel log | NOW (convention only) |

Deletion of tracked files: none proposed this pass. `repo_canonical_map.md`
delete-gates (reference scan, import scan, hash-verified duplicates, smoke runs)
must be run before any future delete.

## 3. Verified stale-documentation findings

- **Nav-link scan clean.** 200 markdown files scanned (excluding `docs/archive/`),
  50 relative links checked, **0 broken**. Includes `AGENTS.md`, `CONTEXT.md`,
  `docs/EXECUTION_BACKLOG.md`, `repo_canonical_map.md`, `production/README.md`/`INDEX.md`/`RUNBOOK.md`,
  `docs/reference/reports/README.md`. No link repairs needed.
- **CONFIRMED correctness issue (report-only; Chat 2/owner owns the script):**
  `production/ops/run_daily_operator_flow.ps1:59` runs
  `production\notebooks\results_gate_policy.ipynb`, which **does not exist**
  (`Test-Path` = False). The notebook was retired in the 2026-09-17 notebook GC;
  `results_bettable_cohort.ipynb` hosts the retired gate-policy audit
  (docs commit `20c2724c`). Any operator flow run that reaches line 59 will fail.
  Matches the 2026-10-09 backlog OPS record. Open questions stand: unconditional
  vs optioned invocation, whether the flow is still used, intended replacement.
- **PR #3 body staleness (report-only):** the body's head-identity block cites
  docs head `980b886` + CI run 38681175349. Actual origin head is `9dc01b3`
  (4 later commits: `17aee8d`, `972fc55`, `5fdfcf9`, `1b56a2b`, `aed7f36` —
  recency-batch-v1 freeze + executed results + null-centered bootstrap
  registration + builder handoff), with a newer green CI run (38792394966) on
  that head. Body should be refreshed by the owning chat before merge.

## 4. Open-PR inventory, merge order, conflict assessment

| PR | State | Head | Delta vs main | CI | Readiness |
| --- | --- | --- | --- | --- | --- |
| #1 PA research closure | MERGED | `6567c51` → main `72d7923` | — | — | Done |
| #2 paired slate-date uncertainty repair | OPEN, ready | `2c4d9bb` | 2 files, +512 | green on head | Ready; fast-forwardable (contains main) |
| #3 market-eval v2 | OPEN, **draft** | `9dc01b3` | 58 files, +13,863 | green on head `9dc01b3` | Draft by owner order — hold until LightGBM stage closes |

**Conflict assessment (verified, not assumed):**
- PR #3's branch **contains** PR #2's tip (merge-base of the two branches =
  `2c4d9bb` = PR #2 head). The two files PR #2 adds
  (`research/offseason_2026/run_paired_uncertainty.py`, `tests/test_paired_uncertainty.py`)
  are **blob-identical** in both branches. Merging PR #2 first leaves PR #3
  conflict-free against main.

**Proposed merge order (Chat 1 executes, owner gates):**
1. **PR #2** — merge when owner is ready. Smallest, ready, green, FF.
2. **PR #3** — stays draft until the LightGBM stage closes per owner. Before
   merge: refresh the body (head identity + CI), confirm recency-batch-v1
   executed-run reconciliation is closed, then merge.
3. **Docs maintenance PR (this branch)** — after #2/#3, rebased on integrated
   main if the gate ran long.

**Coordination risks found (report-only):**
- Local `research/paired-uncertainty-v2` (`beb146b`) is **4 commits ahead of the
  open PR #2**, unpushed: backlog restructure (`beb146b`), `AGENTS_ROLES.md` +
  `PROJECT_STATE.md` (`4bdb5ec`), market-eval review docs (`4a190f3`), pinned
  review snapshot (`02ce162`). **`docs/AGENTS_ROLES.md` and `docs/PROJECT_STATE.md`
  also exist in PR #3** — if those 4 commits get pushed onto PR #2, they may
  conflict with PR #3's copies. Chat 1/owner should decide: push them to #2, land
  them via #3, or drop duplicates — before either merge.
- Main-checkout uncommitted work (candidate #4 above) predates and overlaps
  nothing in the PRs but must be dispositioned before integration moves.

## Boundary statement

This pass changed **no** harness/adapter/config/production files, deleted no
evidence, moved no sources, and created no approval gate. Cleanup actions in §2
marked HOLD require owner order after the current LightGBM stage closes.
