---
name: improve-codebase-architecture
description: Survey the codebase for deepening opportunities and grill the pick. Use when a module feels shallow, logic leaks across seams, or tests are hard to write; trigger phrases include "architecture review", "deepen this module", "codebase survey". Survey and plan only; implementation needs a separate user order.
disable-model-invocation: true
---

# Improve Codebase Architecture

> Adaptation of Matt Pocock's `improve-codebase-architecture` (MIT, Copyright (c) 2026 Matt Pocock).
> Upstream: `https://github.com/mattpocock/skills` (`skills/engineering/improve-codebase-architecture/` + `HTML-REPORT.md`), commit `d81f3a183412e71a5b1e84ca21bc1a35eea03a60`.
> Local changes: domain docs repointed to `CONTEXT.md` + `docs/adr/` (no GLOSSARY.md); MLB safety block added (frozen stack, no 2026 tuning, research-vs-production); HTML report kept as an OS-temp artifact; no absolute paths to other checkouts or employer trees.
> Full MIT text in `docs/agent/skills-provenance.md`.

## Purpose

Surface architectural friction and propose deepening opportunities: refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability of this repo's pipeline and ops code.

## Preconditions

- Read `AGENTS.md`, `CONTEXT.md`, and any ADRs in the area being touched (`docs/adr/`). Do not re-litigate accepted ADRs without real friction.
- Know the hot spots: walk back commit history (`git log --oneline`) and weight recently changed areas. If the user named a module or pain point, take it.
- Keep this repo's vocabulary: module, interface, seam, adapter, leverage, locality; domain terms from `CONTEXT.md` (PA, TBF, xK, champion, challenger). Do not drift into employer-specific terms.

## Allowed

- Read code, tests, callers, configs, registries, and docs.
- Write one self-contained HTML report to the OS temp dir (fresh file per run); tell the user the absolute path.
- Ask which candidate to explore; grill the pick with constraints, dependencies, seam shape, and surviving tests.

## Prohibited

- No code, config, policy, schedule, or ledger changes from this skill. Survey and plan only.
- No touching protected production paths (`market.py`, `count_layer.py`, `live_assembly.py`, `odds_ledger.py`, board/poll, policy JSONs, model artifacts) beyond reading.
- No 2026 tuning, no retrain proposals, no live-policy changes.
- No new top-level folders without a comparison of alternatives. No second sources of truth (backlog stays the queue; `CONTEXT.md` stays the glossary).
- No broad writes without explicit user approval; characterization tests first when implementation is later ordered.

## Required inputs

- Scope: user-named direction or permission to infer hot spots from history.
- Report depth: candidate count and whether diagrams are wanted.

## Workflow

1. Explore: scope before scanning (YAGNI). Read `CONTEXT.md` + nearby ADRs, then walk the code noting friction: concepts split across many small modules; shallow modules (interface nearly as complex as implementation); pure functions extracted for testability while bugs hide in callers (no locality); tightly coupled modules leaking across seams; untested or hard-to-test interfaces. Apply the deletion test: would deleting it concentrate complexity or just move it.
2. Present: one HTML file in OS temp (Tailwind + Mermaid via CDN; Mermaid for graph-shaped relations, hand-built divs/SVG for editorial visuals). Each candidate card: files, problem (one sentence), solution (one sentence), wins (short bullets in locality/leverage terms), before/after diagram, recommendation strength (`Strong` / `Worth exploring` / `Speculative`). End with a top recommendation. If a candidate contradicts an ADR, flag it explicitly and only when the friction warrants reopening.
3. Grill: once the user picks a candidate, walk the decision tree (constraints, dependencies, deepened-module shape, seam contents, surviving tests). Side effects inline only: sharpen a `CONTEXT.md` term where it genuinely changed meaning, or offer an ADR when the rejection reason is load-bearing for future explorers. Then stop; implementation is a separate order (`/consolidate-code` owns the merge plan).

## Validation gates

- Every candidate names real files and the seam it deepens.
- ADR conflicts flagged, not silently listed.
- Report path reported; nothing written into the repo by the survey.

## Required outputs

- HTML report path + candidate cards + top recommendation.
- Grilling record for the picked candidate (decision, constraints, next step).

## Stop conditions

- Stop if scope is unbounded (ask for a module or pain point).
- Stop after the report if the user picks nothing; do not implement unasked.
- Stop before any repo write except an explicitly requested `CONTEXT.md` touch-up or ADR offer.
