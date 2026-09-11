# Repo quality hold inventory — 2026-09-11

Point-in-time hold list from `/repo-quality-passthrough`. **Not a work queue.**
Live plan: [`docs/EXECUTION_BACKLOG.md`](../../EXECUTION_BACKLOG.md).
Numbers: [`docs/reference/golden_metrics.md`](../golden_metrics.md).

| Path / topic | Decision | Evidence | Risk | Owner action |
| --- | --- | --- | --- | --- |
| `tmp_nb_figs/` | **delete** (local) + ignore | 11 PNGs, 769 KB, extracted from notebooks this week; no code refs | None | Ignored + local files removed this pass |
| Untracked `production/ops/market_research/*.py` (stacker, harness, closeout, …) | **keep** | Live pack #113 + research probes; tests exist | Losing measurement tools | Commit when you publish; do not delete |
| Untracked `docs/reference/{opencode_handoff,golden_metrics,cursor_deep_dive_brief}.md` | **keep** | Agent contract + canonical numbers | Stale if Snapshot diverges | Commit with next publish; Snapshot wins |
| `artifacts/**` (local) | **keep** (local) / ignore | Entire tree gitignored; odds_log + projection_log + models | Deleting loses provenance | Leave local |
| Case aliases `Data/` / `Artifacts/` / `Models/` | **hold** | Windows FS collapses case; both patterns in `.gitignore` | Case-only rename unsafe | No rename |
| Closed `docs/research/step*.md` (pre-step11) | **hold** | Freeze lineage | Losing audit trail | Consolidate only after explicit approve |
| Item 13 MLflow | **hold / deferred** | Backlog DEFERRED | Mid-ops distraction | Do not install |
| Dashboard `_dedupe_frame` vs `dedupe_ledger_props` | **hold** | Dashboard parked until #113 green | Display double-count if UI ships stale | Unpark only after backend pack |
| Manuscript HTML/PDF + resume HTML/PDF | **keep** | Portfolio; `.md` is source | Stale render after #111 paper rewrite | Regen `make_figures` / PDF when you say go |
| Git history bloat (`data/Savant-Data/` untracked, old blobs remain) | **hold** | filter-repo needs sign-off | History rewrite | Owner-only; not this pass |
| `cursor_deep_dive_brief.md` vs `opencode_handoff.md` | **keep** both | Brief is a pointer, not a second queue | Drift if brief restates a plan | Keep brief short (already is) |

## This pass — automatic (no approval needed)

- `.gitignore`: `tmp_nb_figs/`.
- Deleted local `tmp_nb_figs/*.png`.
- SOP nested-hole “next build” line now points at the backlog.
- `docs/reference/repo_canonical_map.md` lists handoff + golden metrics.
- No production code, notebooks, or artifact trees deleted.
