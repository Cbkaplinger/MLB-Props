---
name: compare-champion-challenger
description: Read-only champion-vs-challenger comparison audit. Use when judging a challenger, reviewing a comparison report, or checking a promotion claim; trigger phrases include "compare challenger", "should this promote", "challenger review". Reads only; a written summary only if the user authorizes it.
disable-model-invocation: true
---

# Compare Champion Challenger

## Purpose

Judge whether a challenger beats the frozen champion on the same observations, same quotes, and same targets -- with probability metrics first, trading metrics second, and complexity penalized.

## Preconditions

- Read `AGENTS.md`, `CONTEXT.md`, `docs/reference/champion_challenger_protocol.md`, and `docs/reference/experiment_sop.md`.
- Champion pointer is frozen (artifact hash + policy version). Challenger artifact is identified.
- Comparison panel or report exists; this skill does not build panels or run models.

## Allowed

- Read panels (via manifests/reports, not raw parquet discovery), code, cards, and decision JSONs.
- Recompute nothing from raw outcomes; verify arithmetic from cited artifacts when cheap.
- With explicit user authorization, write a short comparison summary only (no code, config, or ledger changes).

## Prohibited

- No training, scoring, re-spinning the model, or rebuilding panels.
- No production writes (live scorers, policy JSONs, schedules, ledgers).
- No 2026 tuning: do not promote, retune, or re-rank from 2026 paper or juiced 2026 slices.
- No promoting fair-price harness ROI as a betting claim; no mixing SharpAPI live CLV with Odds API juiced replay as one number.

## Required inputs

- Champion id (artifact + policy version) and challenger id (artifact + card).
- Evaluation panel identity (dates, n, join audit) or the report under review.
- Decision tier being claimed (Tier 1 quality / Tier 2 policy-risk / Tier 3 stability).

## Workflow

1. Confirm paired observations: same starts, same lines, same books, same timestamps on both arms; label any mismatch.
2. Confirm temporal validity (chrono-safe, date-disjoint) separately from mechanical replayability (same code path, pinned versions).
3. Check probability metrics first: Brier skill vs market > 0, logloss skill > 0, pooled + per-line + same chrono split.
4. Check policy/risk gates: n_bets >= 25, roi > 0, sortino >= 0.25, profit_factor >= 1.20, drawdown/CVaR not materially worse.
5. Check stability: full history + last 60 + last 30 settled; same family top-2 across windows; no window failing both Tier 1 gates.
6. Check intervals (bootstrap/CI method named), slice stability, single line/side dominance, and book-universe honesty (next-book vs DK+FD-only reported separately).
7. Apply deterministic tie-break order from the protocol; penalize complexity (small linear first; GBM-on-top needs a linear loss first).
8. Verify rollback plan exists (prior bundle hashed + restorable) before any PROMOTE language.

## Validation gates

- Same-subset rule: identical n/dates/join or labeled difference.
- Main-market only; devigged-pair CLV sign/scale correct (never raw-implied vs fair).
- Required artifacts present or explicitly missing: skill compare, governance compare, floor sweep, decision JSON, freeze card.

## Required outputs

- Verdict table: gate | champion | challenger | pass/fail | evidence.
- Labeled gaps: what is missing for PROMOTE vs HOLD vs RESEARCH.
- Rollback and revert path status.

## Stop conditions

- Stop if champion pointer or panel identity is unknown (ask).
- Stop if the claim needs 2026 selection data (refuse promotion; confirmatory read-only only).
- Stop before writing anything except an authorized summary; never touch production.

## Repository evidence

Read when relevant:

1. `production/ops/live_krate_ensemble.json` -- where the live champion pointer lives (read-only; never edit from this skill).
2. `docs/reference/golden_metrics.md` -- cite canonical numbers and their JSON sources; do not recompute.

If canonical sources disagree, stop and report the conflict. Do not silently choose the newest file.
