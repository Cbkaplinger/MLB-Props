# Cleanup execution plan — 2026-10-16 (Chat 3, report-first)

Ranked execution plan for the 12 backlog tickets
([`repo_cleanup_backlog_2026-10-16.md`](repo_cleanup_backlog_2026-10-16.md)),
scored on risk, expected benefit, path family, test burden, dependencies, and
the **earliest safe merge slot** given the serialized queue. Base: branch
`8bb86e6…` over `origin/main` @ `1927c8c…`. No PR opened; nothing executed.

## Merge-slot model (current)

Serialized main; one active PR per path family; up to three merge-ready PRs +
one Chat 3 docs/report PR coexisting (revised policy). Live queue:

```text
slot 0 (now):      #3 research lane — Chat 2 review -> READY -> ONE count run -> reconciliation
slot 1:            #2 (rebase at slot, CI, merge)
slot 2:            #8 (results index; Chat 2 verdict)
slot 3:            #10 OR role-card PR (governance; ONE vehicle chosen)
then:              free slots for maintenance slices in the ranked order below
```

Path families and current occupancy: `.github/workflows` FREE; `docs/reference`
root (#10 pending) OCCUPIED until slot 3; `research/*` OCCUPIED by #3 until
merge; `production/*` docs FREE (but content-blocked); `src/Python` FREE
(content-blocked); `docs/reference/reports` FREE (this branch, PR-less).

## Ranked plan

| Rank | Ticket | Path family | Risk | Expected benefit | Test burden | Depends on | Earliest safe slot |
|---|---|---|---|---|---|---|---|
| 1 | **T3** CI `permissions: contents: read` + artifact `retention-days` | `.github/workflows` (FREE) | Low | High (least-privilege token; bounded artifact retention) | Workflow self-test (PR's own CI) | owner approval (requested) | **Next free maintenance slot** — family free now |
| 2 | **T5** superseded-pointer pass (gate-policy refs → Issue #5/bettable cohort; SUPERSEDED banners) | `production/RUNBOOK.md`, `docs/diagrams/01,03` (FREE) | Low | High (kills the dead-reference class; aligns docs with reality) | link check + `check_notebook_artifacts.py` | #8 verdict; B1 gate already cleared | After #8 merge (slot 2) |
| 3 | **T1** role cards + template-pack adoption + AGENTS.md pointer | `docs/agent_roles/*` (new), `AGENTS.md`, `pr_workflow.md` (OCCUPIED by #10) | Low | High (durable operating contract; ends role drift) | docs-only CI | #8 verdict; **choose #10-refresh OR role-card vehicle** | Slot 3 (as the chosen governance vehicle) |
| 4 | **T4** CI cache-key: hash installed extras | `.github/workflows` | Medium | Medium-High (kills silent version drift) | cache behavior over 2+ runs | T3 merged | After T3 (same family, serialized) |
| 5 | **T2** base refreshes at merge slots | none new | Low | Medium (keeps merge-ready set honest) | exact-head CI rerun | each merge moment | continuous, at slots |
| 6 | **T10** SHA-pin actions (or document accepted risk) | `.github/workflows` | Low | Medium (supply-chain posture) | workflow self-test | T3/T4 (same family) | After T4 |
| 7 | **T6** archive 2 prereg drafts with pointers | `research/offseason_2026/*-draft.md` (OCCUPIED by #3) | Low-Med | Medium (removes duplicate-evidence ambiguity) | blob-identity already proven | owner approval + #3 merged | After #3 merge |
| 8 | **T12** terminology standardization (vocabulary doc first, then touched-in-passing fixes) | docs-wide (touch-in-passing only) | Low | Medium (stops cross-era misreadings) | n/a | T1 (governance home for the vocab doc) | After slot 3 |
| 9 | **T7** `prune_artifacts.py` canonicality fix | 6 doc lines (+1 file if owner says so) | Medium | Medium (removes a real wrong-command risk) | command runnable check | **owner ruling** (pending) | Any slot after ruling |
| 10 | **T9** `reliability.py` dead pointer (Issue #9) | `src/Python` (FREE) | Medium | Medium (cleans active-code staleness) | `git grep` zero-match + suite | owner Option A/B (pending) | Any slot after decision |
| 11 | **T8** Issue #5 operator-flow fix (Option A) | `production/ops/run_daily_operator_flow.ps1` | Medium | Medium (functional defect; conditional path) | validation plan in issue | explicit functional-fix authorization | Post-gate; owner order |
| 12 | **T11** notebook archival (caller-validated) | `src/Notebooks/*`, `models/**` (lineage) | Medium-High | Medium (space/clarity; riskiest surface) | per-file caller evidence + retention check | census reviewed (this branch) + owner | Last |

## Where the four citation gates slot in

The coordination-designated citation gates are **post-count-run** slices and
share the `research` path family with #3 — they queue after the count run's
reconciliation, in this order: (1) count-eval-v1 independent reconciliation,
(2) calibration decile recomputation, (3) LGBM equal-info CAL-lane review,
(4) canonical bootstrap consolidation into a durable shared location (this one
also touches `src/Python`-adjacent research code → its own approved PR).

## Scheduling rules applied

- Same-family tickets are serialized (CI: T3→T4→T10; governance: T1; research: T6 + gates).
- No ticket opens while its blocking verdict/approval is outstanding.
- Chat 3 maintains at most ONE open maintenance PR; this plan executes one
  ranked ticket at a time as slots free.
- Nothing here modifies the count-run execution surface; the scientific lane
  keeps absolute priority on slots 0–2.

## Disposition

Report-only slice on `maintenance/quality-baseline-20261016` (no PR). Re-rank
trigger: any verdict, merge, or owner ruling changes the dependency column.

## Addendum — 2026-10-16 deep-audit discoveries (re-ranked inputs)

From the seven audit reports committed this pass
(`python_dead_code`, `test_quality`, `notebook_artifact_census`,
`dependency_reproducibility`, `entrypoint_ops`, `docs_consolidation_design`,
`security_config`):

- **NEW T13 (high value):** declare the **8 undeclared imports** (`requests`,
  `xgboost`, `optuna`, `catboost`, `modal`, `pymupdf`, `markdown`, `sage`) —
  fresh installs cannot import tracked code today. One-commit slice, low risk.
  Ranks alongside T3.
- **NEW T14 (medium):** research/harness suites under `research/offseason_2026/`
  are **outside default pytest collection** (`testpaths = ["tests"]`) — CI green
  does not exercise them. Proposal: explicit research-lane pytest invocation in
  CI (no path filtering of the main suite). Owner approval; schedule after T3.
- **RANK UP — T5:** superseded-pointer pass now also carries the operator-chain
  smoke-existence test proposal (would have caught Issue #5).
- **NEW T15 (owner validation):** 5 documented-canonical `src/Python` modules
  (`ballpark`, `batter_features`, `batter_rolling`, `identity`, `reliability`)
  are statically dead (zero importers/tests/callers) — owner must confirm
  whether invocation exists outside the tracked tree before any disposition.
  Also 1 true zero-reference orphan file awaiting the same ruling.
- **CORRECTED:** `bullpen.py` is proven active (prior census wrong); census
  conclusions superseded by `python_dead_code_audit_2026-10-16.md`.
- Security posture: no committed credentials; remaining items are the already-
  ticketed T3/T10 plus 3 informational `Invoke-Expression` sites.

## Addendum 2 — 2026-10-16 (second audit wave; tickets T13-T18)

From `dynamic_import_resolution`, `ci_coverage_map`, `entrypoint_inventory`,
`notebook_deep_review`, `artifact_lifecycle_map`, `dependency_closure`,
`config_provenance`:

- **T13 CONFIRMED (upgraded):** 8 undeclared imports; full taxonomy + homes in
  `dependency_closure_2026-10-16.md`. Declarations first (D1), lockfile second.
- **T14 NARROWED:** exactly 5 test files excluded from default CI on main
  (`ci_coverage_map_2026-10-16.md`); grows materially when PR #3 lands. Minimal
  non-weakening remedy proposed (research-lane step + required status).
- **NEW T15 FINAL:** the 5 canonical modules are now PROVEN dead in the tracked
  tree (dynamic-loading refuted; `ballpark`/`batter_features` have zero
  references of any kind). Blocking question is now purely owner knowledge:
  out-of-tree invocation yes/no. Same ruling covers the 1 zero-ref orphan and
  test-only `skill_stats.py`.
- **NEW T16:** INDEX-completeness pass — 62 undocumented entry points + 4
  undocumented env vars + env-var reference table (ops + config audits).
- **NEW T17:** `src/Notebooks/` archive-with-manifest (10 files, 2026-07-23
  vintage, output-less, lineage-only) — supersedes the vaguer T11; two docs
  (`dev-notes.md`, `CLEANUP_LOG.md`) need pointer updates in the same slice.
- **NEW T18:** registry-vs-reality schedule reconciliation (22 scheduled
  entry points vs pipeline registry's 10 schedules; registry is design-only).
- **T11 superseded by T17.** All other ranks unchanged; T3 still first at the
  next free CI-family slot after the count run finalizes.
