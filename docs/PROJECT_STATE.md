# PROJECT_STATE — dashboard

Point-in-time dashboard. `docs/EXECUTION_BACKLOG.md` remains the live work
queue and wins on conflicts. Detailed evidence lives at the linked commits,
PRs, and lake files — not duplicated here.

## As-of

- **2026-10-19**, state frozen at this file's latest commit.
- `068e9df6d8c8901ddc7dd85647d6641933d4302c` (also published on branch
  `research/project-state-20261016`) is a **HISTORICAL EVIDENCE CHECKPOINT**
  only — it is NOT the current dashboard revision.

## Closed

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

## Active

- **Chat 1:** hold for projected-batter authorization (see Blocked).
- **Chat 2:** review #15, then #14.
- **Chat 3:** address those reviews, integrate eligible cleanup PRs, then
  hand off blocked slices.

## Blocked (owner decisions needed)

- Projected-batter scoring authorization (gates Chat 1).
- S-B / S-C dependency declarations.

## Protected

- **Immutable evidence:** sealed pilot outputs, frozen packets, registered
  runners, lake write-once run dirs (`count_b1_recovery_v1\` and siblings),
  lake `CLOSEOUT_CORRECTIONS.md`.
- **Do not edit without owner order:** `docs/EXECUTION_BACKLOG.md`,
  production paths (`src/Python/market.py`, `count_layer.py`,
  `live_assembly.py`, `odds_ledger.py`, `production/ops/*.json`,
  `production/odds/`, `artifacts/models/`), CI workflows
  (`.github/workflows/`).
- **Prohibited:** unauthorized reruns, model promotion, live-path changes,
  committing `data/` / `artifacts/`, agent `git push` to main.

## Integration owner (merge queue)

| PR | State | Owner |
| --- | --- | --- |
| #2 (paired slate-date uncertainty repair) | OPEN | owner to confirm |
| #3 (`research/market-eval-v2`, research-only) | OPEN draft | owner to confirm |
| #8 | OPEN | owner to confirm |
| #14 | OPEN | Chat 2 reviews; merge owner to confirm |
| #15 | OPEN | Chat 2 reviews; Chat 3 merges |
