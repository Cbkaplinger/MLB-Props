---
name: audit-backtest-integrity
description: Read-only backtest and replay integrity audit. Use when reviewing a backtest, replay ledger, or ROI claim; trigger phrases include "backtest review", "replay audit", "is this ROI honest". Reads only; writes nothing.
disable-model-invocation: true
---

# Audit Backtest Integrity

## Purpose

Stress-test whether a backtest or replay measures the frozen model at bettable prices and clocks -- or manufactures edge through selection, contamination, or unfillable quotes.

## Preconditions

- Read `AGENTS.md`, `CONTEXT.md`, `docs/reference/oddsapi_replay_architecture.md`, and `docs/reference/experiment_sop.md` section 8.
- Identify the replay under audit (script, report key, artifact) and its decision policy version.

## Allowed

- Read replay scripts, join keys, envelope/manifest files, reports, and choice logs.
- Trace clocks (friend open / paid morning / paid close / live poll), book universe, and fill assumptions.

## Prohibited

- No re-running replays, no rebuilding panels, no retuning policy.
- No production writes of any kind.
- No 2026 tuning: 2026 juiced slices are confirmatory; never a promotion license.
- No treating fair-price harness ROI as a betting slip.

## Required inputs

- Replay identity (script + report/artifact key).
- Claimed slice and metric (n, ROI/WR, CLV, Brier/skill).
- Price and clock definitions used (juiced book pair, open vs morning decision, close for evaluation only).

## Workflow

1. Check selection bias: were filters locked before the panel existed; is the full candidate set (rejected rows kept with reasons) visible.
2. Check policy overfitting: count configs searched vs reported; White/PBO/DSR treatment for policy families; LCB and stability across months, not max ROI.
3. Check temporal contamination: vendor timestamps vs reconstructed clocks; post-commence "closes" dropped; 2026 peek discipline; frozen stack never predates its own influence (weights/calibrator dates).
4. Check quote availability: two-way quotes required; book universe declared (next-book canonical vs DK+FD-only sensitivity, never mixed); BetRivers-type soft-book soak disclosed; alt-line vs main-market shape separated.
5. Check settlement honesty: push/void handling, dedupe (one slip per signal), duplication keys, correlated selections (slate/game caps or disclosure), staking changes labeled per arm, fills unmodeled unless stated.
6. Check choice log and pre-registration: decision logged before the run; deviations recorded; locked retrospective rules honored.

## Validation gates

- Same-subset skill: challengers share n/dates/join or the difference is labeled.
- CLV on devigged pairs only, sign/scale correct; same-book headline vs consensus secondary.
- Missing-close rate and denominator rules stated.

## Required outputs

- Integrity table: check | verdict | evidence (file:line or report key).
- Blocking findings first; unverifiable items marked unknown.
- Honest restatement of the claim with its lane (fair vs juiced, next-book vs DK+FD, selection vs confirmatory year).

## Stop conditions

- Stop if the replay script, report, or policy version cannot be identified (ask).
- Stop if the audit would require re-running history (report as unverifiable).
- Stop before any policy edit or live change; this skill reads only.

## Repository evidence

Read when relevant:

1. `docs/reference/market_clv_gates.md` -- CLV sign/scale definitions and gate thresholds.
2. `docs/reference/reports/policy_reset_2025lock_prereg_2026-09-11.md` -- 2025-lock selection precedent and peek disclosure.

If canonical sources disagree, stop and report the conflict. Do not silently choose the newest file.
