---
name: grill-with-docs
description: Relentless interview that sharpens a plan and updates docs inline. Use before building anything fuzzy; trigger phrases include "grill this plan", "pressure-test", "sharpen this design". Interview plus scoped doc updates; never implements the plan itself.
disable-model-invocation: true
---

# Grill With Docs

> Adaptation of Matt Pocock's `grill-with-docs` (MIT, Copyright (c) 2026 Matt Pocock).
> Upstream: `https://github.com/mattpocock/skills` (`skills/engineering/grill-with-docs/`), commit `d81f3a183412e71a5b1e84ca21bc1a35eea03a60`.
> Local changes: domain docs repointed to `CONTEXT.md` + `docs/adr/` (no GLOSSARY.md unless a stub pointing at CONTEXT.md is also created); MLB safety block added (no 2026 tuning, no production writes, no experiment execution without separate authorization); no absolute paths to other checkouts or employer trees.
> Full MIT text in `docs/agent/skills-provenance.md`.

## Purpose

Resolve every branch of a plan's decision tree through relentless interviewing -- and capture the durable outcomes in `CONTEXT.md` terms and ADRs as they crystallize.

## Preconditions

- Read `AGENTS.md`, `CONTEXT.md`, and relevant ADRs before the first question.
- A plan, design, or question exists to grill. If there is nothing to grill, say so.

## Allowed

- Ask hard questions: constraints, dependencies, populations, comparators, metrics, slices, rollback, what kills the idea.
- Update `CONTEXT.md` glossary terms inline when a decision genuinely sharpens or adds a term.
- Offer an ADR (via `/write-adr` rules) when a load-bearing reason emerges that future sessions need.

## Prohibited

- No implementing the plan, no running experiments, no code/config/policy/ledger changes.
- No production writes of any kind.
- No 2026 tuning: do not steer the plan toward selecting or retuning from 2026 paper or juiced 2026 slices.
- No inventing Accepted ADRs; evidence-poor outcomes stay Proposed or stay in the conversation record.

## Required inputs

- The plan or design under grill (text or file pointer).
- Decision owner for branches only the user can resolve.

## Workflow

1. Restate the plan in one paragraph using `CONTEXT.md` terms; confirm understanding before grilling.
2. Walk the decision tree branch by branch: goal, constraints, population/splits, comparator, metrics and kill criteria, risks, rollback, open questions. One branch at a time; do not move on with unresolved load-bearing branches.
3. As decisions crystallize: sharpen the term in `CONTEXT.md` (only when meaning really changed), or note the ADR to write (only when a future session would otherwise re-suggest the rejected path).
4. End with the resolved plan, the remaining open questions with owners, and the docs touched.

## Validation gates

- Every load-bearing branch has a resolution or a named owner + question.
- Doc updates use repo vocabulary (PA, TBF, xK, champion, challenger, grains, periods).
- No plan step assumes 2026 selection data, production writes, or unapproved execution.

## Required outputs

- Resolved plan summary + open-question list with owners.
- Docs touched: `CONTEXT.md` terms and/or ADR paths (or "none").

## Stop conditions

- Stop when all branches resolve or the user calls it; report what is still open.
- Stop if grilling reveals there is no plan (say so, do not invent one).
- Stop before any implementation or execution; that needs a separate order.
