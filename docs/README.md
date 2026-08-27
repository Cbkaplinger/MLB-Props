# Documentation

This folder is trimmed to one rule: active operations live in `production/`
and supporting standards live in `docs/reference/`.

## What to read first

- `../production/README.md` for day-to-day execution.
- `reference/model-card.md` for model scope and constraints.
- `reference/daily_kpi_protocol.md` for gate definitions.
- `paper/manuscript.md` for full system narrative.

## Folder map

- `paper/`: manuscript and publication artifacts.
- `reference/`: living production standards and protocols.
- `research/`: evidence trail and freeze rationale.
- `diagrams/`: architecture and risk visuals.
- `archive/`: deprecated or superseded material.

## Operating scope (current)

- Production claim lane: pitcher strikeouts only.
- Expansion lane in progress: pitcher outs/hits/walks through shadow artifacts and watcher capture, without production promotion yet.
- Source of truth for expansion status: runtime dashboard + `artifacts/odds_log/aux_market_shadow_summary.json`.

## Bloat control policy

- New dated reports go under `reference/reports/`.
- Snapshot-style experiment notes go under `research/snapshots/`.
- Avoid creating new top-level ad-hoc markdown unless it is a long-lived
  canonical document.
