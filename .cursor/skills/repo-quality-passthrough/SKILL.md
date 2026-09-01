---
name: repo-quality-passthrough
description: Performs a safe repository cleanup pass by inventorying generated artifacts, stale caches, duplicate files, and dead scripts, then applying only low-risk cleanup changes with explicit guardrails. Use when the user asks to clean up the repo, reduce git noise, or run a quality passthrough.
disable-model-invocation: true
---

# Repo Quality Passthrough

## Goal

Run a repeatable, low-risk cleanup protocol that improves repository hygiene without deleting core source, production assets, or historical data blindly.

## Safety Rules

- Never use destructive git commands (`git reset --hard`, force push, history rewrites).
- Never delete production code, notebooks, or config files without explicit user approval.
- Treat data and artifacts as sensitive by default; prefer ignore rules over deletion unless asked.
- If unexpected external changes appear during work, pause and ask the user before proceeding.

## Cleanup Workflow

Copy this checklist and track progress:

```text
Task Progress:
- [ ] 1) Snapshot current git status
- [ ] 2) Inventory generated/stale files
- [ ] 3) Classify keep vs ignore vs delete candidates
- [ ] 4) Apply low-risk fixes (ignore rules, docs, naming cleanup)
- [ ] 5) Validate (status + lint for edited files)
- [ ] 6) Report what changed and what needs user approval
```

## File-By-File Decision Engine

For each candidate file, assign exactly one status:

- `keep`: actively used now, required for reproducibility, or protected by policy.
- `hold`: unclear usage, potential future value, or pending owner decision.
- `delete`: provably redundant/generated/disposable and safe to remove.

Apply this scoring rubric before any move/delete:

1. **Reference evidence**: Is the path referenced by scripts, notebooks, docs, tests, or task schedulers?
2. **Runtime criticality**: Is it on an ops path (`production/ops`, `production/odds`, `production/projections`, `production/notebooks`)?
3. **Provenance value**: Does it preserve historical or paper evidence that cannot be trivially regenerated?
4. **Regeneration cost**: Can it be recreated quickly and deterministically from tracked code?
5. **Duplication status**: Is it byte-identical or semantically duplicate of another retained file?

Decision rule:

- If (1) or (2) is true -> `keep`.
- If (3) is true and no active reference -> `hold`.
- If only generated cache/temp output and no provenance value -> `delete`.
- If uncertain at all -> `hold` and ask the user.

## Inventory Heuristics

Prioritize these targets first:

1. Build/runtime artifacts: cache folders, temp outputs, logs, binary leftovers.
2. Notebook churn artifacts: checkpoints and transient exports.
3. Duplicate paths from case drift (`data/` vs `data/`, `models/` vs `models/`).
4. Generated reports and large local outputs that should be ignored.

Then run redundancy checks:

- Name collisions (same basename in multiple families).
- Case collisions (`Data` vs `data`, `Models` vs `models`, `Artifacts` vs `artifacts`).
- Byte-identical duplicates (hash compare before deleting one).
- Near-duplicate script wrappers with overlapping orchestration behavior.

## MLB-Props Historical Rules

Use repository cleanup history as guardrails:

- Respect prior no-delete guidance for active `production/notebooks/*.ipynb` and `production/ops/*.py` families unless user explicitly approves.
- Treat `src/Python/` as pipeline-core and default to `keep`.
- Treat local `artifacts/{models,projection_log,odds_log,feature_research,stabilization,count_layer,model_quality,notebook_exec}/` as protected unless deletion is explicitly approved (prefer `.gitignore` coverage).
- Prefer documentation consolidation (link to canonical docs) over deleting nuanced historical notes.
- Before deletion, run dependency/reference checks and require smoke-check plan.
- **Work-queue canon:** `docs/EXECUTION_BACKLOG.md` is the only holy work-state file. Cleanup may retarget subordinate docs to it; never create a parallel backlog.

## MLB-Props Current-State Rules (Sep 2026)

- Treat `docs/EXECUTION_BACKLOG.md` + `AGENTS.md` + `.cursor/rules/execution-backlog.mdc` as the agent/work-plan source of truth.
- Treat `production/ops/kpi_policy.json` + `production/README.md` + `production/INDEX.md` as canonical **runtime** truth.
- Treat `docs/research/step11_discipline_registry_freeze.md` as the active freeze anchor.
- For historical step cleanup, consolidate closed `docs/research/step*.md` files into one summary doc before deleting originals.
- Keep freeze-lineage docs (`step11_*`, `step10_*`, and any currently referenced freeze companion) unless explicitly approved for removal.
- Preserve parity-lock and gate documentation (`--from-recommendations`, execution-vs-research split) in all cleanup edits.
- Live decision policy (4.5-over veto + soft probation) is documented in `docs/reference/reports/live_policy_promotion_2026-09-01.md`; further promotes stay gated in the backlog DEFERRED table.

## Allowed Automatic Changes

- Add or refine `.gitignore` entries for generated outputs.
- Normalize obvious path-pattern coverage in ignore rules.
- Remove clearly disposable cache files if removal is unambiguous and safe.
- Add brief README notes clarifying generated vs source-of-truth directories.
- Create a `hold` inventory document listing unresolved candidates and rationale.

## Require Explicit Approval First

- Deleting datasets, model outputs that may be source-of-truth, or notebooks.
- Removing scripts that might still be referenced by workflows.
- Renaming top-level directories or changing repository structure.
- Moving any file on the daily pipeline execution path.
- Any case-only rename on Windows (`Data` -> `data`) due git/cross-platform risk.

## Reorganization Protocol

When reorganizing files by family:

1. Propose target taxonomy first (current path -> target path -> risk -> update set).
2. Execute low-risk moves only after reference rewrites are prepared.
3. Keep compatibility wrappers or path updates for scripts/docs in the same pass.
4. Validate pipeline integrity with smoke checks before and after changes.
5. Update folder-level README/docs immediately after each approved move batch.

Never do a large all-at-once restructure.

## Documentation Update Protocol

For each approved cleanup/reorg batch:

- Update impacted folder README(s).
- Update canonical operational docs first:
  - `docs/EXECUTION_BACKLOG.md` (Session Snapshot PRESENT / docs hierarchy if work-state changed)
  - `production/INDEX.md`
  - `production/RUNBOOK.md`
  - `production/README.md`
  - `docs/reference/repo_canonical_map.md`
- Update dependent reference docs/diagrams/paper notes only where paths or claims changed.
- Prefer links to canonical docs over duplicating procedures.
- Prefer links to `docs/EXECUTION_BACKLOG.md` over duplicating “next steps” lists.

## Filename and Folder Standardization

- Prefer lowercase, hyphenated markdown names for new docs (for example `historical-step-findings-summary.md`).
- Do not perform case-only renames on Windows.
- If mixed naming exists, standardize via additive migration:
  1. create canonical target file,
  2. rewrite references,
  3. delete source only after verification.
- Keep top-level taxonomy stable (`docs/paper`, `docs/reference`, `docs/research`, `docs/archive`).

## Resume-Readiness Add-on

When cleanup touches project-facing docs, include a short "resume-ready facts"
extract in the final report:

- frozen model identifier(s),
- evaluation metrics used publicly,
- production controls shipped,
- measurable operational outcomes (ROI/CLV/risk where already documented).

Do not invent metrics; only use repository-backed values.

## Required Report

Return a final report with:

```markdown
## Cleanup Results
- change
- why safe

## Keep/Hold/Delete Ledger
- path | decision | evidence | risk | owner action

## Pipeline Validation
- checks run
- outcome

## Documentation Updates
- files updated
- reason

## Approval Queue
- blocked item
- risk
- recommendation
```

## Additional Resources

- Detailed project guardrails and smoke checks: [reference.md](reference.md)

## Output Format

Return results using:

```markdown
## Cleanup Results
- What was changed
- Why it was safe
- What was intentionally left untouched

## Follow-up Approval Items
- Candidate item
- Risk
- Recommended action
```
