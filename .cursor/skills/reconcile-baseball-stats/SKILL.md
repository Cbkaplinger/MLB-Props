---
name: reconcile-baseball-stats
description: Read-only reconciliation of derived baseball totals to official records. Use when PA/K/BF totals disagree, attribution is unclear, or a dataset needs validation; trigger phrases include "reconcile totals", "box score check", "attribution", "split pitcher". Reads only; writes nothing.
disable-model-invocation: true
---

# Reconcile Baseball Stats

## Purpose

Prove that derived pitch, PA, and game totals tie to official pitcher and box-score totals -- or pinpoint exactly where they diverge and why.

## Preconditions

- Read `AGENTS.md` and `CONTEXT.md` (grains + PA-overhaul attribution rule).
- Know the population (qualifying starters PA>=9, PA-level table, or slate) and the official source of truth (box score / Stats API / Savant event rows).

## Allowed

- Read pipeline code (`pipeline/games.py`, rolling, training), dataset cards, manifests, and reports.
- Work unit arithmetic in small checked steps (counts, not models).

## Prohibited

- No dataset rebuilds, no code edits, no training or scoring.
- No production writes.
- Never silently reassign strikeout or PA attribution; official scorer convention governs.

## Required inputs

- Derived total under test (table/card + row count + filters).
- Official total it should match (source + game/date scope).
- Grain: pitch vs PA vs AB vs BF.

## Workflow

1. Fix definitions: pitch vs PA vs AB vs BF; official starter vs opener vs bulk vs terminal pitcher; truncated, suspended, or split-pitcher PAs.
2. Apply the attribution rule: the K is credited to the pitcher who threw the third-strike pitch; the PA is charged to the completing pitcher; flag splits (`split_pa_flag`).
3. Reconcile in layers: pitches to PAs, PAs to pitcher games, pitcher games to box scores; record n_in / n_matched / unmatched-why at each join.
4. Isolate divergences: opener/bulk splits, mid-PA changes, field-error PAs, unknown labels, doubleheaders, neutral-site keys, excluded game_pks.
5. Confirm cohort filters (PA>=9 postgame filter) are applied identically on both sides before comparing.

## Validation gates

- Every join emits counts and unmatched reasons; no silent drops.
- Split-PA rows identified and handled per card spec (excluded from single-pitcher primary purity where required, disclosed elsewhere).
- Final match rate stated with the residual list, not just a percentage.

## Required outputs

- Reconciliation table: layer | derived | official | delta | explanation.
- Residual list: each unmatched group with cause and disposition.
- Verdict: reconciled, reconciled-with-disclosure, or blocked (with the exact rows to inspect).

## Stop conditions

- Stop if the official source or population filter is undefined (ask).
- Stop if reconciliation needs data that does not exist locally (report unknown).
- Stop before any rebuild or relabeling; this skill reads only.

## Repository evidence

Read when relevant:

1. `docs/reference/reports/pa_overhaul_phase4_5_record_2026-09-29.md` -- attribution rule and split-PA convention (section 4).
2. `docs/reference/model-card.md` -- target and cohort definitions (k_rate, PA>=9 filter).

If canonical sources disagree, stop and report the conflict. Do not silently choose the newest file.
