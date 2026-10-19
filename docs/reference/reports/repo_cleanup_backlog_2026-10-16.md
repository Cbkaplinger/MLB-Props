# Repository cleanup backlog — 2026-10-16 (Chat 3, report-first)

Narrow, sequenced tickets. **Nothing is deleted, renamed, or consolidated from
this backlog alone** — each ticket becomes its own approved slice with one PR.
Sequenced to minimize conflict with the active merge queue (#2 → #3 → #8 → #10).

| # | Ticket | Exact paths | Risk | Tests/verification | Depends on | Owner gate |
|---|---|---|---|---|---|---|
| T1 | Role cards `docs/agent_roles/` (4 files) + AGENTS.md pointer + adopt template pack into `pr_workflow.md` | `docs/agent_roles/*`, `AGENTS.md`, `docs/reference/pr_workflow.md` | Low | links; docs-only CI | #8 verdict; not concurrent with #10 refresh | owner |
| T2 | PR base refreshes at merge slots (merge main into #2/#8/#10) | none new | Low | exact-head CI rerun | merge slot | integration owner |
| T3 | CI hardening C1: `permissions: contents: read` + explicit artifact `retention-days` | `.github/workflows/ci.yml` | Low | workflow self-test run | owner approval | owner |
| T4 | CI cache-key C2: hash installed extras (requirements-style list or lockfile) | `.github/workflows/ci.yml`, possibly new lockfile | Medium | cache behavior observed over 2+ runs | T3 landed | owner |
| T5 | Superseded-pointer pass: RUNBOOK + diagrams 01/03 gate-policy refs → Issue #5/bettable cohort; SUPERSEDED banners per register | `production/RUNBOOK.md`, `docs/diagrams/01,03`, flagged docs | Low | link check; `check_notebook_artifacts.py` | #8 verdict + B1 gate closure | owner |
| T6 | Prereg draft/final pairs: archive `*-draft.md` with pointer (2 files) | `research/offseason_2026/pa-k-baseline-prereg-draft.md`, `expanding-training-prereg-draft.md` | Low-Med (evidence) | blob-identity already proven | owner approval | owner |
| T7 | `prune_artifacts.py` canonicality: owner ruling → doc-line fix (canonical map + INDEX/README/RUNBOOK mentions) | 6 doc lines + possibly 1 file move | Medium | command still runnable | owner ruling | owner |
| T8 | Issue #5 fix: remove `$IncludeGatePolicy` dead step (option A) | `production/ops/run_daily_operator_flow.ps1` | Medium (functional) | validation plan in issue | explicit functional-fix authorization | Chat 2/owner |
| T9 | Issue #9 fix: `reliability.py` dead notebook pointer | `src/Python/reliability.py` | Medium (src path) | `git grep` zero-match + suite | owner Option A/B | Chat 1/owner |
| T10 | Action pinning C3: SHA-pin 3 actions or document accepted risk | `.github/workflows/ci.yml` | Low | workflow self-test | owner approval | owner |
| T11 | Notebook census slice: caller-validate `src/Notebooks/*` + `models/**/research/*.ipynb`; archival proposal only | report first | Medium | caller evidence attached | T-census reviewed | owner |
| T12 | Terminology standardization (`equal-information`, `paired slate-date bootstrap`, `p_bar`, BF/TBF) | report-first vocabulary doc, then touched-in-passing fixes | Low | n/a | T1 landed | chat3 |

Order rationale: T1 is the queued governance vehicle; T3/T4 are the approved CI
slices; T5-T7 need verdicts/approvals already in flight; T8-T10 are
functional/security with existing issue paper-trails; T11/T12 are last because
they touch the widest surfaces.

Explicitly NOT in the backlog (blocked by standing rules): any edit to
`docs/EXECUTION_BACKLOG.md`, frozen research packets, experiment outputs,
another chat's worktree, or bulk "update all docs" passes.
