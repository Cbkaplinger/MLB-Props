---
name: write-adr
description: Draft or record an architecture decision with evidence. Use when a durable choice needs capturing; trigger phrases include "record this decision", "write an ADR", "decision log". May write the ADR file only; never invent Accepted status.
disable-model-invocation: true
---

# Write ADR

## Purpose

Capture durable decisions with their evidence so future sessions do not re-litigate or silently reverse them.

## Preconditions

- Read `AGENTS.md`, `CONTEXT.md`, and `docs/adr/TEMPLATE.md`.
- The decision is real (made or firmly proposed) and repo evidence exists or is named as missing.

## Allowed

- Read code, reports, cards, choice logs, and backlog entries for evidence.
- Write one ADR file under `docs/adr/` using the template.

## Prohibited

- Never invent an Accepted ADR without durable repo evidence (use `PROPOSED-*.md` instead).
- No production writes; no code changes; no retuning claims.
- No rewriting history: supersede with a new ADR, do not edit an Accepted one in place (append a Superseded note + pointer).

## Required inputs

- Decision statement (one paragraph).
- Status requested: Proposed or Accepted.
- Evidence list (paths, hashes, report keys, tests) -- required for Accepted.

## Workflow

1. Confirm the decision is durable (outlives one session) and not already recorded.
2. Fill the template: ID, Title, Status, Date, Context, Decision, Alternatives, Consequences, Evidence, Revisit trigger, Related code, Related experiments.
3. If evidence is thin, write `docs/adr/PROPOSED-*.md` and list exactly what would promote it to Accepted.
4. Cross-link: backlog entry, experiment card, or report that motivated it.
5. Keep candidate ADRs honest: PA-level matchup, no sparse pair memorization, frozen TBF for first PA challenger, temporal periods, Poisson-binomial later, champion/challenger gates, research isolation, doc retention -- evaluate against evidence, never invent.

## Validation gates

- Template fields all present; filename matches `NNNN-short-title.md` or `PROPOSED-*.md`.
- Accepted ADRs cite at least one repo path, artifact, report, or test.
- No duplicate of an existing ADR (check `docs/adr/` first).

## Required outputs

- ADR file path + status + evidence summary.
- Promotion checklist if Proposed (what evidence would accept it).

## Stop conditions

- Stop if the decision itself is still open (offer `/grill-with-docs` instead).
- Stop if evidence does not exist and the user demands Accepted (write Proposed and say why).
- Stop before touching anything outside `docs/adr/`.

## Repository evidence

Read when relevant:

1. `docs/reference/offseason_2026_choice_log.md` -- house style for evidence-linked decision entries.

If canonical sources disagree, stop and report the conflict. Do not silently choose the newest file.
