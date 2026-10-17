# Maintenance slice specifications — 2026-10-16 (Chat 3, prepared for execution AFTER the count-run repair/re-execution closes)

Four coordination-named conversions, specified to ready-to-execute precision.
**Nothing opened, nothing edited outside this branch.** Each spec becomes a
one-commit PR when its release condition fires.

## S-A — CI test-collection correction (T14)

**Release condition:** count-run repair/re-execution closed; PR #3 merged (its
suites join the excluded set).
**Exact change** (`.github/workflows/ci.yml`, one new step after the main suite):

```yaml
      - name: Run research/harness test suites (outside default testpaths)
        run: |
          python -m pytest \
            research/offseason_2026/p1_harness \
            research/offseason_2026/bf_workload_v1/tests \
            research/offseason_2026/prospective_logging \
            research/offseason_2026/market_eval/tests \
            -q -rs
```

- Explicit path list (NO broad glob, NO path filtering of the main suite, main
  suite step byte-unchanged).
- Strict failure (no `--continue-on-collection-errors`): fail loud; artifact-
  pinned tests inside these suites already skip with named reasons when lake
  inputs are absent, so ubuntu CI stays green without data.
- Path list grows only by deliberate edit (each addition = one reviewed line).
- Validation: the PR's own CI run exercises the new step; main-suite runtime
  unchanged; step runtime expected < 60s.
- Coordination note honored: Chat 1's repair keeps its runner test under the
  active `tests/` collection path — this slice covers the OTHER excluded suites.

## S-B — dependency declarations (T13 / D1)

**Release condition:** owner approval (one word).
**Exact change** (`pyproject.toml`):

```toml
[project.optional-dependencies]
research = [
  # existing entries unchanged, plus:
  "xgboost", "optuna", "catboost",
  "requests",
]
paper = ["pymupdf", "markdown"]
deploy = ["modal"]
```

- `requests` → research tier **pending owner call** (two of its four consumers
  are historical-odds pullers; if the daily chain never imports it, research is
  correct — the import scan shows all 4 consumers under
  `production/ops/market_research/`, so research-tier is the recommendation).
- `sage` — **verify before declaring**: single consumer
  (`models/Strikeout-Model/research/full_feature_importance_screen.py`);
  confirm the import statement is a real PyPI package and not legacy debris. If
  the script is retired instead, drop it from this slice and queue the file.
- `streamlit` already declared — no change (single importer, dashboard app).
- Validation: fresh-venv smoke install (`pip install ".[research,paper,deploy]"`)
  then `python -c` imports of the 8 modules; CI cache key unaffected until T4
  (lockfile) lands.

## S-C — dead-module ruling brief (T15)

**Release condition:** owner answers ONE question:

> Are `ballpark`, `batter_features`, `batter_rolling`, `identity`, `reliability`
> (src/Python) invoked by anything OUTSIDE the tracked tree (lake-archived
> runners, external schedulers)? Yes / No.

Evidence in hand (all static): zero imports (bare, dotted, `Python.*`), zero
dynamic-import targets (58 sites resolved), zero string references as modules,
zero CLI callers, zero test refs (except test-only `skill_stats.py`).
- **No** → S-C1 dead-code quarantine: `git rm` 5 modules + `skill_stats.py`
  (test-only) + `tests/test_skill_stats.py` + the 1 zero-ref orphan file, full
  reference list attached (dead-code audit), docs-truth fix to
  `CONTEXT.md`/`README.md` in the SAME commit.
- **Yes** → S-C2 docs-truth fix only: annotate the modules' status in
  `CONTEXT.md` (invoked externally; not part of the in-tree import graph) and
  close the finding. Either way a one-commit, one-lane PR.

## S-D — `src/Notebooks/` archival (T17)

**Release condition:** operational-owner confirmation (these are lineage, not
operational).
**Exact change:** `git mv src/Notebooks docs/archive/legacy-notebooks/` (10
notebooks + subdirs, history preserved) + new
`docs/archive/legacy-notebooks/README.md` manifest (each file: purpose, era
2026-07/08, superseding surface = `src/Python/pipeline/*` + `src/Python/*.py`)
+ pointer updates in exactly 2 living docs that reference them:
`docs/reference/dev-notes.md` (`pipeline/training.ipynb`) and
`docs/CLEANUP_LOG.md` (historical log — append-only note, no history rewrite).
`pipeline/training.ipynb` has 3 doc callers and `pipeline/rolling.ipynb` has 2 —
all covered by the same pointer edits. Validation: link check passes; no
production path references `src/Notebooks` (verified in caller evidence).

## Sequencing

S-A and S-B are independent of each other and of S-C/S-D; both wait for the
count-run closeout per coordination. S-C waits only for the owner's one-word
answer (could run immediately if the owner answers). S-D waits for the
operational owner. Each = one commit, one PR, exact-head CI, Chat 2 verdict,
post-merge main-SHA receipt — per the standing contract.
