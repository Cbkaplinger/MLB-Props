# NEXT - current action

Owner: architect. Updated 2026-11-11. Chat 3 closed; cleanup integrated.
Chat 1 active: parity lanes CLOSED (reproduced bit-exactly); the K-PMF
diagnostic executed (cohort contract; results in backlog + PR #83
comments); the market-benchmark seam is implemented and synthetic-tested.
ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your card.
EXECUTION_BACKLOG remains the single queue.

## Ablation baseline decision (owner, 2026-11-09)

Control = registered 8-feature multinomial + pooled W0; challenger =
registered 12-feature platoon recipe; no promotion/fresh-validation
claim. Evaluation: per-PA multiclass log loss, per-start means, paired
slate-date bootstrap, K-count RPS guard; no calibration. Full record:
`docs/EXECUTION_BACKLOG.md` + `experiment_impact_ledger_2026-10-22.md`.

## Prior completed milestones (this lane)

All VERIFIED; full records in `docs/EXECUTION_BACKLOG.md` and
`docs/reference/reports/experiment_impact_ledger_2026-10-22.md`:
workload w0v1, starter-outcome derivation, history-sensitivity,
Ref0-vs-Ref1, Stage-A (implemented; authorization-gated), binary-K /
LGBM / platoon lanes, lane stack at `2ca8aef`; paired comparison
reproduced bit-exactly (`b1b91357...224ba`); bridge (PR #81) and K-PMF
diagnostic (PR #83) merged.

## Current action: boundary-exception coverage follow-up (2026-11-11)

- **Implemented on this branch** (probe_board_coverage_boundary_2025H1.py):
  the follow-up to the correctly BLOCKED original probe. Explicit
  declared exception for book-lines boundary groups rg16-rg17 (quote
  columns only); envelope footer preflight (fail-closed on missing
  stats); immediate 2025H1 window filter after decode; protected rows
  never persisted/printed/summarized. Original probe remains
  fail-closed. 8 synthetic tests + 5 original = 13 green; focused
  combined run 111 passed. NOT RUN on real odds; needs owner
  authorization. Near-close labeling: this is a NEAR-CLOSE coverage
  query, not evidence of early-morning readiness.

## Prior action: market-benchmark seam (CLOSED, PR #84 merged)

market_benchmark_seam.py: harness PMF frame + per-book de-vig +
LTBO consensus. 7 synthetic tests. Zero live-path change.
  Closing quotes remain benchmark-only; the seam's benchmark paths are
  NEAR-CLOSE, not morning evidence. NOT RUN on real odds.
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
- Deferred hypothesis (corrected; not implemented): recency weighting
  of the model's EW features (fixed 90d half-life, self-relative,
  unshrunk - the committed stale-form finding). The batter-recency
  challenger was REJECTED and recency-batch-v1 showed development-only
  gains; no implementation without a new registered reason.
- Diagnostic: first execution BLOCKED (2,532 vs 2,509); second PASSED
  with 23 exclusions
  (results + delta-decomposition handoffs in PR #83 comments).
