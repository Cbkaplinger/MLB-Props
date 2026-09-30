---
name: design-ml-experiment
description: Plan a leakage-safe ML experiment card without running it. Use when proposing a feature, challenger, calibration, or policy test; trigger phrases include "design an experiment", "experiment card", "how should we test this". Planning only; never executes the experiment.
disable-model-invocation: true
---

# Design ML Experiment

## Purpose

Turn a vague idea into an immutable, reviewable experiment plan that a later session can execute exactly once without improvising.

## Preconditions

- Read `AGENTS.md`, `CONTEXT.md`, and `docs/reference/experiment_sop.md`.
- The hypothesis fits one card: one comparator, one population, one kill metric.
- Target write path exists: `research/offseason_2026/experiments/<card>/`.

## Allowed

- Read code, registries, manifests, prior cards, and reports for precedent.
- Draft the card, manifest skeleton, and deviation log template as text for the user to approve.
- Reference canonical metrics: Brier/skill, logloss, ECE, MAE, ROI/WR, CLV.

## Prohibited

- Do not run the experiment, build datasets, train, score, or backtest.
- No production writes (live scorers, policy JSONs, schedules, ledgers).
- No 2026 tuning: 2026 is locked retrospective/confirmatory; selection uses 2025 or pre-registered 2023-24 folds.
- No overwriting a prior card; each card is immutable once run.

## Required inputs

- Hypothesis in one sentence (what changes, what improves, by how much).
- Comparator (frozen champion or named baseline, with artifact pointer).
- Population and temporal splits (train/select/judge dates, never split a date).

## Workflow

1. Fix the comparator and freeze its artifact pointer; record the code commit.
2. Define population, grains, and date-disjoint splits; state which season judges (2025 benchmark or future post-freeze, never recycled 2025 for selection).
3. Pre-register cells/slices BEFORE any panel exists where n allows fishing (lines, xK bins, TBF tails, month/hand/history slices).
4. Choose metrics in stage-gate order: probability skill (Brier/skill, logloss, ECE) before trading metrics (ROI/WR/CLV/Sharpe/drawdown).
5. Set bootstrap unit (default game-date-clustered, B=2000, seed fixed), promotion rule (kill metric threshold, e.g. held-out Brier gain >= 0.0005), and stop rule (max runs, kill criteria).
6. Record inputs/hashes, permitted deviations, and output paths (`experiments/<card>/` + manifest + deviations).
7. Confirm single-feature rule: ablate leave-one-in, one at a time, on a fixed base set (no family dumps).

## Validation gates

- Every choice answers: same n, same dates, same join as the comparator, or the difference is labeled.
- Main-market filter declared (`p_book_close` not null) before scoring; fair vs juiced price language consistent with live floors.
- No same-game actuals (K/PA/TBF) as inputs; projected TBF only.

## Required outputs

- Experiment card draft: hypothesis, comparator, population, splits, metrics, slices, bootstrap, promotion/stop rules, input hashes, deviation policy, output paths.
- Manifest skeleton and empty deviations log.
- Open questions the user must resolve before execution.

## Stop conditions

- Stop if the hypothesis, comparator, or judge season is missing (ask).
- Stop if the plan would need 2026 for selection (refuse; offer 2026-confirmatory framing instead).
- Stop before any execution; hand the card to the user for approval.

## Repository evidence

Read when relevant:

1. `docs/reference/offseason_2026_choice_log.md` -- pre-registration precedent: how decisions get logged before runs.
2. `docs/reference/reports/pa_overhaul_phase4_5_record_2026-09-29.md` -- card precedent: preflight gates, bootstrap spec, logged deviations.

If canonical sources disagree, stop and report the conflict. Do not silently choose the newest file.
