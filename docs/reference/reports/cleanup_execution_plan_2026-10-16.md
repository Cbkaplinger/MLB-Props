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

---

# Repository sweep 2026-10-20 — coverage record + ordered plan (Chat 3, integration/maintenance owner)

Baseline: `origin/main` @ `4e764ab` (post #6). This section is the sweep
record required by the owner's deep-clean assignment; it extends this plan
document (no new audit-packet collection). Machine-readable inventory:
session artifact; compact figures below are the durable record.

## Coverage (982 tracked files, all classified)

| kind | count | kind | count |
|---|---|---|---|
| doc (md/txt) | 305 | config (yaml/toml/json) | 101 |
| production-code | 153 | test | 96 |
| research-code | 92 | model-code | 70 |
| source (src/) | 42 | other-text | 30 |
| script | 24 | notebook | 22 |
| csv | 11 | binary-figure | 10 |
| binary-data | 10 | other | 14 |
| binary-pdf | 2 | | |

Top-level spread: research 287, production 191, docs 185, tests 97, models 79,
src 54, dotfiles 47, scripts 28, playground 4, analysis 2, data 2, report 1.
Key surfaces read in full this pass: root README, docs/README, canonical map
(pointer scan), ci.yml (2 jobs), AGENTS_ROLES operating rules, cleanup plan
(this doc), diagrams index pointers. Long-tail reads continue per batch.

## Findings (confirmed vs merely unreferenced)

1. **`scripts/prune_artifacts.py` == `production/ops/prune_artifacts.py`
   content-identical (CRLF/LF only).** Genuine duplicate; entry-point
   deletion needs owner nod + living-pointer update (canonical map cites the
   scripts path). Batch 2.
2. **`report/` top-level dir holds ONE file**
   (`recency_batch_results_table.md`), referenced by the backlog (Chat 1
   sole-writer) + the recency-batch card. Move to
   `docs/reference/reports/` requires a coordinated backlog pointer edit.
   Batch 2 with Chat 1 coordination.
3. **Two `odds_board.py`** (`production/odds/` 8.9KB — docs-canonical,
   protected; `src/Python/` — imported by `test_safety_invariants`). Both
   protected paths; relationship needs consumer analysis before any
   proposal. Separate substantive-refactor track, NOT batch work.
4. **`docs/reference/` = 121 files**, many dated 2026-10-16 census/sweep
   reports now partially superseded by merged work (#18, #4, #16, #21, #22,
   #6). Superseded statements must be labeled in living docs; the dated
   reports themselves stay as evidence (historical layer, already the
   established convention).
5. **Root layout is functional** (17 top-level entries, all load-bearing or
   referenced); the UI clutter is directory-internal (docs/reference,
   research), not root-level loose files. Root README is current and
   correctly linked (current_state doc landed via #4).
6. **CI/CD:** 2 jobs mapped (test-and-validate: checkout, pip install
   `.[dev]`+scipy/joblib/sklearn/lightgbm/statsmodels, compileall production,
   full pytest with junitxml upload; tracking: mlflow install, complete
   tracking module, zero-skip guard). Redundancy: none found; gap: tracking
   job runs on every PR (~9-10 min) — change-category gating (docs-only
   paths skip tracking) is a candidate optimization that does NOT weaken
   mandatory coverage (the module still runs on every code-path change).
   Batch 3, CI-only, no deployment/secret changes.
7. **Notebooks:** 22 tracked; results_dashboard.ipynb (1.5MB) and
   results_pnl_clv.ipynb (0.9MB) carry executed outputs — operator surfaces
   per prior rulings (keep; artifact-census 2026-10-16 T17 covers the
   src/Notebooks archive separately).
8. **Committed experiment data** (pa_table 4.8MB, prediction parquets ~6.5MB
   total) are frozen-registration evidence — path-sensitive, untouched.

## Ordered batches (one cleanup PR active at a time; Chat 2 exact-head review)

- **Batch 1 (this PR, docs-only):** this sweep record + plan. No moves, no
  deletions. Establishes the plan-of-record in the canonical document.
- **Batch 2 (after Chat 2 verdict on batch 1):** (a) delete
  `scripts/prune_artifacts.py` (content-identical duplicate) + update the
  canonical-map pointer to the production/ops path; (b) move
  `report/recency_batch_results_table.md` ->
  `docs/reference/reports/` with card pointer update + Chat 1 backlog
  coordination (sole-writer applies the backlog line on their side);
  (c) living-doc supersession labels for the 10-16 census claims that later
  merges overtook. Deletion + move = entry-point/path changes — owner sees
  this plan before batch 2 executes.
- **Batch 3:** CI change-category gating for the tracking job (docs-only
  diffs skip tracking; all code paths keep it) + any coverage-gap fixes;
  evidence = before/after job timings.
- **Batch 4:** stale-doc sweep results from the long-tail read (docs dated
  pre-2026-10 with current-state claims), duplicate-explanation merges,
  broken-link repairs (link checker run recorded).
- **Separate track (not batch):** odds_board.py relationship proposal;
  src/Notebooks archive (existing T17).
- **Preservation invariants:** main-active unique commits + the historical
  `run_bf_ab_score.py` v1 preserved before any removal (owner already holds
  the classification packet); no untracked/ignored/local-only deletions
  without owner disposition; frozen/path-sensitive files (registrations,
  model artifacts, production entry points) untouched without consumer +
  registration checks.

## Exhaustive path-level inventory (982 files; reconciles the PR-body count)

Category semantics note: the PR body headline list omitted three rows that the
classification table above carries (other-text = 30, csv = 11, and 3 of the
36 non-figure binaries: model.pkl/joblib and .db), which produced the 938 vs
982 discrepancy. The complete 15-kind table sums to 982. Per-path listing:
one line per tracked file, kind-coded (D doc, C config, P production-code,
T test, R research-code, M model-code, S source, O other-text, X script,
N notebook, V csv, F figure, B binary-data, K model-binary, Z pdf, ? other).

### (root) AGENTS.md
- [D] AGENTS.md

### (root) CONTEXT.md
- [D] CONTEXT.md

### (root) README.md
- [D] README.md

### (root) activate.ps1
- [O] activate.ps1

### analysis/ (2)
- [D] analysis/model_results/README.md
- [N] analysis/model_results/model_results_story.ipynb

### data/ (2)
- [D] data/Pitcher-Starts-2023-2025-Data/README.md
- [D] data/README.md

### docs/ (185)
- [D] docs/AGENTS_ROLES.md
- [D] docs/CLEANUP_LOG.md
- [D] docs/EXECUTION_BACKLOG.md
- [D] docs/PROJECT_STATE.md
- [D] docs/README.md
- [D] docs/adr/PROPOSED-mlflow-research-mirror.md
- [D] docs/adr/TEMPLATE.md
- [D] docs/agent/skills-catalog.md
- [D] docs/agent/skills-evaluations.md
- [D] docs/agent/skills-provenance.md
- [D] docs/archive/README.md
- [D] docs/archive/leaky-baseline-2026-07-23/GIT_STATE.txt
- [D] docs/archive/leaky-baseline-2026-07-23/README.md
- [C] docs/archive/leaky-baseline-2026-07-23/mean.json
- [C] docs/archive/leaky-baseline-2026-07-23/ridge.json
- [D] docs/archive/pre-pipeline-v6/README.md
- [V] docs/archive/pre-pipeline-v6/shap_table_v6_lgb.csv
- [V] docs/archive/pre-pipeline-v6/test_predictions_v6_lgb.csv
- [D] docs/diagrams/00-index.md
- [D] docs/diagrams/01-architecture.md
- [D] docs/diagrams/02-leakage-and-risks.md
- [D] docs/diagrams/03-modeling-and-evaluation.md
- [D] docs/diagrams/04-roadmap.md
- [D] docs/diagrams/05-live-prediction-flow.md
- [D] docs/diagrams/06-count-eval-harness-2026-10-16.md
- [D] docs/diagrams/README.md
- [D] docs/paper/README.md
- [F] docs/paper/figures/fig10_monthly.png
- [F] docs/paper/figures/fig1_pipeline.png
- [F] docs/paper/figures/fig2_ablation.png
- [F] docs/paper/figures/fig3_overunder.png
- [F] docs/paper/figures/fig4_juiced_roi.png
- [F] docs/paper/figures/fig5_edge_band.png
- [F] docs/paper/figures/fig6_white.png
- [F] docs/paper/figures/fig7_policy_flow.png
- [F] docs/paper/figures/fig8_reliability.png
- [O] docs/paper/make_figures.py
- [O] docs/paper/manuscript.html
- [D] docs/paper/manuscript.md
- [Z] docs/paper/manuscript.pdf
- [O] docs/paper/render_pdf.py
- [O] docs/paper/render_resume_summary.py
- [O] docs/paper/resume-summary.html
- [D] docs/paper/resume-summary.md
- [Z] docs/paper/resume-summary.pdf
- [O] docs/paper/validate_pdf.py
- [D] docs/reference/PROPOSED_COMMITS.md
- [D] docs/reference/README.md
- [D] docs/reference/agentic_stack_final_plan_updated.md
- [D] docs/reference/beat_the_books_program.md
- [D] docs/reference/champion_challenger_protocol.md
- [D] docs/reference/clv_backfill_plan.md
- [D] docs/reference/current_state_2026-10-16.md
- [D] docs/reference/cursor_deep_dive_brief.md
- [D] docs/reference/daily_kpi_protocol.md
- [D] docs/reference/dashboard_information_architecture.md
- [D] docs/reference/dev-notes.md
- [D] docs/reference/evaluation-framework-external-2026-10-06.md
- [D] docs/reference/exit_anomaly_protocol.md
- [D] docs/reference/experiment_sop.md
- [D] docs/reference/golden_metrics.md
- [D] docs/reference/governance_metric_stack.md
- [D] docs/reference/lineup_train_serve.md
- [D] docs/reference/live_assembly_plan.md
- [D] docs/reference/market_clv_gates.md
- [D] docs/reference/measurement_operations.md
- [D] docs/reference/mlb-strikeout-forecasting-roadmap.md
- [D] docs/reference/model-card.md
- [D] docs/reference/oddsapi_replay_architecture.md
- [D] docs/reference/offseason_2026_choice_log.md
- [D] docs/reference/offseason_2026_source_register.md
- [D] docs/reference/offseason_architecture_audit_2026-09-28.md
- [D] docs/reference/opencode_handoff.md
- [D] docs/reference/pa_feature_lineage_2026-09-30.md
- [D] docs/reference/pa_split_provenance_correction_2026-09-30.md
- [C] docs/reference/pipeline_registry.json
- [D] docs/reference/pitcher_outs_expansion_plan.md
- [D] docs/reference/post_freeze_holdout.md
- [D] docs/reference/pr_workflow.md
- [D] docs/reference/repo_canonical_map.md
- [D] docs/reference/repo_hygiene_check.md
- [D] docs/reference/repo_waste_sweep_checklist.md
- [D] docs/reference/reports/README.md
- [D] docs/reference/reports/RECOUNT_SCORECARD_2026-10-15.md
- [D] docs/reference/reports/artifact_lifecycle_map_2026-10-16.md
- [D] docs/reference/reports/bf-closure-record-2026-10-13.md
- [D] docs/reference/reports/calibration_sharpness_note_2026-10-15.md
- [V] docs/reference/reports/canonical_document_register_2026-10-16.csv
- [D] docs/reference/reports/canonical_document_register_2026-10-16.md
- [D] docs/reference/reports/change_impact_matrix_2026-10-16.md
- [D] docs/reference/reports/chat3_final_handoff_2026-10-19.md
- [D] docs/reference/reports/ci_coverage_map_2026-10-16.md
- [D] docs/reference/reports/cleanup_constitution_2026-10-16.md
- [D] docs/reference/reports/cleanup_execution_plan_2026-10-16.md
- [D] docs/reference/reports/cleanup_skill_taxonomy_2026-10-16.md
- [D] docs/reference/reports/cloud_hosting_2026-09-14.md
- [D] docs/reference/reports/code_census_2026-10-16.md
- [D] docs/reference/reports/config_provenance_audit_2026-10-16.md
- [D] docs/reference/reports/confounder_strata_audit_2026-09-14.md
- [V] docs/reference/reports/data_contract_edges_2026-10-16.csv
- [D] docs/reference/reports/data_contract_inventory_2026-10-16.md
- [D] docs/reference/reports/deletion_quarantine_ledger_2026-10-16.md
- [D] docs/reference/reports/dependency_closure_2026-10-16.md
- [D] docs/reference/reports/dependency_reproducibility_audit_2026-10-16.md
- [D] docs/reference/reports/docs_consolidation_design_2026-10-16.md
- [D] docs/reference/reports/docs_staleness_audit_2026-10-16.md
- [D] docs/reference/reports/duplication_audit_2026-10-16.md
- [D] docs/reference/reports/dynamic_import_resolution_2026-10-16.md
- [V] docs/reference/reports/entrypoint_inventory_2026-10-16.csv
- [D] docs/reference/reports/entrypoint_inventory_2026-10-16.md
- [D] docs/reference/reports/entrypoint_ops_audit_2026-10-16.md
- [D] docs/reference/reports/evidence_maturity_register_2026-10-16.md
- [D] docs/reference/reports/forward_diary_archive_2026-09-14.md
- [D] docs/reference/reports/freeze_playbook_2026-09-11.md
- [C] docs/reference/reports/github_reconciliation_receipt_2026-10-19.json
- [D] docs/reference/reports/granular_open_calibration_2026-09-01.md
- [D] docs/reference/reports/historical_clv_odds_apis_2026-09-02.md
- [D] docs/reference/reports/hygiene_automation_design_2026-10-16.md
- [D] docs/reference/reports/juiced_replay_ledger_2026-09-11.md
- [D] docs/reference/reports/known_issues_overnight_p2_2026-10-13.md
- [D] docs/reference/reports/language_runtime_decision_memo_2026-10-16.md
- [D] docs/reference/reports/maintenance_inventory_2026-10-15.md
- [D] docs/reference/reports/maintenance_pass2_preservation_inventory_2026-10-15.md
- [D] docs/reference/reports/maintenance_pass3_deviation_checklist_2026-10-15.md
- [D] docs/reference/reports/maintenance_slice_specs_2026-10-16.md
- [D] docs/reference/reports/metrics_evaluation_architecture_2026-10-16.md
- [V] docs/reference/reports/model_comparison_pack/2026-08-21-ranked-summary.csv
- [C] docs/reference/reports/model_comparison_pack/2026-08-21.manifest.json
- [D] docs/reference/reports/model_comparison_pack/2026-08-21.md
- [D] docs/reference/reports/notebook_artifact_census_2026-10-16.md
- [D] docs/reference/reports/notebook_deep_review_2026-10-16.md
- [D] docs/reference/reports/o3_settlement_contract_proposal_2026-10-19.md
- [D] docs/reference/reports/observability_audit_2026-10-16.md
- [D] docs/reference/reports/oddsapi_replay_inventory_2026-09-11.md
- [D] docs/reference/reports/ops_contracts_2026-09-30.md
- [D] docs/reference/reports/pa_bf_review_record_2026-10-12.md
- [D] docs/reference/reports/phase8_5_truth_sync_2026-09-30.md
- [D] docs/reference/reports/policy_reset_2025lock_prereg_2026-09-11.md
- [D] docs/reference/reports/pr_quality_template_pack_2026-10-16.md
- [D] docs/reference/reports/preservation_closeout_2026-10-19.md
- [D] docs/reference/reports/python_dead_code_audit_2026-10-16.md
- [D] docs/reference/reports/qira_os_skill_benchmark_supplement_2026-10-16.md
- [D] docs/reference/reports/ratings_hook_wake_2026-09-14.md
- [D] docs/reference/reports/real_bets_logging_checklist.md
- [D] docs/reference/reports/repo_cleanup_backlog_2026-10-16.md
- [D] docs/reference/reports/repo_quality_baseline_2026-10-16.md
- [D] docs/reference/reports/repo_quality_index_2026-10-16.md
- [D] docs/reference/reports/repo_quality_passthrough/2026-08-18.md
- [D] docs/reference/reports/repo_quality_passthrough/2026-08-21.md
- [D] docs/reference/reports/sb_dependency_declaration_choices_2026-10-19.md
- [D] docs/reference/reports/security_config_audit_2026-10-16.md
- [D] docs/reference/reports/shared_utility_consolidation_plan_2026-10-16.md
- [V] docs/reference/reports/shared_utility_family_inventory_2026-10-16.csv
- [D] docs/reference/reports/skill_acceptance_test_plan_2026-10-16.md
- [D] docs/reference/reports/skill_adoption_matrix_2026-10-16.md
- [D] docs/reference/reports/skill_benchmark_2026-10-16.md
- [D] docs/reference/reports/slate_shock_join_2026-09-11.md
- [V] docs/reference/reports/supersession_graph_2026-10-16.csv
- [D] docs/reference/reports/supersession_graph_report_2026-10-16.md
- [D] docs/reference/reports/t6_prereg_disposition_plan_2026-10-16.md
- [D] docs/reference/reports/test_quality_audit_2026-10-16.md
- [D] docs/reference/reports/weekly_policy_settle_pack_latest.md
- [D] docs/reference/research_assistant_instructions.md
- [D] docs/reference/results_dashboard_diagnostics.md
- [V] docs/reference/results_index.csv
- [D] docs/reference/results_index.md
- [D] docs/reference/retrain_spec.md
- [D] docs/research/PAPER_NOTES.md
- [D] docs/research/README.md
- [D] docs/research/count_layer_findings.md
- [D] docs/research/floor_freeze_log.md
- [D] docs/research/historical-step-findings-summary.md
- [D] docs/research/notebook_change_log.md
- [D] docs/research/phase11_model_quality_gates.md
- [D] docs/research/phase_d_population_findings.md
- [D] docs/research/pitch_type_strike_csw_findings.md
- [D] docs/research/prob_calibration_findings.md
- [D] docs/research/snapshots/2026-08-20/final58_consensus_freeze.md
- [D] docs/research/snapshots/README.md
- [D] docs/research/statistical_audit_and_sequencing_report.md
- [D] docs/research/step10_p1_registry_freeze.md
- [D] docs/research/step11_discipline_registry_freeze.md
- [D] docs/research/step7_registry_freeze.md
- [D] docs/research/tbf_first_model_findings.md
- [D] docs/research/tbf_spine_phase_ab.md

### dotfiles/ (47)
- [D] .agents/skills/repo-garbage-collector/SKILL.md
- [D] .agents/skills/repo-garbage-collector/references/cleanup-policy.md
- [D] .agents/skills/repo-garbage-collector/references/metric-invariants.md
- [D] .agents/skills/repo-garbage-collector/references/verification-checklist.md
- [O] .agents/skills/repo-garbage-collector/scripts/duplicate_finder.py
- [O] .agents/skills/repo-garbage-collector/scripts/find_doc_claims.py
- [O] .agents/skills/repo-garbage-collector/scripts/inventory_repo.py
- [O] .agents/skills/repo-garbage-collector/scripts/reference_graph.py
- [?] .clineignore
- [?] .cursor/rules/agent-context.mdc
- [?] .cursor/rules/documentation-policy.mdc
- [?] .cursor/rules/execution-backlog.mdc
- [?] .cursor/rules/git-push-policy.mdc
- [?] .cursor/rules/ml-experiment-policy.mdc
- [?] .cursor/rules/repository-safety.mdc
- [?] .cursor/rules/use-polars.mdc
- [D] .cursor/skills/archive-research-memory/SKILL.md
- [D] .cursor/skills/audit-backtest-integrity/SKILL.md
- [D] .cursor/skills/audit-dead-code/SKILL.md
- [D] .cursor/skills/audit-feature-leakage/SKILL.md
- [D] .cursor/skills/compare-champion-challenger/SKILL.md
- [D] .cursor/skills/consolidate-code/SKILL.md
- [D] .cursor/skills/design-ml-experiment/SKILL.md
- [D] .cursor/skills/document-architecture/SKILL.md
- [D] .cursor/skills/grill-with-docs/SKILL.md
- [D] .cursor/skills/improve-codebase-architecture/SKILL.md
- [D] .cursor/skills/reconcile-baseball-stats/SKILL.md
- [D] .cursor/skills/repo-artifact-lifecycle-auditor/SKILL.md
- [D] .cursor/skills/repo-ci-coverage-auditor/SKILL.md
- [D] .cursor/skills/repo-dead-code-auditor/SKILL.md
- [D] .cursor/skills/repo-dependency-hygiene/SKILL.md
- [D] .cursor/skills/repo-docs-canonicalizer/LANGUAGE.md
- [D] .cursor/skills/repo-docs-canonicalizer/SKILL.md
- [D] .cursor/skills/repo-garbage-collector/LANGUAGE.md
- [D] .cursor/skills/repo-garbage-collector/SKILL.md
- [D] .cursor/skills/repo-quality-passthrough/SKILL.md
- [D] .cursor/skills/repo-quality-passthrough/reference.md
- [D] .cursor/skills/repo-setup-onboarding/SKILL.md
- [D] .cursor/skills/write-adr/SKILL.md
- [?] .cursorignore
- [?] .cursorindexingignore
- [?] .env.example
- [?] .gitattributes
- [D] .github/PULL_REQUEST_TEMPLATE.md
- [C] .github/workflows/ci.yml
- [?] .gitignore
- [C] .pre-commit-config.yaml

### models/ (79)
- [D] models/README.md
- [F] models/Strikeout-Model/Model-Graphs/lgb_feature_importance.png
- [D] models/Strikeout-Model/README.md
- [M] models/Strikeout-Model/predict_slate.py
- [D] models/Strikeout-Model/research/README.md
- [M] models/Strikeout-Model/research/ablate_sparse72_model_families.py
- [M] models/Strikeout-Model/research/ablation_bootstrap.py
- [M] models/Strikeout-Model/research/age_member_brier.py
- [M] models/Strikeout-Model/research/age_per_term_ablation.py
- [M] models/Strikeout-Model/research/age_walkforward.py
- [M] models/Strikeout-Model/research/aggregate_feature_chunks.py
- [M] models/Strikeout-Model/research/anti_leak_final_suite.py
- [M] models/Strikeout-Model/research/assemble_chunk_winner_pool.py
- [M] models/Strikeout-Model/research/batter_discipline_ablation.py
- [M] models/Strikeout-Model/research/batter_quality_ablation.py
- [M] models/Strikeout-Model/research/beta_binomial_nested_compare.py
- [M] models/Strikeout-Model/research/binomial_nested_compare.py
- [M] models/Strikeout-Model/research/build_final58_refined_registry.py
- [M] models/Strikeout-Model/research/calibrate_stack.py
- [M] models/Strikeout-Model/research/combined60_final.py
- [M] models/Strikeout-Model/research/combo_refine_final58_windows.py
- [M] models/Strikeout-Model/research/command_optionA_retest.py
- [M] models/Strikeout-Model/research/deep_feature_review.py
- [M] models/Strikeout-Model/research/exploratory_pipeline_bakeoff.py
- [M] models/Strikeout-Model/research/feature_ablation.py
- [M] models/Strikeout-Model/research/fetch_pitcher_birthdates.py
- [M] models/Strikeout-Model/research/final_feature_dataset_search.py
- [M] models/Strikeout-Model/research/final_feature_set_ablation.py
- [M] models/Strikeout-Model/research/fit_prob_calibration.py
- [M] models/Strikeout-Model/research/full_feature_importance_screen.py
- [M] models/Strikeout-Model/research/greedy_refine_final58_windows.py
- [M] models/Strikeout-Model/research/kadj_member_test.py
- [M] models/Strikeout-Model/research/leave_family_out_ablation.py
- [M] models/Strikeout-Model/research/lgbm_lift_promotion.py
- [M] models/Strikeout-Model/research/marcel_baseline.py
- [M] models/Strikeout-Model/research/materialize_frontier_top_candidates.py
- [M] models/Strikeout-Model/research/max_lift_exploration.py
- [M] models/Strikeout-Model/research/max_lift_robustness_suite.py
- [M] models/Strikeout-Model/research/merge_ranked_feature_pools.py
- [M] models/Strikeout-Model/research/multi_lift_pre_freeze.py
- [M] models/Strikeout-Model/research/nested_cv.py
- [M] models/Strikeout-Model/research/pa_weight_nested_compare.py
- [M] models/Strikeout-Model/research/phase_d_pa_cutoff_screen.py
- [M] models/Strikeout-Model/research/phase_d_population_audit.py
- [M] models/Strikeout-Model/research/physics_window_ablation.py
- [M] models/Strikeout-Model/research/pitch_type_strike_csw_lift.py
- [M] models/Strikeout-Model/research/pitch_type_woba_lift.py
- [M] models/Strikeout-Model/research/print_step9_inventory.py
- [M] models/Strikeout-Model/research/probe_window_swaps_final58.py
- [M] models/Strikeout-Model/research/root_feature_reevaluation.py
- [M] models/Strikeout-Model/research/run_batter_discipline_stabilization.py
- [M] models/Strikeout-Model/research/run_batter_quality_stabilization.py
- [M] models/Strikeout-Model/research/run_interaction_family_ablation.py
- [M] models/Strikeout-Model/research/run_interaction_feature_walkforward_suite.py
- [M] models/Strikeout-Model/research/run_pitch_type_stabilization.py
- [M] models/Strikeout-Model/research/run_single_feature_checks.py
- [M] models/Strikeout-Model/research/run_stabilization.py
- [M] models/Strikeout-Model/research/section61_checks.py
- [M] models/Strikeout-Model/research/sparse40_model_variant_scan.py
- [M] models/Strikeout-Model/research/sparse40_stability_filter.py
- [N] models/Strikeout-Model/research/stabilization.ipynb
- [M] models/Strikeout-Model/research/step8_keep_drop.py
- [M] models/Strikeout-Model/research/step9_metric_window_select.py
- [M] models/Strikeout-Model/research/step9_widen_priority.py
- [M] models/Strikeout-Model/research/step9c_short_std_and_p1.py
- [N] models/Strikeout-Model/research/strikeout-eda.ipynb
- [M] models/Strikeout-Model/research/targeted_window_ablation.py
- [M] models/Strikeout-Model/research/tune_lightgbm_feature_set_optuna.py
- [M] models/Strikeout-Model/research/tune_lightgbm_final58_optuna.py
- [M] models/Strikeout-Model/research/tune_lightgbm_production.py
- [M] models/Strikeout-Model/research/walkforward_bootstrap.py
- [M] models/Strikeout-Model/research/walkforward_stack_backtest.py
- [M] models/Strikeout-Model/research/window_ablation.py
- [D] models/Strikeout-Model/results/README.md
- [M] models/Strikeout-Model/score_count_layer.py
- [N] models/Strikeout-Model/train.ipynb
- [M] models/Strikeout-Model/train.py
- [D] models/TBF-Model/README.md
- [M] models/TBF-Model/train.py

### playground/ (4)
- [D] playground/README.md
- [O] playground/__init__.py
- [O] playground/line_shopper.py
- [O] playground/whatif_pitcher.py

### production/ (191)
- [D] production/INDEX.md
- [D] production/README.md
- [D] production/RUNBOOK.md
- [P] production/app/dashboard_streamlit.py
- [D] production/cloud/README.md
- [P] production/cloud/modal_app.py
- [D] production/notebooks/README.md
- [P] production/notebooks/_notebook_score.py
- [N] production/notebooks/daily_projections.ipynb
- [N] production/notebooks/model_governance.ipynb
- [N] production/notebooks/results_bettable_cohort.ipynb
- [N] production/notebooks/results_calibration_lab.ipynb
- [N] production/notebooks/results_dashboard.ipynb
- [N] production/notebooks/results_kpi_monitor.ipynb
- [N] production/notebooks/results_pnl_clv.ipynb
- [N] production/notebooks/results_recommendation_audit.ipynb
- [D] production/odds/README.md
- [P] production/odds/build_ab_board_diff.py
- [P] production/odds/close_watcher.py
- [P] production/odds/grade_odds_ledger.py
- [P] production/odds/log_odds_quotes.py
- [P] production/odds/odds_board.py
- [P] production/odds/poll_odds.py
- [O] production/odds/run_close_watcher.ps1
- [D] production/ops/README.md
- [P] production/ops/backfill_open_projection_overlap.py
- [P] production/ops/backfill_real_bets.py
- [P] production/ops/build_automation_self_check.py
- [P] production/ops/build_aux_market_shadow_score.py
- [P] production/ops/build_board_ledger_reconciliation.py
- [P] production/ops/build_book_quality_scorecard.py
- [P] production/ops/build_daily_operator_summary.py
- [P] production/ops/build_line_price_calibration_gap.py
- [P] production/ops/build_line_price_correction_table.py
- [P] production/ops/build_open_market_diagnostics.py
- [P] production/ops/build_open_projection_calibration_suite.py
- [P] production/ops/build_open_projection_signal.py
- [P] production/ops/build_policy_governance_report.py
- [P] production/ops/build_runtime_monitoring_snapshot.py
- [P] production/ops/build_segment_calibration_offsets.py
- [P] production/ops/build_validation_ops_report.py
- [P] production/ops/build_weekly_policy_digest.py
- [P] production/ops/build_winner_board_local.py
- [P] production/ops/calibration_snapshot.py
- [P] production/ops/check_data_freshness.py
- [P] production/ops/check_drawdown_brake.py
- [P] production/ops/check_nightly_drift.py
- [P] production/ops/compact_aux_quote_history.py
- [P] production/ops/compare_feature_set_governance.py
- [P] production/ops/compare_feature_set_market_skill.py
- [P] production/ops/compare_model_family_governance.py
- [P] production/ops/edge_floor_sweep_governance.py
- [V] production/ops/exit_anomaly_overrides.csv
- [P] production/ops/fit_granular_open_calibration.py
- [P] production/ops/frozen_edge_watch.py
- [P] production/ops/heal_stale_slate.py
- [P] production/ops/kpi_daily_action.py
- [C] production/ops/kpi_policy.json
- [C] production/ops/live_krate_ensemble.json
- [P] production/ops/log_model_lineage.py
- [D] production/ops/market_research/README.md
- [P] production/ops/market_research/alt_curve_harness.py
- [P] production/ops/market_research/alt_curve_measure.py
- [P] production/ops/market_research/analyze_book_skill.py
- [P] production/ops/market_research/analyze_open_model_deltas.py
- [P] production/ops/market_research/apply_calibration_policy.py
- [P] production/ops/market_research/bettable_calibration.py
- [P] production/ops/market_research/build_age_table.py
- [P] production/ops/market_research/build_calibration_deploy_matrix.py
- [P] production/ops/market_research/build_consensus_cache.py
- [P] production/ops/market_research/build_prob_scoring_report.py
- [P] production/ops/market_research/build_start_command.py
- [P] production/ops/market_research/calibrate_showdown.py
- [C] production/ops/market_research/calibration_policy.json
- [P] production/ops/market_research/clv_basis_reconcile.py
- [P] production/ops/market_research/clv_flavors.py
- [P] production/ops/market_research/combo_matrix.py
- [P] production/ops/market_research/confounder_strata_audit.py
- [P] production/ops/market_research/correction_audit.py
- [P] production/ops/market_research/count_family_race.py
- [P] production/ops/market_research/decision_grade_harness.py
- [P] production/ops/market_research/deploy_regate.py
- [P] production/ops/market_research/disagreement_signal_probe.py
- [P] production/ops/market_research/distill_stacker.py
- [P] production/ops/market_research/fills_analytics.py
- [P] production/ops/market_research/fit_consensus_blend.py
- [P] production/ops/market_research/game_cap_audit.py
- [P] production/ops/market_research/glicko_pitcher_ratings.py
- [P] production/ops/market_research/hook_pull_table.py
- [P] production/ops/market_research/join_keys.py
- [P] production/ops/market_research/join_universe.py
- [P] production/ops/market_research/juiced_price_spike.py
- [P] production/ops/market_research/juiced_replay_ledger.py
- [P] production/ops/market_research/kadj_l3_parity.py
- [P] production/ops/market_research/kalshi_disagreement_audit.py
- [P] production/ops/market_research/kalshi_k_reader.py
- [P] production/ops/market_research/kalshi_overlay_gate.py
- [P] production/ops/market_research/ladder_sim.py
- [P] production/ops/market_research/ledger_gate.py
- [P] production/ops/market_research/ledger_gate_glicko.py
- [P] production/ops/market_research/ledger_gate_kadj.py
- [P] production/ops/market_research/ledger_gate_stacker.py
- [C] production/ops/market_research/line_cell_gate_2025.json
- [C] production/ops/market_research/line_floor_policy.json
- [P] production/ops/market_research/line_policy_settled_lookback.py
- [P] production/ops/market_research/line_side_policy.py
- [P] production/ops/market_research/mc_reality_gate.py
- [P] production/ops/market_research/monte_carlo_starts.py
- [P] production/ops/market_research/monthly_prob_curves.py
- [P] production/ops/market_research/nb_tbf_mixture.py
- [P] production/ops/market_research/novig_probe.py
- [P] production/ops/market_research/pa_sim.py
- [P] production/ops/market_research/paper_ladder.py
- [P] production/ops/market_research/pnl_sensitivity_audit.py
- [P] production/ops/market_research/probe_2023_2024.py
- [P] production/ops/market_research/promote_ws1c.py
- [P] production/ops/market_research/pull_featured_totals.py
- [P] production/ops/market_research/pull_kalshi_k_history.py
- [P] production/ops/market_research/pull_oddsapi_historical.py
- [P] production/ops/market_research/pull_opencommand.py
- [P] production/ops/market_research/pull_regular_season_closeout.py
- [P] production/ops/market_research/recover_snapshot_envelope.py
- [P] production/ops/market_research/rescore_cal_cells.py
- [P] production/ops/market_research/rescore_shiplift.py
- [P] production/ops/market_research/run_market_research.py
- [P] production/ops/market_research/run_universe_cells.py
- [P] production/ops/market_research/score_historical_range.py
- [P] production/ops/market_research/season_metrics.py
- [P] production/ops/market_research/select_2025_champion.py
- [P] production/ops/market_research/september_cohort.py
- [P] production/ops/market_research/sizing_judgment.py
- [P] production/ops/market_research/slate_shock_join.py
- [P] production/ops/market_research/tail_recal.py
- [P] production/ops/market_research/v4_showdown.py
- [P] production/ops/market_research/ws1c_line_recal.py
- [P] production/ops/market_research/ws2_age_cells.py
- [P] production/ops/market_research/ws2_age_correct.py
- [P] production/ops/market_research/ws2_staleness_probe.py
- [P] production/ops/market_research/ws3_tbf_probe.py
- [P] production/ops/market_research/ws3b_hook_rates.py
- [P] production/ops/market_research/ws3c_workhorse.py
- [P] production/ops/market_research/ws5b_blend_fit.py
- [P] production/ops/market_research/ws5b_poisson_binomial.py
- [P] production/ops/market_research/ws6_timing_decay.py
- [P] production/ops/market_research/ws7_floor_gate.py
- [P] production/ops/market_research/ws8_kadj_probe.py
- [P] production/ops/market_research/ws9_famvuln_probe.py
- [P] production/ops/market_research/zone_probe.py
- [P] production/ops/paper_quant_track.py
- [P] production/ops/policy_calibration_uncertainty_sweep.py
- [P] production/ops/policy_freshness_audit.py
- [P] production/ops/policy_simulator.py
- [P] production/ops/prune_artifacts.py
- [P] production/ops/recalibrate_top3_ensembles_open_to_manual.py
- [P] production/ops/refresh_features.py
- [P] production/ops/refresh_statcast.py
- [O] production/ops/run_analysis_notebooks.ps1
- [O] production/ops/run_catchup.ps1
- [P] production/ops/run_champion_challenger_cycle.py
- [P] production/ops/run_close_sweep.py
- [P] production/ops/run_daily.py
- [P] production/ops/run_daily_kpi_loop.py
- [O] production/ops/run_daily_operator_flow.ps1
- [O] production/ops/run_end_of_day_settle.ps1
- [O] production/ops/run_market_refresh.ps1
- [P] production/ops/run_model_ensemble_sweep.py
- [P] production/ops/run_monitoring_cycle.py
- [O] production/ops/run_morning_workflow.ps1
- [O] production/ops/run_nightly_drift.ps1
- [P] production/ops/run_null_decision_lane.py
- [P] production/ops/run_open_snapshot_counterfactual.py
- [P] production/ops/run_post_score_automation.py
- [P] production/ops/run_postfreeze_deep_diagnosis.py
- [O] production/ops/run_self_check_task.ps1
- [P] production/ops/run_shadow_asymmetric_policy.py
- [O] production/ops/run_task_captured.ps1
- [P] production/ops/run_tuned_lgbm_ensemble_sweep.py
- [O] production/ops/run_wake_recovery.ps1
- [P] production/ops/run_weekly_policy_settle_pack.py
- [P] production/ops/score_slate.py
- [P] production/ops/send_daily_grading.py
- [P] production/ops/send_morning_alert.py
- [O] production/ops/set_alert_env.ps1
- [O] production/ops/setup_automation_tasks.ps1
- [O] production/ops/start_close_watcher_background.ps1
- [O] production/ops/watch_close_watcher_health.ps1
- [P] production/ops/weekly_kpi_report.py
- [D] production/projections/README.md
- [P] production/projections/grade_projections.py
- [P] production/projections/log_projections.py
- [P] production/projections/post_freeze_holdout.py

### (root) pyproject.toml
- [C] pyproject.toml

### report/ (1)
- [D] report/recency_batch_results_table.md

### research/ (287)
- [D] research/offseason_2026/README.md
- [D] research/offseason_2026/bf-2026-predictor-seal-v1/CLASSIFICATION.md
- [D] research/offseason_2026/bf-2026-predictor-seal-v1/README.md
- [D] research/offseason_2026/bf-2026-predictor-seal-v1/READY_BRIEF.md
- [D] research/offseason_2026/bf-distribution-design-prereg.md
- [D] research/offseason_2026/bf-distribution-readiness-clarifications.md
- [D] research/offseason_2026/bf-origin-tail-audit-2026-10-08.md
- [R] research/offseason_2026/bf_distribution.py
- [D] research/offseason_2026/bf_lane/B1_CLOSEOUT.md
- [D] research/offseason_2026/bf_lane/COUNT_REGISTRATION.md
- [D] research/offseason_2026/bf_lane/PROJECTED_LINEUP_SPEC.md
- [R] research/offseason_2026/bf_lane/b1_d1_ci95_correction_v1.py
- [C] research/offseason_2026/bf_lane/freeze_count_eval_v1.json
- [R] research/offseason_2026/bf_lane/recover_b1_logging_v1.py
- [R] research/offseason_2026/bf_lane/run_b1_ridge_v1.py
- [R] research/offseason_2026/bf_lane/run_count_b1_v1.py
- [R] research/offseason_2026/bf_lane/test_b1_d1_ci95_correction.py
- [R] research/offseason_2026/bf_lane/test_run_count_b1_v1.py
- [C] research/offseason_2026/bf_workload_v1/report.json
- [C] research/offseason_2026/bf_workload_v1/report_v2.json
- [R] research/offseason_2026/bf_workload_v1/scripts/run_kcount_comparison.py
- [R] research/offseason_2026/bf_workload_v1/scripts/run_kcount_correction_v2.py
- [R] research/offseason_2026/bf_workload_v1/tests/test_milestone_correction.py
- [R] research/offseason_2026/boundary.py
- [R] research/offseason_2026/build_wf_spine_2024.py
- [R] research/offseason_2026/contracts/pa_contracts.py
- [D] research/offseason_2026/corrected-history-feature-manifest.md
- [D] research/offseason_2026/corrected-history-workload-prereg.md
- [R] research/offseason_2026/datasets/build_eval_panel.py
- [R] research/offseason_2026/datasets/build_funnel.py
- [R] research/offseason_2026/datasets/build_pa_dataset.py
- [B] research/offseason_2026/datasets/eval_panel.parquet
- [C] research/offseason_2026/datasets/eval_panel_manifest.json
- [C] research/offseason_2026/datasets/pa_dataset_manifest.json
- [C] research/offseason_2026/datasets/pa_funnel_manifest.json
- [B] research/offseason_2026/datasets/pa_table_2023_2024.parquet
- [D] research/offseason_2026/early-season-extension-prereg.md
- [R] research/offseason_2026/eval_package.py
- [D] research/offseason_2026/expanding-training-prereg-draft.md
- [D] research/offseason_2026/expanding-training-prereg.md
- [D] research/offseason_2026/experiments/bf-2026-cohort-enumeration-2026-10-14/card.md
- [B] research/offseason_2026/experiments/bf-2026-cohort-enumeration-2026-10-14/cohort_rows_metadata.parquet
- [C] research/offseason_2026/experiments/bf-2026-cohort-enumeration-2026-10-14/report.json
- [D] research/offseason_2026/experiments/bf-cohort-scorer-mode-2026-10-14/card.md
- [C] research/offseason_2026/experiments/bf-cohort-scorer-mode-2026-10-14/demo_report.json
- [C] research/offseason_2026/experiments/bf-cohort-scorer-mode-2026-10-14/pinned_manifest_pilot134.json
- [D] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/card.md
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/demo_rerun_after_enforcement/demo_report.json
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/demo_rerun_after_enforcement/pinned_manifest_pilot134.json
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/enforcement_checks/enforcement_verification.json
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/enforcement_checks/membership_badstatus.json
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/enforcement_checks/membership_dup.json
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/enforcement_checks/membership_extra.json
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/enforcement_checks/membership_flip.json
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/enforcement_checks/membership_missing.json
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/enforcement_checks/membership_swapped.json
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/enforcement_checks/out_positive/cohort_validation_report.json
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/hash_ledger.json
- [R] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/pmf_divergence_compare.py
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/pmf_divergence_report.json
- [C] research/offseason_2026/experiments/bf-pilot-diagnostic-reclass-2026-10-14/synthetic_label_run/cohort_scoring_report.json
- [D] research/offseason_2026/experiments/lgbm-equal-info-v1-prep-2026-10-15/card.md
- [D] research/offseason_2026/experiments/lgbm-equal-info-v2-closeout-2026-10-16/card.md
- [R] research/offseason_2026/experiments/logistic_pa/bundle/build_bundle.py
- [C] research/offseason_2026/experiments/logistic_pa/bundle/feature_manifest.json
- [C] research/offseason_2026/experiments/logistic_pa/bundle/hashes.json
- [C] research/offseason_2026/experiments/logistic_pa/bundle/model_bundle.json
- [C] research/offseason_2026/experiments/logistic_pa/bundle/model_card.json
- [C] research/offseason_2026/experiments/logistic_pa/bundle/preprocessing_manifest.json
- [D] research/offseason_2026/experiments/logistic_pa/bundle/provenance_sidecar.md
- [C] research/offseason_2026/experiments/logistic_pa/card.json
- [D] research/offseason_2026/experiments/logistic_pa/deviations.md
- [C] research/offseason_2026/experiments/logistic_pa/hashes.json
- [C] research/offseason_2026/experiments/logistic_pa/metrics.json
- [C] research/offseason_2026/experiments/logistic_pa/next_tree_card_draft.json
- [C] research/offseason_2026/experiments/logistic_pa/output_hashes.json
- [B] research/offseason_2026/experiments/logistic_pa/pa_predictions.parquet
- [B] research/offseason_2026/experiments/logistic_pa/reliability.parquet
- [D] research/offseason_2026/experiments/logistic_pa/report.md
- [R] research/offseason_2026/experiments/logistic_pa/run_phase7.py
- [D] research/offseason_2026/experiments/logistic_pa/validation_lanes.md
- [C] research/offseason_2026/experiments/pa1a_raw_pa/attribution_reconciliation.json
- [D] research/offseason_2026/experiments/pa1a_raw_pa/attribution_sha.txt
- [C] research/offseason_2026/experiments/pa1a_raw_pa/card.json
- [D] research/offseason_2026/experiments/pa1a_raw_pa/deviations.md
- [C] research/offseason_2026/experiments/pa1a_raw_pa/hashes.json
- [R] research/offseason_2026/experiments/pa1a_raw_pa/make_cards.py
- [B] research/offseason_2026/experiments/pa1a_raw_pa/per_pa.parquet
- [C] research/offseason_2026/experiments/pa1a_raw_pa/preflight.json
- [B] research/offseason_2026/experiments/pa1a_raw_pa/reliability.parquet
- [R] research/offseason_2026/experiments/pa1a_raw_pa/run_pa1a.py
- [C] research/offseason_2026/experiments/pa1b_oracle_xk/bootstrap.json
- [C] research/offseason_2026/experiments/pa1b_oracle_xk/card.json
- [C] research/offseason_2026/experiments/pa1b_oracle_xk/completeness.json
- [D] research/offseason_2026/experiments/pa1b_oracle_xk/deviations.md
- [C] research/offseason_2026/experiments/pa1b_oracle_xk/frozen_comparator_validity.json
- [C] research/offseason_2026/experiments/pa1b_oracle_xk/hashes.json
- [C] research/offseason_2026/experiments/pa1b_oracle_xk/metrics.json
- [C] research/offseason_2026/experiments/pa1b_oracle_xk/output_hashes.json
- [C] research/offseason_2026/experiments/pa1b_oracle_xk/paired_comparisons.json
- [C] research/offseason_2026/experiments/pa1b_oracle_xk/preflight.json
- [C] research/offseason_2026/experiments/pa1b_oracle_xk/prep.json
- [D] research/offseason_2026/experiments/pa1b_oracle_xk/report.md
- [C] research/offseason_2026/experiments/pa1b_oracle_xk/residual_diagnostics.json
- [R] research/offseason_2026/experiments/pa1b_oracle_xk/run_pa1b_o.py
- [C] research/offseason_2026/experiments/pa1b_oracle_xk/slices.json
- [B] research/offseason_2026/experiments/pa1b_oracle_xk/start_predictions.parquet
- [C] research/offseason_2026/experiments/pitcher_prior/bootstrap.json
- [C] research/offseason_2026/experiments/pitcher_prior/calibration.json
- [C] research/offseason_2026/experiments/pitcher_prior/card.json
- [D] research/offseason_2026/experiments/pitcher_prior/deviations.md
- [R] research/offseason_2026/experiments/pitcher_prior/gate_prep.py
- [C] research/offseason_2026/experiments/pitcher_prior/hashes.json
- [C] research/offseason_2026/experiments/pitcher_prior/metrics.json
- [C] research/offseason_2026/experiments/pitcher_prior/output_hashes.json
- [B] research/offseason_2026/experiments/pitcher_prior/pa_predictions.parquet
- [C] research/offseason_2026/experiments/pitcher_prior/paired_comparisons.json
- [C] research/offseason_2026/experiments/pitcher_prior/pitcher_identity_resolution.json
- [C] research/offseason_2026/experiments/pitcher_prior/preflight.json
- [C] research/offseason_2026/experiments/pitcher_prior/prep.json
- [D] research/offseason_2026/experiments/pitcher_prior/report.md
- [R] research/offseason_2026/experiments/pitcher_prior/run_pitcher_prior.py
- [C] research/offseason_2026/experiments/pitcher_prior/slices.json
- [D] research/offseason_2026/experiments/recency-batch-v1-2026-10-15/card.md
- [C] research/offseason_2026/experiments/recency-batch-v1-2026-10-15/independent_recompute_verification.json
- [C] research/offseason_2026/experiments/recency-batch-v1-2026-10-15/metrics.json
- [D] research/offseason_2026/experiments/recency-batch-v1-2026-10-15/metrics.md
- [C] research/offseason_2026/experiments/tree_pa/card.json
- [D] research/offseason_2026/experiments/tree_pa/deviations.md
- [C] research/offseason_2026/experiments/tree_pa/hashes.json
- [C] research/offseason_2026/experiments/tree_pa/lineup_replay_audit.json
- [C] research/offseason_2026/experiments/tree_pa/metrics.json
- [C] research/offseason_2026/experiments/tree_pa/output_hashes.json
- [C] research/offseason_2026/experiments/tree_pa/paired_comparisons.json
- [D] research/offseason_2026/experiments/tree_pa/report.md
- [R] research/offseason_2026/experiments/tree_pa/run_tree.py
- [C] research/offseason_2026/experiments/tree_pa/slices.json
- [B] research/offseason_2026/experiments/tree_pa/tree_predictions.parquet
- [D] research/offseason_2026/history-contract-2026-10-08.md
- [D] research/offseason_2026/i3-closeout-2026-10-08.md
- [D] research/offseason_2026/i3b-transfer-freeze-2024.md
- [D] research/offseason_2026/i4-card-source-experiment-draft.md
- [D] research/offseason_2026/i4-card-source-experiment.md
- [D] research/offseason_2026/i5-tail-challenger-draft.md
- [D] research/offseason_2026/i5-tail-challenger.md
- [D] research/offseason_2026/kcount-integration-clarification-2026-10-08.md
- [D] research/offseason_2026/kcount-integration-prereg-draft.md
- [D] research/offseason_2026/kcount-integration-prereg.md
- [R] research/offseason_2026/kcount_combiner.py
- [D] research/offseason_2026/lgbm-bridge-contract-2026-10-09.md
- [R] research/offseason_2026/lineup_opportunity.py
- [?] research/offseason_2026/market_eval/.gitattributes
- [D] research/offseason_2026/market_eval/ARTIFACT_MAP.md
- [D] research/offseason_2026/market_eval/BUILDER_HANDOFF.md
- [D] research/offseason_2026/market_eval/BUNDLE_EXTRACTION.md
- [D] research/offseason_2026/market_eval/CHAT2_HANDOFF.md
- [D] research/offseason_2026/market_eval/EXCLUSION_LEDGER.md
- [D] research/offseason_2026/market_eval/EXPERIMENT_CARD.md
- [D] research/offseason_2026/market_eval/FINDINGS_F1_F5_2026-10-14.md
- [D] research/offseason_2026/market_eval/INCIDENT.md
- [D] research/offseason_2026/market_eval/METRIC_SCHEMA.md
- [D] research/offseason_2026/market_eval/MOMENTS.md
- [D] research/offseason_2026/market_eval/PENDING_FINDINGS.md
- [D] research/offseason_2026/market_eval/REVIEW_HANDOFF.md
- [D] research/offseason_2026/market_eval/REVIEW_SNAPSHOT.md
- [D] research/offseason_2026/market_eval/SPLIT_MAP.md
- [R] research/offseason_2026/market_eval/audit_prep_refs.py
- [R] research/offseason_2026/market_eval/market_eval.py
- [R] research/offseason_2026/market_eval/tests/test_f6_confirmation_exclusion.py
- [R] research/offseason_2026/market_eval/tests/test_f6_confirmation_separation.py
- [R] research/offseason_2026/market_eval/tests/test_market_eval.py
- [R] research/offseason_2026/market_eval/tests/test_score_end_to_end.py
- [R] research/offseason_2026/market_eval/verify_ledger.py
- [D] research/offseason_2026/p1_harness/ACCEPTANCE_EVIDENCE.md
- [D] research/offseason_2026/p1_harness/PROBABILITY_SOURCE_TABLE.md
- [D] research/offseason_2026/p1_harness/RUN_VERSION_MAP.md
- [R] research/offseason_2026/p1_harness/conftest.py
- [R] research/offseason_2026/p1_harness/scripts/build_features.py
- [R] research/offseason_2026/p1_harness/scripts/build_pa_table.py
- [R] research/offseason_2026/p1_harness/scripts/fit_models.py
- [R] research/offseason_2026/p1_harness/test_feature_contract.py
- [R] research/offseason_2026/p1_harness/test_harness_guards.py
- [R] research/offseason_2026/p1_harness/test_log5_identities.py
- [D] research/offseason_2026/pa-aggregation-contract-2026-10-09-CORRECTION-1.md
- [D] research/offseason_2026/pa-aggregation-contract-2026-10-09.md
- [D] research/offseason_2026/pa-k-baseline-prereg-draft.md
- [D] research/offseason_2026/pa-k-baseline-prereg.md
- [D] research/offseason_2026/pa-l3-refit-contract-2026-10-09.md
- [D] research/offseason_2026/pa-lgbm-contract-2026-10-09.md
- [R] research/offseason_2026/pa_k_baseline.py
- [R] research/offseason_2026/pa_lgbm_scaffold.py
- [D] research/offseason_2026/pregame-opportunity-contract-draft.md
- [D] research/offseason_2026/pregame-opportunity-contract.md
- [C] research/offseason_2026/pregame-pa-ext/OUTPUT_INVENTORY.json
- [D] research/offseason_2026/pregame-pa-ext/SEQUENCE_DEVIATION.md
- [C] research/offseason_2026/pregame-pa-ext/ablation_record_authoritative.json
- [C] research/offseason_2026/pregame-pa-ext/ablation_row_v2_status.json
- [C] research/offseason_2026/pregame-pa-ext/ablation_row_v3_status.json
- [C] research/offseason_2026/pregame-pa-ext/lake_mirror_status.json
- [C] research/offseason_2026/pregame-pa-ext/lake_mirror_status_v2.json
- [C] research/offseason_2026/pregame-pa-ext/mlflow_import_record.json
- [C] research/offseason_2026/pregame-pa-ext/mlflow_reconciliation.json
- [C] research/offseason_2026/pregame-pa-ext/supplemental_metrics.json
- [D] research/offseason_2026/pregame-pa-ext/supplemental_metrics.md
- [R] research/offseason_2026/pregame_lineup_capture.py
- [D] research/offseason_2026/pregame_pa_ext/COUNT_EVAL_COMMANDS.md
- [R] research/offseason_2026/pregame_pa_ext/adapter.py
- [R] research/offseason_2026/pregame_pa_ext/build_checkpoint.py
- [C] research/offseason_2026/pregame_pa_ext/freeze_pregame_pa_ext_v2.json
- [D] research/offseason_2026/prospective_logging/LOGGING_SPEC.md
- [R] research/offseason_2026/prospective_logging/logger.py
- [R] research/offseason_2026/prospective_logging/test_logger.py
- [D] research/offseason_2026/publication-checkpoint-staging-2026-10-08.md
- [R] research/offseason_2026/retrosheet_cards.py
- [R] research/offseason_2026/run_bf_2026_cohort_enumeration.py
- [R] research/offseason_2026/run_bf_2026_seal_parity_check.py
- [R] research/offseason_2026/run_bf_2026_seal_prep.py
- [R] research/offseason_2026/run_bf_ab_forecast_2026.py
- [R] research/offseason_2026/run_bf_ab_score_cohort.py
- [R] research/offseason_2026/run_bf_ab_score_v2.py
- [R] research/offseason_2026/run_bf_ab_score_v3.py
- [R] research/offseason_2026/run_bf_cohort_mode_demo.py
- [R] research/offseason_2026/run_bf_distribution_2023.py
- [R] research/offseason_2026/run_bf_preflight_2026.py
- [R] research/offseason_2026/run_bf_reconstruct_2026.py
- [R] research/offseason_2026/run_corrected_history_2023.py
- [R] research/offseason_2026/run_i3_opportunity_2023.py
- [R] research/offseason_2026/run_i3_transfer_2024.py
- [R] research/offseason_2026/run_i4_card_source_2023.py
- [R] research/offseason_2026/run_i5_tail_2023.py
- [R] research/offseason_2026/run_kcount_integration_2023.py
- [R] research/offseason_2026/run_lgbm_bridge.py
- [R] research/offseason_2026/run_pa_aggregation_abc.py
- [R] research/offseason_2026/run_pa_k_baseline_2023.py
- [R] research/offseason_2026/run_pa_l3_refit.py
- [R] research/offseason_2026/run_pa_label_reconciliation.py
- [R] research/offseason_2026/run_pa_lgbm_comparison.py
- [R] research/offseason_2026/run_pa_lineage_order_check.py
- [R] research/offseason_2026/run_pa_prefit_checks.py
- [R] research/offseason_2026/run_pa_pregame_ab.py
- [R] research/offseason_2026/run_pa_workload_lineup_check.py
- [R] research/offseason_2026/run_paired_uncertainty.py
- [R] research/offseason_2026/run_reconstruction_audit_2023.py
- [R] research/offseason_2026/run_sep_challenger.py
- [R] research/offseason_2026/run_training_policy_2023.py
- [R] research/offseason_2026/run_wf_comparison.py
- [D] research/offseason_2026/sep-challenger-contract.md
- [D] research/offseason_2026/specs/bf-lane-v1/B0_AUDIT.md
- [D] research/offseason_2026/specs/bf-lane-v1/B1_REGISTRATION.md
- [C] research/offseason_2026/specs/bf-lane-v1/MANIFEST.json
- [D] research/offseason_2026/specs/bf-lane-v1/SELF_CHECK_CHAT2.md
- [C] research/offseason_2026/specs/bf-lane-v1/b0_audit.json
- [V] research/offseason_2026/specs/bf-lane-v1/b0_per_start_availability.csv
- [C] research/offseason_2026/specs/bf-lane-v1/b1_registration.json
- [R] research/offseason_2026/specs/bf-lane-v1/scripts/b0_audit.py
- [D] research/offseason_2026/specs/count-eval-v2-spec/harness/CANDIDATE_MAP.md
- [D] research/offseason_2026/specs/count-eval-v2-spec/harness/FIRST_RUN_CONFIG.md
- [D] research/offseason_2026/specs/count-eval-v2-spec/harness/HANDOFF_CAPABILITIES.md
- [C] research/offseason_2026/specs/count-eval-v2-spec/harness/MLFLOW_RETRIEVAL_RECEIPT.json
- [D] research/offseason_2026/specs/count-eval-v2-spec/harness/README.md
- [D] research/offseason_2026/specs/count-eval-v2-spec/harness/RECENCY_BATCH_REGISTRATION.md
- [R] research/offseason_2026/specs/count-eval-v2-spec/harness/comparison.py
- [C] research/offseason_2026/specs/count-eval-v2-spec/harness/first_run_packet_v1.json
- [C] research/offseason_2026/specs/count-eval-v2-spec/harness/freeze_lgbm_equal_info_v1.json
- [C] research/offseason_2026/specs/count-eval-v2-spec/harness/freeze_lgbm_equal_info_v2.json
- [C] research/offseason_2026/specs/count-eval-v2-spec/harness/freeze_recency_batch_v1.json
- [R] research/offseason_2026/specs/count-eval-v2-spec/harness/run_lgbm_equal_info.py
- [R] research/offseason_2026/specs/count-eval-v2-spec/harness/run_lgbm_equal_info_v2.py
- [R] research/offseason_2026/specs/count-eval-v2-spec/harness/test_auto_tracking.py
- [R] research/offseason_2026/specs/count-eval-v2-spec/harness/test_comparison.py
- [R] research/offseason_2026/specs/count-eval-v2-spec/harness/test_lgbm_equal_info_v2.py
- [R] research/offseason_2026/specs/count-eval-v2-spec/harness/test_null_centered.py
- [R] research/offseason_2026/specs/count-eval-v2-spec/harness/track_and_verify.py
- [D] research/offseason_2026/specs/count_metrics.md
- [D] research/offseason_2026/specs/features.md
- [D] research/offseason_2026/specs/friend_retention.md
- [D] research/offseason_2026/specs/lineups.md
- [D] research/offseason_2026/specs/mlflow-mirror-implementation-card.md
- [D] research/offseason_2026/specs/pa-count-distribution-d0-d5-spec.md
- [D] research/offseason_2026/specs/pa_dataset_contract.md
- [D] research/offseason_2026/specs/pregame-workload-dev-spec.md
- [D] research/offseason_2026/specs/splits.md
- [D] research/offseason_2026/specs/tbf_residual_store.md
- [D] research/offseason_2026/transfer-2024-prereg.md
- [D] research/offseason_2026/transfer-validation-readiness-2026-10-08.md
- [D] research/offseason_2026/wf-comparison-contract-2026-10-09.md
- [R] research/offseason_2026/workload_spine.py

### scripts/ (28)
- [D] scripts/README.md
- [X] scripts/agent/check_skill_links.py
- [X] scripts/agent/inventory_skills.py
- [X] scripts/agent/validate_skills.py
- [X] scripts/backfill_historical_exit_anomaly_overrides.py
- [X] scripts/batter_pitch_type_rv_research.py
- [X] scripts/build_exit_anomaly_overrides.py
- [X] scripts/build_exit_anomaly_training_mask.py
- [X] scripts/check_notebook_artifacts.py
- [X] scripts/expanded_feature_registry.py
- [O] scripts/export-notebook.ps1
- [X] scripts/export_notebook.py
- [X] scripts/feature_coverage_matrix.py
- [X] scripts/feature_diagnostics.py
- [X] scripts/finalize_step1_registries.py
- [X] scripts/generate_results_index.py
- [X] scripts/prune_artifacts.py
- [X] scripts/repo_hygiene_check.py
- [X] scripts/report_exit_anomaly_impact.py
- [X] scripts/report_rolling_anomaly_policy_impact.py
- [C] scripts/results_index_annotations.json
- [C] scripts/results_index_exclusions.json
- [X] scripts/review_verify.py
- [X] scripts/run_walkforward_anomaly_ab.py
- [X] scripts/run_walkforward_anomaly_sensitivity.py
- [X] scripts/vif_cluster_reduction.py
- [X] scripts/window_change_proposals.py
- [X] scripts/window_stabilization_gap.py

### src/ (54)
- [N] src/Notebooks/ballpark.ipynb
- [N] src/Notebooks/batter-features.ipynb
- [N] src/Notebooks/batter_rolling.ipynb
- [N] src/Notebooks/features.ipynb
- [N] src/Notebooks/pipeline/games.ipynb
- [N] src/Notebooks/pipeline/rolling.ipynb
- [N] src/Notebooks/pipeline/training.ipynb
- [N] src/Notebooks/pitcher-features.ipynb
- [N] src/Notebooks/pitcher-rolling.ipynb
- [N] src/Notebooks/statcast.ipynb
- [D] src/Python/README.md
- [S] src/Python/__init__.py
- [S] src/Python/ballpark.py
- [S] src/Python/batter_features.py
- [S] src/Python/batter_rolling.py
- [S] src/Python/bullpen.py
- [S] src/Python/clv_basis.py
- [S] src/Python/config.py
- [S] src/Python/count_layer.py
- [S] src/Python/daily_lineups.py
- [S] src/Python/env_load.py
- [S] src/Python/exit_anomalies.py
- [S] src/Python/features.py
- [S] src/Python/identity.py
- [S] src/Python/kpi_policy.py
- [S] src/Python/likelihoods.py
- [S] src/Python/live_assembly.py
- [S] src/Python/market.py
- [S] src/Python/notebook_analysis_utils.py
- [S] src/Python/novig_client.py
- [S] src/Python/odds_board.py
- [S] src/Python/odds_close.py
- [S] src/Python/odds_ledger.py
- [S] src/Python/odds_open.py
- [S] src/Python/pipeline/__init__.py
- [S] src/Python/pipeline/games.py
- [S] src/Python/pipeline/rolling.py
- [S] src/Python/pipeline/training.py
- [S] src/Python/pitcher_features.py
- [S] src/Python/pitcher_rolling.py
- [S] src/Python/prob_calibration.py
- [S] src/Python/projection_support.py
- [S] src/Python/real_bets.py
- [S] src/Python/registries.py
- [S] src/Python/reliability.py
- [S] src/Python/run_manifest.py
- [S] src/Python/serving_gates.py
- [S] src/Python/sharp_odds.py
- [S] src/Python/skill_stats.py
- [S] src/Python/statcast.py
- [S] src/Python/tbf.py
- [S] src/Python/training.py
- [S] src/Python/whatif.py
- [D] src/README.md

### tests/ (97)
- [D] tests/README.md
- [T] tests/conftest.py
- [T] tests/test_ballpark.py
- [T] tests/test_batter_features.py
- [T] tests/test_batter_rolling.py
- [T] tests/test_bf37_wiring.py
- [T] tests/test_bf_distribution.py
- [T] tests/test_bullpen.py
- [T] tests/test_clv_basis.py
- [T] tests/test_corrected_history_2023.py
- [T] tests/test_count_b1_end_to_end.py
- [T] tests/test_count_layer.py
- [T] tests/test_daily_lineups.py
- [T] tests/test_data_freshness.py
- [T] tests/test_drawdown_brake.py
- [T] tests/test_eval_package.py
- [T] tests/test_feature_safety.py
- [T] tests/test_flips_only.py
- [T] tests/test_gc_population_truth.py
- [T] tests/test_grade_settlement_characterization.py
- [T] tests/test_grading_sharpe.py
- [T] tests/test_i3_runner.py
- [T] tests/test_identity.py
- [T] tests/test_juiced_replay_ledger.py
- [T] tests/test_kadj_join.py
- [T] tests/test_kalshi_reader.py
- [T] tests/test_kcount_combiner.py
- [T] tests/test_kcount_runner.py
- [T] tests/test_ladder_sim.py
- [T] tests/test_lgbm_bridge.py
- [T] tests/test_likelihoods.py
- [T] tests/test_lineup_opportunity.py
- [T] tests/test_live_assembly.py
- [T] tests/test_live_stack_pin.py
- [T] tests/test_market.py
- [T] tests/test_modal_schedules.py
- [T] tests/test_nested_cv.py
- [T] tests/test_nightly_drift.py
- [T] tests/test_novig_client.py
- [T] tests/test_novig_probe.py
- [T] tests/test_odds_board_lines.py
- [T] tests/test_odds_close.py
- [T] tests/test_odds_ledger.py
- [T] tests/test_offseason_workspace_boundary.py
- [T] tests/test_one_slip.py
- [T] tests/test_pa_aggregation_abc.py
- [T] tests/test_pa_k_baseline.py
- [T] tests/test_pa_k_runner.py
- [T] tests/test_pa_l3_refit.py
- [T] tests/test_pa_lgbm_comparison.py
- [T] tests/test_pa_lgbm_scaffold.py
- [T] tests/test_pa_research_guards.py
- [T] tests/test_pa_sim.py
- [T] tests/test_paid_clocks.py
- [T] tests/test_paired_uncertainty.py
- [T] tests/test_paper_ladder.py
- [T] tests/test_pipeline.py
- [T] tests/test_pitcher_features.py
- [T] tests/test_pitcher_rolling.py
- [T] tests/test_pregame_lineup_capture.py
- [T] tests/test_pregame_pa_adapter.py
- [T] tests/test_pregame_pa_checkpoint_pin.py
- [T] tests/test_pregame_pa_tracking.py
- [T] tests/test_prob_calibration.py
- [T] tests/test_projection_support.py
- [T] tests/test_properties.py
- [T] tests/test_real_bets.py
- [T] tests/test_reconstruction_audit_2023.py
- [T] tests/test_registries.py
- [T] tests/test_reliability.py
- [T] tests/test_repo_hygiene_check.py
- [T] tests/test_results_index.py
- [T] tests/test_retrosheet_cards.py
- [T] tests/test_review_verify.py
- [T] tests/test_rolling_anomaly_policy.py
- [T] tests/test_run_manifest.py
- [T] tests/test_safety_invariants.py
- [T] tests/test_sb_dependency_declarations.py
- [T] tests/test_select_2025_champion.py
- [T] tests/test_serving_gates.py
- [T] tests/test_settle_postponed.py
- [T] tests/test_settle_pregame.py
- [T] tests/test_sharp_quotes.py
- [T] tests/test_showdown.py
- [T] tests/test_skill_stats.py
- [T] tests/test_slate_shock_join.py
- [T] tests/test_slip_pick.py
- [T] tests/test_stabilization.py
- [T] tests/test_statcast.py
- [T] tests/test_statcast_refresh_exclude.py
- [T] tests/test_tbf.py
- [T] tests/test_tracking_registration_portable.py
- [T] tests/test_train.py
- [T] tests/test_training_policy_2023.py
- [T] tests/test_vif_cluster_reduction.py
- [T] tests/test_wf_comparison.py
- [T] tests/test_workload_spine.py
