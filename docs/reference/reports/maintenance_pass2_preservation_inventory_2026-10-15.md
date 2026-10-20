# Maintenance pass 2 — preservation, unpublished-commit classification, worktree sync, evaluator inventory (2026-10-15, Chat 3)

Point-in-time record, executed under owner/coordination authorization of 2026-10-15.
Companion to [`maintenance_inventory_2026-10-15.md`](maintenance_inventory_2026-10-15.md).
No active harness files touched; no evidence deleted; nothing merged.

## 1. Uncommitted-work preservation (safety snapshot)

| Item | Value |
| --- | --- |
| Snapshot ID | `legacy-dirty-20261015` |
| Location (local only, never uploaded) | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-safety-snapshots\legacy-dirty-20261015\` |
| Source checkout | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props` @ branch `preserve/legacy-pending-20261005`, HEAD `d311b75` |
| Preserved | 114 files = 66 modified-tracked + 48 untracked; 8,371,841 bytes total; full file copies (NOT a patch — untracked files included) |
| Manifest | `manifest.json` + `manifest.md` in the snapshot root: path, sha256, byte size, tracked/untracked status per file |
| Spot verification | `src/Python/market.py` snapshot sha256 `3d4e86ad…` == live working-tree sha256 at snapshot time (byte-exact) |
| Exclusions | None — untracked set contained no `data/`/`artifacts/` content (gitignored), no secret-pattern filenames; largest file 212 KB (figure PNG) |
| Source checkout state | UNTOUCHED — no discard, reset, stash, or clean was run in the source checkout |

**Boundary:** preservation is NOT approval. The `hold_pct()` addition to protected
`src/Python/market.py` and the other 65 modified files remain unapproved production-code
changes awaiting explicit owner disposition (commit to a named branch / integrate / discard).

## 2. Unpublished PR #2 commits — commit-by-commit classification

Local branch `research/paired-uncertainty-v2` (`beb146b`) is 4 commits ahead of open PR #2
head `2c4d9bb`. Verified per commit (not by filename):

| Commit | Content | In PR #3 (by SHA)? | File-level vs PR #3 head | Disposition |
| --- | --- | --- | --- | --- |
| `02ce162` | market-eval pinned review snapshot (10 files: prep v2 + gated scorer + tests + spec docs) | YES | 6 identical, 4 divergent (later PR #3 commits evolved them) | Already preserved in PR #3; no action on PR #2 |
| `4a190f3` | market-eval 5 review docs | YES | 3 identical, 2 divergent (evolved in PR #3) | Already preserved in PR #3 |
| `4bdb5ec` | `AGENTS_ROLES.md` + `PROJECT_STATE.md` | YES | 2 divergent (evolved in PR #3) | Already preserved in PR #3 |
| `beb146b` | backlog restructure PAST/PRESENT/FORWARD/DEFERRED (docs-only, 1 file: `docs/EXECUTION_BACKLOG.md`) | **NO** | divergent (PR #3 backlog lacks the restructure) | **Only genuinely unpublished commit.** Owner decision (see below) |

**Consequence for the merge plan:** pushing the local branch to PR #2 would balloon the
ready 2-file uncertainty-repair PR with market-eval snapshot content — do not push.
The earlier "duplicate-lane conflict" risk is resolved: the three commits are identical
SHAs in PR #3, so no conflict exists. Recommendation (owner decides): land `beb146b`
via PR #3 or a small docs PR after integration — not via PR #2.

## 3. Worktree removal (checks run before each removal)

Coordination authorized removal "only after checking dirty state, unique commits, and
external evidence paths". Per-worktree results, then action:

| Worktree | HEAD | Dirty | Unique commits vs all refs | Ignored content | Action |
| --- | --- | --- | --- | --- | --- |
| `repo-review-02ce162` | `02ce162` | 0 | 0 | 6.6 KB caches | removed |
| `repo-review-1d3b382` | `1d3b382` | 0 | 0 | 3.2 KB caches | removed |
| `repo-review-33e1f63` | `33e1f63` | 0 | 0 | 3.2 KB caches | removed |
| `repo-review-6a41dbf` | `6a41dbf` | 0 | 0 | 7.5 KB caches | removed |
| `repo-review-72a99ef` | `72a99ef` | 0 | 0 | 3.2 KB caches | removed |
| `repo-review-b2d7140` | `b2d7140` | 0 | 0 | 3.2 KB caches | removed |
| `repo-review-c0805be` | `c0805be` | 0 | 0 | 3.2 KB caches | removed |
| `repo-review-dee0c5a` | `dee0c5a` | 0 | 0 | 3.2 KB caches | removed |
| `repo-review-e4de344` | `9dc01b3` (= PR #3 tip) | 0 | 0 | 14.7 KB caches | removed |
| `paextwt` (Temp dir) | `dfd8f17` | 0 | **2** | n/a | **KEPT** — contains unpublished work |

`paextwt`'s unique commit `dfd8f17` = "fix(paext): scoring secondary bootstrap reads
uniq_* from cmp + key-alignment guard (DEVIATION full_run-1)": `score_pa_ext.py` fix +
`DEVIATION_NOTE.md` + 256-line regression test. Real work, reachable from no branch or
remote. **Flag for the paext-v1 owner (Chat 1 lane):** this commit should be pushed or
cherry-picked onto `research/pregame-pa-ext-v1` by its owner; Chat 3 did not touch it.
Note the corresponding committed work (`e03f238` rmse_correction_v2) IS on that branch —
`dfd8f17` appears to be a later fix not yet folded in.

Remaining worktrees all hold named branches or live chat lanes; none touched.

## 4. Published state changes this pass

| Action | Artifact |
| --- | --- |
| Maintenance branch pushed + draft PR opened | PR #4 (`maintenance/nav-20261015` @ `7a2cb94`, base `main` @ `72d7923`) |
| PR #3 description refreshed (additive only) | Housekeeping note after the head-identity block: live-head disclaimer, current CI run, merge-order status, `beb146b` classification |
| Operator-script defect proposal filed | Issue #5 (`-IncludeGatePolicy` invokes deleted `results_gate_policy.ipynb`; conditional severity; intended replacement = `results_bettable_cohort.ipynb` per `20c2724`; Option A recommended; validation plan included) |

## 5. BF/count evaluator inventory (preparation — not an authorization to run anything)

Purpose: the next modeling stage should reuse these instead of writing a new evaluator.

### Importable building blocks (no CLI; import-safe)

| Module | Role | Notes |
| --- | --- | --- |
| `research/offseason_2026/kcount_combiner.py` | BF distribution x per-PA K probability -> count PMF (`extend_overflow_with_hazard` etc.) | Core count-combiner; support 0..22 + absorbing >=23 conventions live in callers |
| `research/offseason_2026/bf_distribution.py` | BF workload distribution: discrete termination-hazard utilities, PMF checks | Input to combiner |
| `research/offseason_2026/eval_package.py` | Reusable saved-artifact evaluation package (owner work packet) | Saved-prediction loading/eval plumbing |
| `research/offseason_2026/pa_k_baseline.py` | PA-K baseline: identity, target, pregame features, two arms | Arm A (shrunk log5) = retained PA benchmark |
| `research/offseason_2026/pa_lgbm_scaffold.py` | Pure (no I/O) label/pooled-prior/feature-dictionary scaffold | 19 green tests |
| `research/offseason_2026/contracts/pa_contracts.py` | Research-only PA prediction/aggregation contracts (G1 single-season, G8 unique-keys gates) | Reuse for any new aggregation runner |
| `research/offseason_2026/boundary.py` | Workspace boundary guards; import-safe canonical-module allowlist | Use when adding runners |
| `research/offseason_2026/workload_spine.py` | Outcome-independent forecast spine + prior-appearance history builder | |
| `research/offseason_2026/pregame_lineup_capture.py` | Research-only pregame lineup capture adapter (no writes, no live calls) | 6 green tests + runner `run_pa_pregame_ab.py` |

### Scored-run entry points (CLI, one canonical run each; research-only)

| Runner | Lane | Status per backlog/PRs |
| --- | --- | --- |
| `run_kcount_integration_2023.py` | I3b count integration (canonical REF) | Executed; canonical |
| `run_pa_k_baseline_2023.py` | PA-K arm A/B baseline | Executed; prereg recorded |
| `run_pa_aggregation_abc.py` | Aggregation A/B/C oracle diagnostic | Executed 2026-10-09; corrected canonical 154851-era lineage |
| `run_pa_lgbm_comparison.py` | PA LGBM vs log5 vs L3 | Executed; corrected canonical |
| `run_wf_comparison.py` + `build_wf_spine_2024.py` | Walk-forward WF comparison | Executed; gate FAIL recorded |
| `run_lgbm_bridge.py` | LGBM-to-count bridge diagnostic | Executed; PASS, no promotion |
| `run_bf_ab_score_v2.py` / `v3` / `run_bf_ab_score_cohort.py` | BF 2026 cohort scoring (cohort-aware-2) | Executed under owner-conditional authorization 2026-10-14 |
| `run_bf_2026_cohort_enumeration.py`, `run_bf_2026_seal_prep.py` | Cohort enumeration (metadata-only), seal prep | Executed; no outcome reads |
| `run_paired_uncertainty.py` | Block-stratified uncertainty repair (PR #2) | Open PR, CI green, not merged |
| `market_eval/market_eval.py` + `specs/count-eval-v2-spec/harness/comparison.py` | market-eval v2 + count-eval-v2 harness (PR #3) | Draft PR, executed run recorded, not merged |

**Inventory takeaway:** a per-PA -> count-distribution evaluator stack already exists
(scaffold -> arms -> combiner -> RPS/Brier metrics -> paired slate-date bootstrap with
Holm). New modeling stages should enter through `pa_lgbm_scaffold.py` +
`contracts/pa_contracts.py` gates and reuse `eval_package.py` +
`kcount_combiner.py` rather than adding a second harness. Nothing here authorizes a new
real-data run.

## 6. Not done (awaiting owner order, per standing boundaries)

- No CRLF renormalization, source moves, or tracked-file deletions.
- No disposition of the preserved checkout content (owner + Chat 1).
- No `beb146b` landing decision (owner + Chat 1).
