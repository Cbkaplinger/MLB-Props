# PROJECT_STORY — what has been done and what was learned (in time order)

**Status:** living narrative. Assembled 2026-10-21 from `docs/research/PAPER_NOTES.md`,
`docs/research/statistical_audit_and_sequencing_report.md`, and `docs/DECISIONS.md`.
Reconciled against canonical accepted records 2026-10-27 (Chat 3; delta review on
PR #46). Distinguishes **reported results** from **accepted evidence**; the work
queue lives only in `docs/EXECUTION_BACKLOG.md` (not duplicated here). Production
champion history and PA research findings are kept in separate sections.

## The problem

Predict whether an MLB starting pitcher records a strikeout (K) against a
given batter before first pitch, and whether an exploitable pricing gap
exists against sportsbooks — under honest, leakage-safe measurement.

## Approaches, in order (production champion lane)

1. **Data foundation (2026-07/08).** Statcast ingestion (2015-2026 raw;
   2023-2025 pipeline seasons), L1-L3 pipeline (games, rolling, training
   frames), point-in-time feature discipline (forecast cutoff: no feature at
   or after first pitch). Evidence: `docs/research/` step reports,
   `docs/reference/pipeline_registry.json`.
2. **Model search (frozen).** Mean / Ridge / LightGBM k-rate models,
   chronological date-disjoint splits (TRAIN_SEASONS 2023-2024), TBF ridge,
   Poisson count layer with per-line WS1c Platt calibration. Selected via
   pre-registered champion selection (2025-lock: floor 0.12 / cap 0.24 /
   under-lean / DK+FD-only, White-checked). Frozen; retrain path closed
   (evidence: `docs/reference/model-card.md`, `docs/DECISIONS.md`; note: the
   ADR register contains PROPOSED records only — no accepted ADR numbers this).
3. **Decision policy.** Post-freeze diagnosis showed side/line failure
   (overs bleed at low lines), not a universal floor problem. Response:
   4.5-over hard veto + 2.5/3.5 probation, 2025-lock selection (floor 0.12 /
   cap 0.24 / under-lean / DK+FD), flat $50 sizing. Promoted with disclosed
   2026 peek. The judge figure was revised down 2026-09-17 from disk truth:
   champion n=460 / +8.7% / WR 0.574, 2026-judge LCB +0.16% (supersedes the
   n=485 / +15.6% peek figures still printed in `docs/paper/manuscript.md` —
   see `docs/reference/reports/monthly_summary_2026-09-17.md`).
4. **Delivery hardening.** Cloud cutover (Modal, 2026-09-16), DST-exact
   schedules, one-slip-per-signal logging, family dedupe, serving gates,
   manifests and pins. Deployed topology stayed up; betting was paused at
   season end (postseason HOLD, 2026-09-27, `kpi_policy.json`).
5. **Governance era (2026-10).** Cleanup skill system, quality corpus,
   worktree consolidation, DECISIONS register, PROPOSED delivery ADR/PRD.

## PA research lane (separate from the production champion)

- **Question A, count aggregation (2026-10-21):** the exact heterogeneous
  count-aggregation diagnostic was executed once on an eligible development
  subset and recorded — authoritative record:
  `research/offseason_2026/pregame_pa_ext/results_count_agg_eval_v1/RESULT_RECORD.md`
  (commits `6000631`, `c9ab8f2`; merged PR #25). This is **component-level
  development evidence on an eligible subset**; it has NOT passed
  calibration/policy/decision-layer replay, and component migration is NONE
  (the count layer keeps the slot-average aggregator, per DECISIONS D2).
- **Question B pre-registration card** issued (PR #25); its primary candidate
  C-B1 is closed per `docs/NEXT.md` (2026-10-27) — do not rebuild.
- The two reconstruction/scoring commands and their run receipts are recorded
  in `research/offseason_2026/pregame_pa_ext/COUNT_EVAL_COMMANDS.md`
  (status 2026-10-20; navigation notice 2026-10-27).

## Accepted findings (accepted evidence)

- **Frozen stack beats its own ablations on the registered metric** at freeze
  time; the retrain lane stays closed (model card; DECISIONS register).
- **Decision-layer concentration (production lane):** skill vs market is
  negative (Brier skill vs book -0.0043 universe / -0.0021 bet sets,
  `docs/reference/golden_metrics.md` §A); the PnL evidence lives in selection
  and timing (champion selection, juiced replay ledger §F, CLV flavors).
- **Discipline findings that held:** frozen populations, slate-date clustered
  resampling, immutable receipts, separate authorization.

## Rejected findings (closed recipes; valid completed milestones)

- Batter-history challenger (R60/m30 recency recipe): worse by +0.00062 log
  loss, CI excluding zero — recipe rejected, recency modeling not condemned
  (`docs/reference/reports/backlog_archive_2026-10-21.md`).
- Glicko overlay, Kalshi-disagreement filter, September premium, stacker ROI
  lane, alt-ladder, MC-as-scorer: each closed by its pre-registered gate.
- Decision-flip claim (PR #29 lineage): **REPORTED, EXECUTION STATUS
  UNRESOLVED** per `docs/DECISIONS.md` D2 — builder reported one flip in
  19,292; Chat 1 disputes the components at the claimed SHA; no immutable
  execution artifact verifies it. Treated as reported, not accepted evidence.

## Current state (as of 2026-10-27)

- **Champion lane:** frozen stack deployed (Modal, ET-local crons) but
  betting paused since 2026-09-27 (postseason HOLD); real-data execution of
  new experiments owner-gated.
- **PA research lane:** Stage A prediction-path equivalence work active
  (PR #49 per `docs/NEXT.md` 2026-10-27); calibration execution, Stage B,
  new model families, market reconstruction, Kelly, and live execution are
  deferred. M0 multiclass runner holds development acceptance (2026-10-22,
  five-blocker repair, synthetic-tested) — implementation readiness, NOT a
  predictive-gain claim and NOT production approval.
- **Open owner decisions:** abstain-vs-handle for the 59 pitcher-cold starts
  (57 debut-date newcomers + Enns/Hart) — recorded 2026-10-20 and still not
  named as resolved in any accepted record; Question B sequencing per
  DECISIONS D2.

## Remaining questions (the honest list)

- Does any PA-level or aggregation gain survive calibration, policy, and the
  decision layer to produce profit? (Separate replay with prices; confirmation
  block untouched.)
- Can an accepted result be reproduced from a clean environment through the
  documented data route?
- Does the operating pipeline detect bad inputs and recover without
  misleading outputs?

## Limitations

All predictive metrics to date are development-population claims with
clustered-resample uncertainty; the confirmation block is untouched;
real-input identities are implemented/synthetic-exercised, not
real-verified; no institutional-parity claim is made or implied.
