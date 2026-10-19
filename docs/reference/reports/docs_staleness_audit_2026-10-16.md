# Documentation staleness audit — 2026-10-16 (Chat 3, report-first)

Evidence-based staleness findings at `origin/main` @ `1927c8c…`. Nothing edited;
each finding lists exact paths, evidence, and the bounded slice that would fix it.

## 1. Dead references (verified)

| Reference | Held by | Evidence | Fix slice |
|---|---|---|---|
| `results_gate_policy.ipynb` (deleted 2026-09-17-era) | `production/RUNBOOK.md`, `docs/diagrams/01-architecture.md`, `docs/diagrams/03-modeling-and-evaluation.md`, backlog, `run_daily_operator_flow.ps1` | basename absent from 809 tracked files; operator flow = Issue #5 | superseded-pointer pass (blocked on queue) |
| `Strikeouts.ipynb` | `src/Python/reliability.py` | Issue #9; basename absent | owner decides (Option A/B in issue) |
| `feature-understanding.ipynb` | `docs/CLEANUP_LOG.md` | historical log; benign | none (historical record) |

## 2. Unrooted-but-resolvable references (~14)

Bare notebook names in historical docs (`ballpark.ipynb`, `results_dashboard.ipynb`,
`train.ipynb`, …) resolve to `src/Notebooks/` or `production/notebooks/` but are
written without a stable path. Evidence: 2026-10-16 census `nb_callers`.
Disposition: low priority; fix opportunistically in touch-me-anyway edits, not a
dedicated pass. Exceptions worth a real path: `docs/reference/pipeline_registry.json`
→ `models/Strikeout-Model/train.ipynb`, and `research_assistant_instructions.md` →
`production/notebooks/results_dashboard.ipynb` (both currently bare names).

## 3. Duplicate draft/final packets (owner hold)

| Pair | Evidence | Disposition |
|---|---|---|
| `pa-k-baseline-prereg-draft.md` == `pa-k-baseline-prereg.md` | content-identical blobs | hold-owner: archive draft with pointer, or keep as lineage |
| `expanding-training-prereg-draft.md` == `expanding-training-prereg.md` | content-identical blobs | same |

## 4. Obsolete/ambiguous command references

| Item | Evidence | Disposition |
|---|---|---|
| `prune_artifacts.py` dual copies | `scripts/` (122 lines) referenced by canonical map §cleanup-targets + 5 other docs; `production/ops/` (220 lines, protected-folder-aware) unreferenced by docs | owner ruling: which is canonical; then one doc-line fix + possible relocation slice |
| `results_gate_policy` in `production/INDEX.md`? | verified NOT present (INDEX clean) | none |
| `⅛ Kelly` stale wording | already flagged in `docs/diagrams/00-index.md` lineage notes (self-aware) | none (handled by existing notes) |

## 5. Terminology inconsistencies (report-only; fix in a vocabulary slice if approved)

| Term variants observed | Where | Suggested canonical form |
|---|---|---|
| `equal-info` / `equal-information` / `matched-exposure` | PR #3 docs, backlog, reports | `equal-information` (freeze-file spelling) |
| `I3b` / `canonical I3b` / `I3b count model` | backlog, reports | `I3b` at first mention, then plain |
| `BF` / `TBF` / `batters faced` | `CONTEXT.md` defines both; usage drifts in reports | BF for the distribution lane, TBF for the frozen Ridge prediction (per CONTEXT.md) |
| `slate-date bootstrap` / `date-clustered bootstrap` / `game-date-clustered` | reports across eras | `paired slate-date bootstrap` for current harness results |
| `p̄` / `p_bar` / `p-bar` | pipeline + harness docs | `p_bar` (ASCII-safe consoles) |

## 6. Stale branch surface (read-only; no action without owner)

Unmerged remote branches (ahead of main): `research/market-eval-v2` (52, active
PR #3), `chat2/review-tooling` (3, PR #6), `research/paired-uncertainty-v2` (1,
PR #2), maintenance branches (this work + #8/#10 + closed #7's retained branch).
Merged branches still on remote: `agent/distribution-spec`, `agent/mlflow-mirror`,
`review/pa-remediation-2026-10-09`, `maintenance/ci-opt-20261016` — safe-delete
candidates, but branch deletion is owner action (PR #7's branch explicitly
retained for provenance).

## 7. Docs describing behavior different from the current repo (candidates)

| Doc | Divergence | Evidence |
|---|---|---|
| `CONTEXT.md` PA-overhaul section | 2026-09-29 snapshot retained; now banner-marked superseded-for-current-state (fixed on PR #4) | PR #4 diff |
| `docs/reference/opencode_handoff.md` | dated 2026-09-11 briefing; explicitly point-in-time by convention | header |
| `docs/reference/offseason_architecture_audit_2026-09-28.md` | pre-harness architecture narrative | dated by name; verify claims before citing |
| `README.md` on main | lacks current-state/results-index pointers until #4/#8/#10 land | known; resolves at integration |

None of section 7 is edited from this audit; the fixes ride the already-open PRs
or future approved slices.
