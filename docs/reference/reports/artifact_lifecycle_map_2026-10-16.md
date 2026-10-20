# Artifact lifecycle map — 2026-10-16 (Chat 3, report-first)

Definitive lifecycle classification for every tracked artifact class at
`origin/main` @ `1927c8c…` (809 files, 27.4 MB). Supersedes the preliminary
groups in [`notebook_artifact_census_2026-10-16.md`](notebook_artifact_census_2026-10-16.md).
Confidence: HIGH. **No artifact moved, deleted, or untracked by this map.**

## Lifecycle states

| State | Definition | Tracked members |
|---|---|---|
| canonical source | hand-maintained; the thing itself | pipeline/ops code, policy JSONs, specs, contracts, living docs (non-report) |
| immutable evidence | generated once, then frozen; never regenerated | `models/**` boosters/sidecars (79), `research/**/experiments/**` cards+metrics+manifests, prereg docs, dataset parquets + `pa_dataset_manifest.json`, dated reports |
| reproducible generated output | regenerable from committed source + inputs | paper figures/PDF/HTML (`make_figures.py`), rendered notebooks' outputs, generated results index (PR #8, CI-staleness-guarded) |
| lake-only (NOT in Git) | full outputs/forecasts/bootstrap arrays | `bf-lane-v1/*`, market-eval run dirs, MLB-Props-Research packets — referenced in Git only via receipts + hashes (verified working: B1 closeout pattern) |
| cache/temp | disposable | correctly absent from tracking (`.venv`, `data/`, `artifacts/`, `.hypothesis`, `.pytest_cache` ignored; 1 intentional negation README) |
| duplicate | content-identical sibling | 7 groups (register): 2 intentional mirrors, 2 draft==final (owner hold), 2 intentional rerun copies, 1 within-experiment oddity (owner hold) |
| deletion candidate | zero references after full validation | **1 orphan file** (dead-code audit) — owner gate |

## Retention and manifest rules (verified as already operating)

1. **Git holds identity, lake holds bulk.** Every experiment's Git footprint is
   card + metrics + manifest + hashes; predictions/PMFs/bootstrap draws live in
   the lake at recorded paths. No tracked artifact duplicates lake bulk.
2. **Manifests accompany evidence bundles**: `pa_dataset_manifest.json`,
   `hashes.json` per experiment, `run_manifest.json` (B1 closeout pattern).
3. **Boosters stay in Git** (small, hash-pinned, promotion-critical) — correct
   exception to "generated files go to lake".
4. **Figures/paper stay in Git** (publication provenance; regenerable but
   reviewer-visible) — correct.
5. **Retention**: no time-based pruning of tracked evidence; the only pruning
   utility (`prune_artifacts.py`) targets dated runtime artifacts under
   `artifacts/` (ignored), dry-run by default — its canonical-copy question
   remains backlog T7.

## Deletion candidates (complete list, owner-gated)

1. The single zero-reference orphan `.py` (identity in `deep_audit_final.json`).
2. Five proven-dead canonical modules + `skill_stats.py` (test-only) — pending
   the owner's out-of-tree invocation answer.
3. `src/Notebooks/*` archival (move, not delete) after pointer updates.
4. Draft==final prereg duplicates (archive with pointer).

Nothing else in the tracked tree qualifies: every other file has live callers,
inbound references, or evidence status.
