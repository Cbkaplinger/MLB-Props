# Change-impact matrix — 2026-10-16 (Chat 3, report-first)

Execution planning for slices S-A..S-D
([`maintenance_slice_specs_2026-10-16.md`](maintenance_slice_specs_2026-10-16.md))
and tickets T13–T18 ([`cleanup_execution_plan_2026-10-16.md`](cleanup_execution_plan_2026-10-16.md)
addenda). Base `origin/main` @ `1927c8c…`; Chat 3 branch @ `1778cd9…` (reports).
**Nothing executed.** Merge slots assume the serialized queue (#3 → #2 → #8 →
#10/role-cards) drains first; "free" = no open PR owns the path family.

| ID | Changed paths | PR dependencies | Active-worktree overlap | Reviewer | CI/test command | Rollback | Earliest safe slot |
|---|---|---|---|---|---|---|---|
| **S-A** T14 CI collection | `.github/workflows/ci.yml` (+1 step) | after #3 merge (suite list includes its test dirs) | none (family free) | Chat 2 | PR's own CI (new step self-tests); main suite byte-unchanged | revert commit | slot 4 (post-#2/#3/#8, with #10-or-role-cards resolved) |
| **S-B** T13 dependency declarations | `pyproject.toml` (+6 lines, 2 new extras) | none | none (family free) | Chat 2 + owner (tier calls) | fresh-venv smoke install + 8 module imports (local); CI unaffected (cache key unchanged until T4) | revert commit | **any time after owner approval** (family free) |
| **S-C** T15 dead-module disposition | `src/Python/{ballpark,batter_features,batter_rolling,identity,reliability}.py`, `src/Python/skill_stats.py`, `tests/test_skill_stats.py`, `models/Strikeout-Model/research/print_step9_inventory.py`, `CONTEXT.md`, `README.md` | none | none (families free) | Chat 2 + **owner one-word ruling** | full pytest (imports of deleted modules must already be zero — verified); `git grep` zero-match check in PR body | `git revert` (deletes) or edits (annotations) | **any time after owner ruling** |
| **S-D** T17 notebook archival | `src/Notebooks/**` → `docs/archive/legacy-notebooks/**` (10 files), new archive README, `docs/reference/dev-notes.md`, `docs/CLEANUP_LOG.md` | none | none (families free) | Chat 2 + operational owner | link check; `check_notebook_artifacts.py`; grep zero `src/Notebooks` in production paths | `git revert` (moves preserve history) | after operational-owner confirmation |
| **T16** INDEX/env completeness | `production/INDEX.md`, `production/README.md`, `production/RUNBOOK.md` (additive sections) | none | none (families free; #5/#9 fix slices are separate) | Chat 2 + ops owner | link check; documented commands re-run | revert | free — pairs naturally with T8/T9 fixes |
| **T18** schedule reconciliation | `docs/reference/pipeline_registry.json` + canonical map section | none | none | Chat 2 + owner | registry JSON validity check | revert | low urgency; any slot |
| T4 lockfile/cache-key | `pyproject.toml` + lockfile + `ci.yml` cache key | after S-B | `.github` family occupied by S-A until merged | Chat 2 + owner (tool choice) | 2+ CI runs observing cache behavior | revert | after S-A merges |
| T8 Issue #5 fix | `production/ops/run_daily_operator_flow.ps1` | explicit functional authorization | production family free | Chat 2 + owner | validation plan in issue (dry chain, artifacts check) | revert | after owner order (post-gate) |
| T9 Issue #9 fix | `src/Python/reliability.py` | owner Option A/B — folds into S-C if the ruling is "dead" | src family free | Chat 2 | `git grep` zero-match + suite | revert | folds into S-C |
| Citation gates 1–4 (post-count-run) | research-adjacent reports + possible shared bootstrap consolidation (`src`-adjacent) | count run reconciled | research family after #3 merges | Chat 2 | per-gate recomputation | n/a (evidence work) | after count closeout, in stated order |

Cross-cutting: every row = one commit, one PR, exact-head CI, Chat 2 verdict,
post-merge main-SHA receipt; no two slices share a path family concurrently;
no slice touches research registration, frozen packets, or another chat's
worktree.
