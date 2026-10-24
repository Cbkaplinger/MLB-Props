# PROJECT_STATE — dashboard

Point-in-time dashboard. `docs/EXECUTION_BACKLOG.md` remains the live work
queue and wins on conflicts. Detailed evidence lives at the linked commits,
PRs, and lake files — not duplicated here.

## As-of

- **2026-10-19** (state correction pass), state frozen at this file's latest
  commit.
- `068e9df6d8c8901ddc7dd85647d6641933d4302c` (also published on branch
  `research/project-state-20261016`) is a **HISTORICAL EVIDENCE CHECKPOINT**
  only — it is NOT the current dashboard revision.
- Separation rule: **experimental completion is tracked in "Closed"; PR
  integration state is tracked in "Integration owner" — the two are kept
  separate.** An experiment's completion (or a lane's closure) never implies
  its PR is merged, and a merged PR never retroactively approves an
  experiment.

## Closed (experimental work — complete regardless of PR state)

| Item | Canonical evidence |
| --- | --- |
| PR #12 (hygiene checker) MERGED | `d57ba17f` on `origin/main` |
| PR #13 (governance/cleanup-skills) MERGED | review PASS at `5571b338`; post-merge main `dd3318f` |
| Directory mapping resolved (upstream BF fit / failed count attempt / count recovery = three distinct dirs) | lake `CLOSEOUT_CORRECTIONS.md` (sibling of frozen run dir) |
| Recovery inventory = 21 files; earlier 11-file account WITHDRAWN | lake `CLOSEOUT_CORRECTIONS.md` |
| count_b1_recovery_v1 independently reproduced, accepted WITH LIMITATION | lake `CLOSEOUT_CORRECTIONS.md` (computation complete; package finalization failed) |
| Recovery finalization = **CLOSED LIMITATION** | analysis accepted with limitation; NOT an open execution blocker — no further execution required |
| RECOUNT metric-context scorecard published | `8f8c0f5` |
| Market review CLOSED (de-vig dominates both PA arms at matched contracts) | scorecard at `8f8c0f5`; Brier ordering **0.4469 (market) < 0.4663 (LOG5) < 0.4684 (H3)** |
| B1 Ridge run executed once + reconciled (ACCEPT WITH LIMITATION, max dev 4.44e-16); count lane closed | backlog 2026-10-16 entry, commit `6ee8544`; lake `bf-lane-v1\b1_run_v1\` |

## Withdrawn (stale request)

- **Count-execution request WITHDRAWN 2026-10-19.** The first-run packet
  (`research/offseason_2026/specs/count-eval-v2-spec/harness/
  FIRST_RUN_CONFIG.md`, status "NOT-EXECUTED — awaiting owner
  authorization") is stale: the count lane closed with recovery finalization
  = CLOSED LIMITATION ("no further execution required") and the B1 count
  challenger was already executed once and closed 2026-10-16. The question
  that packet was registered to answer has been answered by other means. The
  frozen packet and its hashes remain as evidence only — **no run is
  authorized, expected, or pending**; do not execute it without a new,
  explicit owner order.

## Active (assignments as of 2026-10-19)

- **Chat 1:** projected-lineup implementation proposal prep — advance
  `research/offseason_2026/bf_lane/PROJECTED_LINEUP_SPEC.md` (registered
  SPECIFIED-NOT-IMPLEMENTED, no code) toward an implementation proposal.
  Prep only: no code execution, no scoring; any execution stays behind the
  owner's run gate.
- **Chat 2:** (a) #2/#3 live-state review — current PR states, merge
  receipts, and role-document integration at origin/main (first pass:
  `MLB-Props-Research\CHAT2_INTEGRATION_REVIEW.md`, post-change review, not
  retroactive pre-merge approval); (b) score_v2 integrity review.
- **Chat 3:** **CLOSED after handoff (2026-10-19).** Branch
  `maintenance/quality-baseline-20261016` published at `f6a5e056` (four
  terminal commits on origin); S-B/S-C recorded owner-blocked. No further
  work in this lane.

## Blocked (owner decisions needed)

- **S-B (dependency declarations, T13):** OWNER-BLOCKED — needs owner
  approval of tier placement (`requests` research-tier recommendation;
  `sage` verify-or-retire call). Spec:
  `docs/reference/reports/maintenance_slice_specs_2026-10-16.md`.
- **S-C (dead-module ruling brief, T15):** OWNER-BLOCKED — needs the owner's
  one-word answer (are `ballpark` / `batter_features` / `batter_rolling` /
  `identity` / `reliability` invoked outside the tracked tree?).
- Projected-lineup EXECUTION authorization (any projected-batter/lineup
  scoring run; does not gate Chat 1's proposal prep).

## Process deviations (recorded 2026-10-19, not retroactively approved)

1. **Direct push to main for role docs.** `1321b72` ("docs: consolidate role
   map into AGENTS_ROLES.md; AGENTS.md points to it") landed on
   `origin/main` with no PR, no review, and no CI gate — against the
   standing never-push rule and `AGENTS_ROLES.md`'s own "Push/PR/merge: only
   on an explicit owner order naming the branch". Recorded for the ledger.
2. **Merge of PR #10 despite Chat 3's assigned ownership.** `AGENTS_ROLES.md`
   assigns cleanup-PR integration to Chat 3 ("owns approved cleanup
   branches, cleanup-PR integration, and the final handoff"); PR #10
   (maintenance/pr-handbook-20261016) was merged without that lane. Recorded
   for the ledger.

## Protected

- **Immutable evidence:** sealed pilot outputs, frozen packets, registered
  runners, lake write-once run dirs (`count_b1_recovery_v1\` and siblings),
  lake `CLOSEOUT_CORRECTIONS.md`, frozen count-eval packets (incl. the
  withdrawn first-run packet — evidence only).
- **Do not edit without owner order:** `docs/EXECUTION_BACKLOG.md`,
  production paths (`src/Python/market.py`, `count_layer.py`,
  `live_assembly.py`, `odds_ledger.py`, `production/ops/*.json`,
  `production/odds/`, `artifacts/models/`), CI workflows
  (`.github/workflows/`).
- **Prohibited:** unauthorized reruns (including the withdrawn first-run
  packet), model promotion, live-path changes, committing `data/` /
  `artifacts/`, agent `git push` to main.

## Integration owner (merge queue — PR state only)

| PR | State (2026-10-19) | Head | Note |
| --- | --- | --- | --- |
| #2 (`research/paired-uncertainty-v2`, paired slate-date uncertainty repair) | OPEN | `2c4d9bb2` | mergeStateStatus UNKNOWN; needs rebase onto current main — branch predates the role-doc consolidation and would remove `docs/AGENTS_ROLES.md` |
| #3 (`research/market-eval-v2`, research-only) | OPEN draft | `2c335246` | mergeStateStatus UNKNOWN; needs rebase — carries the older 2026-10-14 `AGENTS_ROLES.md` (no Chat 3 role) |
| #8, #14, #15 | MERGED | — | per the 2026-10-19 GitHub reconciliation receipt (maintenance branch `f6a5e056`) |


## Integration owner update - 2026-10-20 (Chat 3; supersedes the merge-queue rows above for PR state; "Closed" experimental rows unchanged)

- **Merged (receipts):** #16 `a16a51a`->`9c60c70`; #17 `a3bd3a7`->`07d1b1d`;
  #21 `1b3bfd3`->`ccd0148`; #4 `b1411b0`->`cab0f02`; #22 `5b2ea4c`->`3c62655`;
  #6 `dd0ec36`->`4e764ab`; #23 `5b9ccbe`->`f85e7c8`. The #2/#3 OPEN rows in the
  table above are SUPERSEDED - both merged 2026-10-19 (2026-10-19 GitHub
  reconciliation receipt).
- **Open PRs:** #24 cleanup batches (Chat 3, head advancing under exact-head
  review); #25 batter-history challenger implementation (Chat 1, gated,
  synthetic tests only, no fitting).
- **Active assignments (supersede the 2026-10-19 rows):** Chat 1 - PR #25
  implementation; Chat 2 - cleanup-PR delta reviews (#24); Chat 3 - cleanup
  lane ACTIVE again (the "CLOSED after handoff" note above is superseded by
  the owner's reassignment; maintenance/quality-baseline history unchanged).
- **Owner decisions (current):** (a) abstain-vs-handle for the 59
  pitcher-cold starts (57 debut-date newcomers + Enns 608650 / Hart 606996)
  after the scoring run's FAILED zero-exclusion acceptance - output
  UNACCEPTED, preserved, no rerun authorized; (b) S-C dead-module ruling
  (unchanged); (c) distribution-spec workspace disposition (requested once
  2026-10-20, pending).
- **Resolved since 2026-10-19:** S-B tier approval GRANTED and MERGED (PR #17:
  requests/xgboost/optuna/catboost = research; pymupdf/markdown = paper;
  modal = deploy; sage undeclared by design) - the S-B owner-blocked row
  above is superseded.
- **Worktrees (verified 2026-10-20, 6 incl. primary):** preservation ledger
  section 17 (`docs/reference/reports/preservation_closeout_2026-10-19.md`).


## Integration owner update - 2026-10-23 (Chat 3; matches docs/NEXT.md)

- **Market matching component: UNDER AUDIT.** The ±1-day tolerance is a
  suspected failure mode, not a demonstrated root cause. Existing market
  scores are quarantined pending identity verification. The
  two-starters-one-game synthetic test is the required regression check.
- **M0 v2 ACCEPTED as development-only diagnostic** (executed at `2e2482b`,
  Chat 2 independently verified; effects small: K log-loss delta ~-7e-06,
  multiclass 1.2241 vs log5 1.2263, count-RPS delta -0.000169). Not evidence
  of practical betting value.
- **Question A decision-flip**: 1 flip in 19,292; below practical
  significance; no promotion. Recipe closed as documented curiosity.
- **Question B (workload dependence)**: design card pending; on hold behind
  M0 verdict.
- **Abstain-vs-handle (59 starts)**: owner decision pending.
- **Open PRs:** #34 (research, Chat 1/2). All cleanup PRs merged (#33/#35/
  #36/#37/#38/#39/#40).
- **Cleanup lane:** Chat 3 parked after the deep-clean pass; branch audit
  for the remaining 6 non-main branches delivered; 0 unmet obligations from
  the six-folder assignment.
- **Owner decisions (current):** (a) abstain-vs-handle for the 59
  pitcher-cold starts (57 debut-date newcomers + Enns 608650 / Hart 606996);
  (b) Question B design card (on hold behind M0 verdict); (c) dashboard
  v1 unpark (parked until backend #113 is green).
