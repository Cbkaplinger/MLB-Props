# PROJECT_STORY — what has been done and what was learned (in time order)

**Status:** PROPOSED draft (2026-10-21; Chat 3, assembled per assignment from
`docs/research/PAPER_NOTES.md`, `docs/research/statistical_audit_and_sequencing_report.md`,
and `docs/DECISIONS.md`). Distinguishes **reported results** from
**accepted evidence**; the work queue itself lives only in
`docs/EXECUTION_BACKLOG.md` (not duplicated here).

## The problem

Predict whether an MLB starting pitcher records a strikeout (K) against a
given batter before first pitch, and whether an exploitable pricing gap
exists against sportsbooks — under honest, leakage-safe measurement.

## Approaches, in order

1. **Data foundation (2026-07/08).** Statcast ingestion (2015-2026 raw;
   2023-2025 pipeline seasons), L1-L3 pipeline (games, rolling, training
   frames), point-in-time feature discipline (forecast cutoff: no feature at
   or after first pitch). Evidence: `docs/research/` step reports,
   `pipeline_registry.json`.
2. **Model search (frozen).** Mean / Ridge / LightGBM k-rate models,
   chronological date-disjoint splits (TRAIN_SEASONS 2023-2024), TBF ridge,
   Poisson count layer with per-line WS1c Platt calibration. Selected via
   pre-registered champion selection (2025-lock: floor 0.12 / cap 0.24 /
   under-lean / DK+FD-only, White-checked). Accepted and frozen; retrain path
   closed.
3. **Decision policy.** Post-freeze diagnosis showed side/line failure
   (overs bleed at low lines), not a universal floor problem. Response:
   4.5-over hard veto + 2.5/3.5 probation, 2025-lock selection (floor 0.12 /
   cap 0.24 / under-lean / DK+FD), flat $50 sizing. Promoted with disclosed
   2026 peek; 2026 judge +15.6% paper ROI on the locked champion.
4. **Delivery hardening.** Cloud cutover (Modal, 2026-09-16), DST-exact
   schedules, one-slip-per-signal logging, family dedupe, serving gates,
   manifests and pins.
5. **Governance era (2026-10).** Cleanup skill system, quality corpus,
   worktree consolidation, DECISIONS register, PROPOSED delivery ADR/PRD.

## Accepted findings (accepted evidence)

- **Frozen stack beats its own ablations on the registered metric** at freeze
  time; the retrain lane stays closed (ADR-0007 evidence; model card).
- **Decision-layer concentration:** edge lives in choice (clock, ticket,
  book), not raw probability — skill vs market is negative; selection and
  timing carry the PnL evidence (juiced replay, champion selection, CLV
  flavors).
- **Discipline findings that held:** frozen populations, slate-date clustered
  resampling, immutable receipts, separate authorization.

## Rejected findings (closed recipes; valid completed milestones)

- Batter-history challenger (R60/m30 recency recipe): worse by +0.00062 log
  loss, CI excluding zero — recipe rejected, recency modeling not condemned.
- Glicko overlay, Kalshi-disagreement filter, September premium, stacker ROI
  lane, alt-ladder, MC-as-scorer: each closed by its pre-registered gate.
- Question A (exact Poisson-binomial aggregation): built; a decision-flip
  result was REPORTED (one flip in 19,292) but its execution status is
  UNRESOLVED (same-SHA contradiction between builder/reviewer handoffs) —
  treated here as **reported, not accepted evidence**; no promotion
  (decision log, D2).

## Current state (as of 2026-10-21)

- Frozen stack live (Modal, ET-local crons); paper execution; real-data
  execution of new experiments owner-gated.
- M0 multiclass runner in implementation review (PR #34 lineage; status
  dated 2026-10-21) — **synthetic implementation readiness is NOT authorized
  real-data execution**; NOT READY for execution; repair batch with Chat 2,
  independent closure check with Chat 1.
- Open owner decisions: abstain-vs-handle for the 59 pitcher-cold starts
  (57 debut-date newcomers + Enns/Hart); Question B sequencing (decision-flip
  analysis first, per the architect).

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
