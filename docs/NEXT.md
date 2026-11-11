# NEXT - current action

Owner: architect. Updated 2026-11-11. Chat 3 closed; cleanup integrated.
Chat 1 active: parity lanes CLOSED (reproduced bit-exactly); the K-PMF
diagnostic executed (cohort contract; results in backlog + PR #83
comments); the market-benchmark seam is implemented and synthetic-tested.
ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your card.
EXECUTION_BACKLOG remains the single queue.

## Ablation baseline decision (owner, 2026-11-09)

- Control: registered 8-feature multinomial plus pooled W0.
- Challenger: registered 12-feature platoon recipe; no production promotion
  or fresh-validation claim.
- Evaluation uses per-PA multiclass log loss, per-start means, paired
  slate-date bootstrap, and the K-count RPS guard; calibration remains absent.
- Full recipe and verified results: `docs/EXECUTION_BACKLOG.md` and
  `docs/reference/reports/experiment_impact_ledger_2026-10-22.md`.

## Prior completed milestones (this lane)

All VERIFIED; full records in `docs/EXECUTION_BACKLOG.md` and
`docs/reference/reports/experiment_impact_ledger_2026-10-22.md`:
workload w0v1 (pooled W0 favored), historical starter-outcome derivation
(9,714 starts), history-sensitivity scorecard, Ref0-vs-Ref1, Stage-A
reconciliation (implemented; real run authorization-gated), binary-K /
LGBM / platoon lanes (control retained / retained / challenger favored),
lane stack integrated at `2ca8aef`. Paired comparison reproduced
bit-exactly (checkpoint `7e6d03c`; every artifact byte-identical,
receipt_final = `b1b91357...224ba`); harness-to-market bridge
implemented and merged (PR #81); K-PMF diagnostic built, executed once
under the cohort contract (PR #83; results + delta-decomposition
handoffs in PR #83 comments).

## Current action: market-benchmark seam built (2026-11-11)

- **Implemented on this branch** (market_benchmark_seam.py): the two
  missing seams between the registered market-eval lane
  (market_eval_k.py) and today's harness outputs - (A) harness keyed
  24-bucket PMFs + assessment-derived observed K + declared eligible
  cohort (hash-checked) + declared start dates -> the registered
  market-eval model frame (block via ad.add_block; protected/unknown
  blocks refuse); (B) per-book two-sided de-vig probabilities +
  leave-target-book-out consensus (median over OTHER books at the
  SAME line; >= 2 other books; unavailable recorded, never filled) +
  all-book consensus (registered construction reused unchanged).
  7 synthetic tests green (hand de-vig, LTBO self-exclusion,
  unavailable accounting, cohort/date gates incl. protected block).
  Closing quotes remain benchmark-only; the seam's benchmark paths are
  NEAR-CLOSE (tier A/B around first pitch) - not evidence of
  early-morning simulation readiness. NOT RUN on real odds; execution
  needs the registered market-eval gate + delegated owner order. Exact
  comparison contract + execution packet: see the PR description and
  backlog FORWARD.
- Next bounded deliverable: the opening-price replay contract
  (market-only first). Registered decision clock
  (oddsapi_replay_inventory_2026-09-11.md): Friend -12h open when
  present, else paid morning T-5h; close = paid commence-5min via
  snapshot_envelope.vendor_timestamp (never the reconstructed ts);
  consensus cache is already de-vigged (never re-devig). Clocks
  recorded in pull_oddsapi_historical._snapshot_ts: close -5min,
  morning -5h, board = fixed 12:00Z (8am ET, all-EDT), open18 -18h
  (T-24h/-30h dead per probe). 2025 board-clock coverage: UNKNOWN
  (2023/24 sampled only). The MODEL morning replay is blocked by
  historical morning-decision-time projected-lineup availability
  (pregame_lineup_capture.py has no committed 2025H1
  morning-coverage record; later confirmed lineups are not morning
  inputs). Replay baseline rows renamed: over_hit (binary panel
  outcome; full-start K only in assessment-derived paths).
- Deferred hypothesis (recorded, not implemented): recency-weighted
  entry consensus (weighting books/snapshots by freshness instead of
  unweighted median) may reduce stale-quote noise in the open-to-
  close baseline; evaluate only after the opening clock is fixed.
- Diagnostic history: first execution hit the exact-key gate
  (2,532-request assessment vs 2,509 eligible cohort); cohort contract
  amended; second execution PASSED with 23 declared exclusions
  (results + delta-decomposition handoffs in PR #83 comments).
