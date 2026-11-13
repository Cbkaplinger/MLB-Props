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

## Current action: Packet B owner-decision brief (2026-11-13)

- **Packet A COMPLETE (executed + closed):** the paid-morning 2025H1
  market-only baseline was PRODUCED (PR #90 merged at main aa61986;
  exit 0; receipt PR #90 comment 6861125006; artifact index 6861289910).
  Headline (market-only, no model-edge claim): 19,800 candidates;
  entry-eligible 5,441/19,797; valid close 4,934/5,441; mean movement
  -0.0869 pp; positive-CLV over 0.4270 / under 0.4497; flat-1u entry
  ROI over -0.0452 / under -0.0782 units per unit. Single-run
  permission CONSUMED.
- NEW PR (this branch): the existing control_vs_books packet now
  carries the PACKET B OWNER-DECISION BRIEF (question, runner
  identity, honest full-file/transitive access + protected exposure,
  timing/identity limitations, fresh out-dir, stop conditions).
  Packet B remains UNAUTHORIZED - owner decision only.

- Prior bounded quote-only diagnostic packet (SUPERSEDED by the
  close-conflict drop-and-count policy above; executed once, refused
  with the preserved close-conflict evidence).

- EXECUTION-READY (PR #88, merged): the gated runner is complete - args
  validated before output/decode; tables as parquet; scores/coverage
  JSON via fail-loud conversion (never default=str); receipt_final
  LAST (output-failure test: no completed receipt on failure);
  consumed identities recorded (cohort hash, pinned artifacts,
  book_lines/envelope/workload, bridge source + card manifest).
  Synthetic main-entry success test reads outputs back with
  hand-computed log-loss/Brier. Timing contract recorded: commence
  (vendor-scheduled) is NOT observed first pitch; near-close does
  NOT establish confirmed-lineup availability before every quote;
  closest-date/id-order tiebreak is NOT independent identity
  validation (per-mapping status = declared gap).
- Four-key binding amendment PREPARED
  (production/ops/market_research/expected_exclusions_2025H1.json:
  3 receipt keys + castillo luis 2025-04-09; union-exclusion policy
  unchanged; no rerun under consumed permissions).
- Combined gates 83 passed. Two proposed execution packets on the
  PR #88 handoff: (A) paid-morning baseline recovery (recorded order
  + amended binding); (B) control-vs-books near-close benchmark
  (ack EXECUTE-CONTROL-VS-BOOKS-V1 + registered gate). NOT EXECUTED.

## Prior action: identity-exclusion policy (CLOSED, PR #87 merged)

PR #87 merged at main 999ffbe. Opt-in `--identity-policy
exclude_ambiguous` (default refuse unchanged; exclusions before book
selection/outcome consumption; morning+close union, no re-entry;
preserved in accounting; `--expected-excluded-keys` receipt binding).
The amended single run was EXECUTED once on integrated main: REFUSED
at the binding gate (fourth close-side key castillo luis 2025-04-09
beyond the bound three; all three bound keys confirmed; no outputs;
panel exception not consumed; receipt PR #87 comment 6829936974).
CLOSED as the execution of record under that order; awaiting the
owner's binding decision before any further run.

## Prior action: market-only T-5h replay (CLOSED, PR #86 merged)

juiced_replay_ledger --entry-clock morning_only: explicit market-only
path (bypasses p_ours_cal/policy/sizing; canonical bare run unchanged;
no candidates parquet). Identity guards refuse duplicate quote sides
and ambiguous reduced-key joins; decision-time vendor timing enforced
(morning lag >= 18000 s, close >= 300 s; T-1h quote refused); fail-
closed on absent envelope/event map; panel projected to minimum
identity/date/line/settlement fields; book-lines game_date pushdown
(deterministic rg11-rg17 scope for 2025H1). 14 tests green. Executed
once under a single-run order: STOPPED at the exact-identity guard
(3 duplicate-event contracts); receipt preserved; CLOSED as the
execution of record. The identity-exclusion policy PR above handles
the declared recovery.

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
