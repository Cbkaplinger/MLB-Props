---
name: audit-feature-leakage
description: Read-only leakage audit of MLB feature code and datasets. Use when adding or reviewing features, rolling windows, joins, or train/serve paths; trigger phrases include "leakage check", "is this feature safe", "as-of join", "train/serve skew". Planning and reading only; writes nothing.
disable-model-invocation: true
---

# Audit Feature Leakage

## Purpose

Find data leakage before it becomes a model or policy claim. Inspect feature code, joins, and dataset builds for information that would not be known before first pitch, and report what is safe, unsafe, or unknown.

## Preconditions

- Read `AGENTS.md` and `CONTEXT.md` first.
- Know the target grain (game/start or PA) and the seasons in play (2023-24 train, 2025 benchmark, 2026 locked).
- Work from the repo: `src/Python/`, `research/offseason_2026/`, dataset manifests. Do not glob `data/` or `artifacts/` parquet to "discover" the repo.

## Allowed

- Read code, configs, registries, manifests, and dated reports.
- Trace column lineage from raw Savant fields to training rows.
- Ask for a specific file, date range, or column definition when evidence is missing.

## Prohibited

- No code edits, no dataset builds, no training, no scoring, no backtests.
- No production writes (live scorers, policy JSONs, schedules, ledgers).
- No 2026 tuning: never use 2026 outcomes to bless or adjust a feature, floor, or weight.
- No copying employer or third-party skill text; author findings in this repo's words (PA, TBF, xK, frozen champion, challenger).

## Required inputs

- Feature or dataset under audit (module path or card name).
- Grain and population (e.g. qualifying starters PA>=9, 2024 PA population).
- Availability claim: when is each input known relative to first pitch.

## Workflow

1. List every input column and its upstream source with an availability timestamp.
2. Check each against the forbidden set: same-game K/PA/Outs/k_rate/actual TBF, current-game rolling contributions, future dates/seasons/lineups/park outcomes, raw IDs/names/teams/dates/join keys.
3. Check join mechanics: as-of direction, current-row inclusion, rolling-window shift (prior games only, current date excluded), fold-fitted transforms (fit on train dates only), actual vs projected lineups (train uses first-9-by-PA; live uses announced order), close-price or outcome leakage, 2026 contamination of train/preprocessing/selection.
4. Check train/serve parity: do fit-time and score-time features use the same definition and the same projected (never actual) TBF.
5. Classify each finding: blocking (must fix before use), major, minor, or note.

## Validation gates

- Every unsafe/unknown claim names the file and line or manifest key.
- `features.py` registry behavior confirmed for any new numeric column (fails loudly vs silently entering training).
- Rolling logic confirms prior-games-only with yearly reset; park confirms prior-seasons-only.

## Required outputs

- Lineage table: column | source | known-when | verdict.
- Severity table: finding | severity | evidence (file:line) | fix.
- Blocking findings listed first. Anything unverifiable is marked unknown, never assumed safe.

## Stop conditions

- Stop if the audit target is unclear (ask for the module or card).
- Stop if evidence lives only in generated parquet with no code or manifest to audit (report unknown, do not reverse-engineer outcomes).
- Stop before any edit, run, or 2026 comparison; this skill reads only.

## Repository evidence

Read when relevant:

1. `docs/reference/model-card.md` -- leakage policy plus target and cohort definitions (k_rate, PA>=9 filter).
2. `docs/reference/research_assistant_instructions.md` -- leakage and feature-safety rules for rolling, park, and registry gates.
3. `src/Python/features.py` -- registry gate behavior: what happens to unknown numeric columns.

If canonical sources disagree, stop and report the conflict. Do not silently choose the newest file.
