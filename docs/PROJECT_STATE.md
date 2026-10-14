# PROJECT_STATE — one-screen current state

**Date:** 2026-10-14. Point-in-time summary; `docs/EXECUTION_BACKLOG.md`
remains the live work queue and wins on conflicts.

## Champion (production)

Legacy production game-level model — **frozen**. Retrain path closed;
no live-path changes; dashboard parked.

## Active work

- **PA/H3 architecture development** — ongoing (per-PA / H3 projected-state
  line of work; see `docs/EXECUTION_BACKLOG.md`).
- **Market-eval v2 implementation** — implementation pinned at
  `02ce162f119208b762edf1fd690edd5e7ee9b8ea`
  (`research/offseason_2026/market_eval/`): prep v2 (outcome-free,
  write-once) + gated scorer + 28 synthetic tests + spec docs. The pin is
  preserved unchanged; review docs are a docs-only commit on top.
- **Scoring status:** NO authorized canonical scoring run. One accidental
  run occurred 2026-10-14 ~17:15 (outputs deleted without being cited;
  INCIDENT.md); whether anyone inspected the computed metrics is
  UNRESOLVED. Scoring remains owner-gated.

## PRs and reviewed SHAs

| Item | State |
| --- | --- |
| PR #1 (PA remediation review) | MERGED at `72d7923` |
| PR #2 (paired slate-date uncertainty repair) | OPEN (non-draft) |
| Reviewed SHA `6567c51` | backlog/docs review snapshot reviewed by Chat 2 |
| Pinned snapshot `02ce162f` | market-eval v2 implementation, byte-identical to lake sources, 28 tests pass on committed bytes |
| Branch `research/market-eval-v2` | published review branch: pin + docs-only follow-up commits; DRAFT research-only PR |

## Next action

Chat 2 independent review of the pinned snapshot (REVIEW_HANDOFF.md in
`research/offseason_2026/market_eval/`), led by the two serious issues:
the 17:15 incident blinding question and the missing verified pregame BF
inputs. The canonical scoring run stays gated until the owner resolves
blinding and accepts the review.
