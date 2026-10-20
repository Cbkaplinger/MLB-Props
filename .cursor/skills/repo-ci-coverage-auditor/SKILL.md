---
name: repo-ci-coverage-auditor
description: Maps what CI actually collects and exercises in MLB-Props (testpaths, excluded suites, subprocess-tested runners, coverage vs claims) and proposes minimal NON-WEAKENING coverage fixes. Use when CI green is doubted, a research/harness suite is missing from default runs, or a test gap is suspected.
---

# CI coverage auditor

## Trigger
Doubt that CI green means tested; a suite found outside default collection;
untested production surface suspected; coverage report requested. Does NOT
apply to: writing production tests (builder lane), CI workflow edits without an
approved slice.

## Explore first (required inventory)
1. Collection facts: `testpaths` in pyproject + pytest discovery defaults →
   exact collected vs excluded file lists (last audit: 83 collected under
   `tests/`, 5 excluded under `research/`).
2. Import-based coverage: which modules do tests import directly; which
   production entry points have no test anchor.
3. Subprocess/CLI-tested code is INVISIBLE to import analysis — check for
   test-of-underlying-module before claiming a gap (real incident:
   `grade_odds_ledger.py` sits atop directly-tested `odds_ledger.py`).
4. Marker lanes: `integration` marker skips with named reasons when lake inputs
   are absent and fails loudly on hash mismatch — preserve this pattern.

## Scope
`.github/workflows/ci.yml` (read; edits only via approved slice), `pyproject.toml`
pytest config, `tests/`, research harness test dirs, suite inventory. Never:
weakening the main suite, path filters on it, test semantics of other lanes.

## Evidence
Collected/excluded file lists (exact), import-graph coverage map, marker-lane
behavior, suite runtimes. Every gap claim names the module, the test that would
cover it, and the exact command.

## Allowed output
Coverage map (collected/excluded/gap); minimal non-weakening fix spec (e.g.
explicit research-lane pytest step with strict failure); smoke-existence test
proposals (the Issue #5 class).

## Never do
Add path filters or `--continue-on-collection-errors` to the MAIN suite;
auto-delete or skip tests; claim a module untested without the subprocess check;
edit workflow files without an approved slice.

## Stop condition
Collected and excluded lists are exact and every gap has either a spec or an
explicit accepted-risk note.

## Escalation
Workflow edits → owner approval (standing rule). Research-lane test additions →
Chat 1 awareness (their lane's suites).

## Glossary
Coverage map, non-weakening, marker lane, skip-with-named-reason — see
[repo-garbage-collector/LANGUAGE.md](../repo-garbage-collector/LANGUAGE.md).
