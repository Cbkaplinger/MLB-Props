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
