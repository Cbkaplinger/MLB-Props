---
name: repo-dependency-hygiene
description: Reconciles declared vs imported dependencies in MLB-Props (pyproject tiers vs the actual import surface), inventories environment variables and config provenance, and proposes declaration diffs, extras taxonomies, and lockfile policy. Use when an import is undeclared, an extra is misplaced, a lockfile question arises, or env-var/config provenance is unclear.
---

# Dependency hygiene

## Trigger
Undeclared import found; extras/tier questions; lockfile policy; env-var or
data-root provenance unclear; fresh-install reproducibility doubt. Does NOT
apply to: editing pyproject/CI without an approved slice; production env config
changes.

## Explore first (required inventory)
1. Import surface: all tracked `.py` third-party imports (stdlib-filtered,
   internal conventions resolved — bare stems, dotted, `Python.*`).
2. Declared set read directly from `pyproject.toml` (base + research + dev
   extras). Diff = undeclared / unused.
3. Per-import consumer attribution (which files import it) — tier placement
   follows consumers (base vs research vs paper vs deploy).
4. Env-var provenance: `os.environ`/`os.getenv`/`$env:` scan; secrets are
   env-sourced and never printed.

## Scope
`pyproject.toml` (proposal only until approved), import surface, env-var
inventory, lockfile policy. Never: package installation, version bumps without
owner order, deploy secrets handling.

## Evidence
Per package: consumers, tier proposal, declaration status; per env var: consumer
files, required-vs-optional, default behavior, documentation status. Verification
= fresh-venv smoke install + import check, never "works locally".

## Allowed output
Declaration diff spec (exact pyproject lines); extras taxonomy; lockfile option
comparison; env-var reference table; report-first findings.

## Never do
Edit pyproject/CI without an approved slice; declare an import without verifying
it is a real PyPI package (real incident: `sage` needed verification — possibly
legacy debris); move secrets into files; propose base-tier for research-only
heavyweights.

## Stop condition
Every import is declared, or has a tier proposal + owner gate; every env var is
documented or queued for the runbook slice.

## Escalation
Tool choice (uv/pip-tools/pins) → owner. Deploy-tier placement → Chat 1/owner.

## Glossary
Tier (base/research/paper/deploy/dev), undeclared, extras, lockfile — see
[repo-garbage-collector/LANGUAGE.md](../repo-garbage-collector/LANGUAGE.md).
