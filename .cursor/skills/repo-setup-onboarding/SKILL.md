---
name: repo-setup-onboarding
description: First-run onboarding for cleanup/quality agents in MLB-Props — records the repo's canonical paths (backlog, golden metrics, reports dir, lake boundary, env vars), confirms decisions with the user one at a time, and validates that the specialist cleanup skills have the context they need. Run before first cleanup use, or when a skill appears to be missing repo context.
---

# Setup onboarding

## Trigger
First cleanup run in a fresh clone; a specialist skill lacks repo context;
canonical paths moved; env-var inventory outdated. Modeled on the Qira-OS
`setup-qira-skills` pattern: prompt-driven, not deterministic; **explore,
present, confirm one decision at a time, then write.**

## Explore first (read whatever exists; don't assume)
1. `git remote -v` — which GitHub repo.
2. `AGENTS.md` — existing entry points and the cleanup-skills pointer.
3. `docs/EXECUTION_BACKLOG.md` — work-state owner (read-only for this lane).
4. `CONTEXT.md`, `docs/reference/repo_canonical_map.md`,
   `docs/reference/current_state_*.md`, `docs/reference/golden_metrics.md` — do
   they exist at expected paths?
5. `docs/reference/reports/` — quality-baseline branch outputs present?
6. Env-var inventory (`os.environ`/`$env:` scan) — data roots, lake root, keys.

## Scope
Present-and-confirm; writes only the artifacts the user approves (env-var
reference table, path manifest for the skills). Never: backlog edits, skill-file
creation without the governance slice, secret values printed or stored.

## Evidence
Each presented fact cites its source path. Unknowns are presented as unknowns
(fail-stop: a missing canonical doc is reported, not invented).

## Allowed output
Path/context manifest; env-var reference table (for the runbook slice);
gaps-list for the specialist skills; confirmed decisions recorded in the
quality-baseline branch reports.

## Never do
Assume a path exists; write without per-decision confirmation; touch
production/research/CI; print secret values.

## Stop condition
All six context areas verified or explicitly reported missing, and each
user decision answered.

## Escalation
Missing canonical docs → owner. Work-state conflicts → coordination.

## Glossary
Decision-at-a-time, fail-stop, path manifest — see
[repo-garbage-collector/LANGUAGE.md](../repo-garbage-collector/LANGUAGE.md).
