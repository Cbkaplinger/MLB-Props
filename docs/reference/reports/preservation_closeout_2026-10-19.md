# Preservation closeout — 2026-10-19 (Chat 3, bounded; no further removals until dispositioned)

Per coordination: accounts for every worktree's unpublished commits and
dirty/untracked deliverables, cites pre-removal preservation evidence for the
removed worktrees, and explicitly covers Chat 2's findings and the untracked
preflight file. Live-verified this pass (`git fetch --prune` first).

## 1. Removed worktrees (8) — preservation receipts

All were verified **pre-removal**: clean including untracked files (0 dirty,
0 untracked), branch pushed to origin, and commit durability confirmed (7 heads
reachable from `origin/main` via merge commits; `maintenance/nav-20261015`
@ `f4fb5b50` retained durably on its pushed origin branch — PR #4 merged by a
non-fast-forward path, so the branch — not main — carries it). Branches were
NOT deleted. Receipts: session verification logs +
`github_reconciliation_receipt_2026-10-19.json`. **Nothing value-bearing was
lost.**

## 2. Remaining worktrees — unpublished commits and untracked deliverables

| Worktree | Branch @ head | Unpublished | Dirty/untracked deliverables | Disposition |
| --- | --- | --- | --- | --- |
| `main-active` | `research/paired-uncertainty-v2` @ `beb146b` | **4 commits** (`beb146b` unique-to-local; `02ce162`/`4a190f3`/`4bdb5ec` also on `origin/research/market-eval-v2` ✓ durable) | M `AGENTS.md`; untracked: `prop-dashboard-design-ticket-2026-10-13.md`, `push_plan_2026-10-14.md`, `preregistration_receipt_2026-10-13.md`, `pr1_description_draft_2026-10-13.md`, `run_bf_ab_score.py` | **PUBLISH** (Chat 1): push the 4 commits (or fold via PR #3 lineage) + commit the 5 untracked docs + AGENTS.md edit |
| `market-eval-v2` | `research/market-eval-v2` @ `cc003fb0` | 0 | untracked: **`research/offseason_2026/bf_lane/COUNT_RUN_PREFLIGHT.md`** | **PUBLISH** (Chat 1): the untracked preflight file named by coordination — commit it next to the count-registration artifacts |
| `chat2-tooling` | `chat2/review-tooling` @ `0c3b786b` | 0 | 0 | Chat 2's findings appendix and backlog edit are **committed and pushed** (verified: clean + 0 unpushed) — preservation concern resolved |
| `distribution-spec` | `agent/distribution-spec` @ `52379dd8` | **2 commits** | 2 dirty + 16 untracked (`d0_adapter.py`, `d0_audit.py`, reports…) | **RETAIN locally** — active WIP, other lane (owner disposition) |
| `evidence-register` | `docs/evidence-maturity-20261015` @ `72d79234` | 0 | untracked: `EVIDENCE_MATURITY_REGISTER_2026-10-15.md` | **Superseded** — the newer `evidence_maturity_register_2026-10-16.md` is delivered via PR #18; the untracked older copy needs no action |
| `MLB-Props` (main checkout) | `preserve/legacy-pending-20261005` @ `d311b751` | 0 (dirty state is vs the old base) | 1 dirty (`docs/EXECUTION_BACKLOG.md` — superseded by main's restructured backlog) + 47 untracked (fig11/fig12, `data/Retrosheet/`, reference docs) | **RETAIN locally pending owner disposition** — covered by safety snapshot `legacy-dirty-20261015`; the 9 manuscript-figure findings trace here |
| `paextwt` | detached `dfd8f170` | 2 commits unique to this worktree | 0 | **RETAIN** — provenance-required (paext fix + regression test); owner published-or-keep decision |
| `results-index-wt` | `research/results-index-v1` @ `7211269` | 0 | 0 | RETAIN — provenance branch checkout (PR #7 ruling) |
| `paext-v2`, `repo-review-pa-ext-v2` | Chat 1 build / Chat 2 review of `eee4f18` | 0 | 0 | active science lanes — untouched |
| `governance-cleanup-skills`, `maintenance-quality-baseline`, `maintenance-quality-delivery`, `maintenance-dep-declarations`, `maintenance-hygiene-check`(removed), merged-slice worktrees | all pushed; merged PRs | 0 | 0 | preserved or removed per section 1 |

Branches with unpushed commits, complete list: `agent/distribution-spec` (2),
`research/paired-uncertainty-v2` (4). **Every other local branch is fully
pushed.**

## 3. Explicit coverage of the named exceptions

- **Chat 2's uncommitted backlog edit + local findings appendix:** resolved —
  `chat2-tooling` is clean with 0 unpushed; the content is committed and pushed
  on `chat2/review-tooling`.
- **Untracked `COUNT_RUN_PREFLIGHT.md`:** located in `market-eval-v2`
  (exactly as reported); disposition = PUBLISH (Chat 1).
- **Audit-placement allegation (`RECONCILIATION_CHAT2.md` inside the frozen
  directory):** recorded as DISPUTED per the earlier ruling — Chat 2's
  directory-mapping task; not re-adjudicated here.

## 4. Standing constraint

**No further worktree removal, branch deletion, or pruning until every item
marked PUBLISH above is dispositioned.** Retained-locally items stay until the
owner rules.

---

## Correction (2026-10-19, later same day): repo-review-pa-ext-v2 removal + provenance + count annotation

1. **epo-review-pa-ext-v2 WAS removed** by the Chat 3 consolidation batch (listed in the removal set). It was Chat 2's ACTIVE review checkout for PR #16 � my "Chat 2-released" classification was an unconfirmed inference and was wrong for this checkout. Remediated: restored the same day at SHA 6feb32e (clean, byte-identical checkout), same path.
2. **Provenance discrepancy corrected:** Chat 2 reported the active checkout at eee4f18; the worktree actually removed was at 6feb32e (a later checkout of that lane). Restoration was therefore at 6feb32e, not eee4f18. Chat 2 selects the current review head from here � origin/research/pregame-pa-ext-v2 is at 46c5f7 (ahead of both).
3. **Count annotation:** the preservation table's "Remaining 9" is the inventory **at that observation** (2026-10-19), not a continuously current count. Chat 1 owns **four** paths (main-active, market-eval-v2, paext-v1, paext-v2), not three. Worktree count is point-in-time and must be re-verified at each observation (verified 10 at this correction).

---

# Preservation receipts - 2026-10-20 (Chat 3; PR #16 integration + consolidation batch)

Live-verified this pass (`git fetch --prune` first; all counts point-in-time).

## 5. PR #16 integration receipt

| Stage | SHA |
| --- | --- |
| Reviewed (Chat 2 READY verdict at exact head + CI SUCCESS) | `a16a51a` |
| Final head at merge (docs-only delta `a16a51a..c12c7e7`, 2 backlog lines, zero code drift; delta verified by Chat 3) | `c12c7e7` |
| Merge commit = resulting origin/main head | `9c60c70` |

- Merged 2026-10-20T04:33Z, normal merge commit, branch NOT deleted.
- Post-integration identity check (owed per the builder's handoff): PASS - merged tree byte-identical to the READY state across `research/offseason_2026/pregame_pa_ext/`, `count-eval-v2-spec/`, and all four paext test files.
- No real-data execution: reconstruction (command a) remains owner-gated; scoring stays blocked by design (null pin + population-policy decision).

## 6. Worktree consolidation 2026-10-20 (count 10 -> 6)

Owner released the review/tooling checkouts and the merged maintenance checkouts. All four removals were verified pre-removal: 0 dirty / 0 untracked, head remote-durable, ignored content trivial or regenerable. Normal `git worktree remove`, **no force**, **branches NOT deleted**.

| Removed worktree | Head | Durability evidence | Ignored content removed with it |
| --- | --- | --- | --- |
| `chat2-tooling` | `ea2ecbc` | == `origin/chat2/review-tooling`; PR #6 stays OPEN (referenced by merged metrics_evaluation_architecture report) | none |
| `repo-review-pa-ext-v2` | `a16a51a` (detached) | ancestor of merged PR #16 head; review complete (READY verdict posted) | `mlruns/` 50 files / 414 KB synthetic test scaffolding (canonical tracking is the external `MLB-Props-Research/mlflow.db`, untouched) |
| `governance-operating-rules` | `4fd3ba6` | merged via PR #19 (`a4ad500`) | none |
| `market-eval-v2` | `f14530c` | == `origin/research/market-eval-v2`; COUNT_RUN_PREFLIGHT durable (published at this SHA); PR #3 merged | `artifacts/odds_log/recommendations_meta.json` (140 B, regenerable sidecar), `data/dimensions/player_id_map.parquet` (regenerable dimension copy), two `mlruns/` test scaffolding (1.4 MB) |

**Remaining 6 (dispositions):**

| Worktree | Head | Disposition |
| --- | --- | --- |
| main checkout | `d311b75` on `preserve/legacy-pending-20261005` | INTENTIONAL preservation state; read current truth from origin/main, not this checkout |
| `paext-v2` | `c12c7e7` = merged PR #16 | Chat 1 keeps until its task closes; reconstruction command (a) runs FROM this worktree root - keep |
| `maintenance-dep-declarations` | `ac3c53a` = origin, PR #17 OPEN | keep while PR #17 is deferred pending owner tier approval |
| `paext-v1` | `e03f238` | **NOT REMOTELY DURABLE - do not remove.** No origin branch carries it; divergent from (not descendant of) `v1-legacy dfd8f17`. Unique commits: `rmse_correction_v2`, attempt-record + provenance corrections. Needs push to a remote legacy branch or owner ruling that it is superseded by v2 before any removal |
| `main-active` | `b70ebfc` | **NOT REMOTELY DURABLE - do not remove.** Commits beyond the merged PR #2 head `2c4d9bb` are local-only, plus M `AGENTS.md` + 5 untracked docs. Chat 1 PUBLISH lane, still open |
| `distribution-spec` | `52379dd8` = origin, 18 dirty/untracked | active WIP; owner disposition (unchanged from closeout) |

Count after batch: **6** (main checkout + 5 worktrees).

## 7. Corrections issued this pass (GitHub clarity, no supersessions)

- `chat3_final_handoff_2026-10-19.md:62` records PR #4 as "merged" - **wrong**; PR #4 is OPEN at `f4fb5b5`, base stale (`72d7923`), not an ancestor of main. Its 10 files exist nowhere on main and the merged 2026-10-16 corpus cites the PR as the carrier of canonical living docs (`current_state_2026-10-16.md`, CONTEXT.md banner fix, README/AGENTS links). NOT superseded; description refreshed on GitHub. The handoff text itself is merged content - left unedited here, flagged for the next docs pass.
- PR #4, #6, #17 descriptions refreshed with current status (stale bases, deferral gate, checkout release). No PR closed: none demonstrably superseded.
- `preservation_closeout` section 2 PUBLISH items: `chat2-tooling` and `market-eval-v2` are now RESOLVED (content durable on origin; worktrees removed above). Remaining PUBLISH: `main-active` (Chat 1).
- Standing constraint stands: no branch deletion, no history rewriting, no removals beyond the owner-released set above; `paext-v1` and `main-active` removal blocked until their unique content is pushed or owner-dispositioned.
