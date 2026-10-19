# Adoption matrix — slices/tickets → owning skill (2026-10-16, Chat 3)

Maps every planned slice and backlog ticket to its owning skill, required
pre-action evidence, and outcome class. Sources:
[`maintenance_slice_specs_2026-10-16.md`](maintenance_slice_specs_2026-10-16.md),
[`cleanup_execution_plan_2026-10-16.md`](cleanup_execution_plan_2026-10-16.md)
(+ addenda), [`change_impact_matrix_2026-10-16.md`](change_impact_matrix_2026-10-16.md),
[`deletion_quarantine_ledger_2026-10-16.md`](deletion_quarantine_ledger_2026-10-16.md).

| Slice/ticket | Owning skill | Evidence required before action | Outcome class | Release gate |
|---|---|---|---|---|
| S-A CI test-collection (T14) | repo-ci-coverage-auditor | exact collected/excluded lists (done); PR #3 merged | **refactor** (CI step) | count closeout |
| S-B dependency declarations (T13) | repo-dependency-hygiene | pyproject-vs-import diff (done); sage verification | **refactor** (declarations) | owner approval |
| S-C dead-module disposition (T15) | repo-dead-code-auditor | proven-dead verdict (done: 5 modules); owner one-word ruling | **delete** (no) / **annotate** (yes) | owner ruling |
| S-D notebook archival (T17) | repo-artifact-lifecycle-auditor | per-notebook census (done); operational-owner confirmation | **archive** (moves + manifest) | operational owner |
| T16 INDEX/env completeness | repo-docs-canonicalizer | 62 undocumented entry points + 4 undocumented env vars (done) | **report → docs** | chat3 slice approval |
| T5 superseded-pointer pass | repo-docs-canonicalizer | dead-ref list (done); #8 verdict | **supersede** (pointers/banners) | #8 verdict + gate closure |
| T6 prereg draft/final pairs | repo-docs-canonicalizer | blob-identity proof (done) | **archive or annotate** | owner pick |
| T7 prune_artifacts canonicality | repo-dead-code-auditor + owner | dual-copy diff (done) | **consolidate/annotate** | owner ruling |
| T4 lockfile/cache-key | repo-dependency-hygiene | taxonomy + option comparison (done) | **refactor** | S-B merged; owner tool choice |
| T8 Issue #5 operator-flow fix | repo-artifact-lifecycle-auditor (notebook-chain) | issue validation plan (done) | **fix** (functional) | explicit authorization |
| T9 Issue #9 reliability pointer | repo-dead-code-auditor | dead-module proof (done) | **fix or delete** | folds into S-C |
| T10 action SHA-pinning | repo-ci-coverage-auditor | workflow inventory (done) | **refactor** (pinning) | owner approval |
| T11/T17 notebooks | repo-artifact-lifecycle-auditor | census + deep review (done) | **archive** | operational owner |
| T12 terminology standardization | repo-docs-canonicalizer | variants table (done) | **report → docs** | chat3 slice approval |
| T18 schedule reconciliation | repo-ci-coverage-auditor | 22-vs-10 schedule census (done) | **report → registry** | owner approval |
| Citation gates 1–4 (post-count-run) | repo-dead-code-auditor (bootstrap consolidation) / Chat 2 (reconciliations) | count run reconciled | **report/evidence** | count closeout |

Pattern: every ticket already has its pre-action evidence committed — the skills
formalize **how the next tickets get theirs**, so future cleanup stops relying on
heroic one-pass audits.
