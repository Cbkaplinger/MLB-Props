# Documentation

This folder is trimmed to one rule: active operations live in `production/`
and supporting standards live in `docs/reference/`.

## What to read first

- **`EXECUTION_BACKLOG.md` — master work-state / approvals / next-session plan** (holy file; agents open this first).
- `../AGENTS.md` — short pointer to that backlog for agent sessions.
- `../production/README.md` for day-to-day execution commands.
- `reference/model-card.md` for model scope and constraints.
- `reference/daily_kpi_protocol.md` for gate definitions.
- `paper/manuscript.md` for full system narrative.
- `reference/research_assistant_instructions.md` for technical constraints (**not** a todo list).

## Folder map

- `EXECUTION_BACKLOG.md`: **single source of truth** for APPROVED / BLOCKED / deferred work and PAST/PRESENT/FORWARD/DEFERRED.
- `paper/`: manuscript and publication artifacts.
- `reference/`: living production standards and protocols.
- `reference/reports/`: dated evidence reports (subordinate to the backlog for “what next”).
- `research/`: evidence trail and freeze rationale.
- `diagrams/`: architecture and risk visuals.
- `archive/`: deprecated or superseded material.
- `CLEANUP_LOG.md`: historical cleanup log (not instructions).

## Operating scope (current)

- Production claim lane: pitcher strikeouts only.
- Expansion lane in progress: pitcher outs/hits/walks through shadow artifacts and watcher capture, without production promotion yet.
- Source of truth for expansion status: runtime dashboard + `artifacts/odds_log/aux_market_shadow_summary.json`.
- Source of truth for **what to build/promote next:** `EXECUTION_BACKLOG.md`.

## Bloat control policy

- New dated reports go under `reference/reports/` and must not invent a parallel work queue — point to `EXECUTION_BACKLOG.md` for next actions.
- Snapshot-style experiment notes go under `research/snapshots/`.
- Avoid creating new top-level ad-hoc markdown unless it is a long-lived
  canonical document (and even then, do not duplicate backlog items).
