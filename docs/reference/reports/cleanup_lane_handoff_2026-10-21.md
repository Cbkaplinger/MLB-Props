# Cleanup lane handoff - 2026-10-21 (Chat 3; residual risks + closure condition)

Point-in-time handoff for the temporary cleanup lane. Coverage record lives in
`cleanup_execution_plan_2026-10-16.md` + the session registry; this file is
the handoff, not a new inventory.

## 1. Canonical entry points (all resolve; verified)

- Work state: `docs/EXECUTION_BACKLOG.md` (Chat 1 sole-writer) -> `AGENTS.md`
- Current research state: `docs/reference/current_state_2026-10-16.md`
- Operating commands: `production/README.md` -> `INDEX.md` -> `RUNBOOK.md`
- Decisions: `docs/DECISIONS.md` (register first, historical quotes below)
- Architecture/roadmap: `docs/adr/` (PROPOSED-* labeled), `docs/ROADMAP.md`
- Navigation rules: `docs/reference/README.md` (authoritative vs historical +
  frozen-artifact hard limit), `docs/diagrams/00-index.md`

## 2. Stale references

- Tracked md links: 96 checked, 2 broken found and repaired (#26); the
  re-check after folder passes found 0 new breaks.
- One dated supersession label added (`PROPOSED_COMMITS.md` NOT-pushed status).
- Diagrams: 0 stale file references (17 paths verified); flows 05/06 validated
  claim-level; 01-04 claim-depth complete.

## 3. Audit findings lacking dispositions (the map)

| Finding (source audit) | Current disposition |
|---|---|
| Dead-code S-C1 modules (`ballpark`, `batter_features`, `batter_rolling`, `identity`, `reliability`, `skill_stats`) | **DEFERRED - owner ruling outstanding** (deletion quarantine ledger) |
| S-B dependency tiers | **FIXED** - merged via PR #17 (tiers approved) |
| Dependency reproducibility: floating resolution (pyarrow 24<->25), streamlit/starlette conflict, local-env assumptions | **PARTIALLY ADDRESSED** (pyarrow restored; streamlit conflict documented pre-existing); **needs current closure evidence before reassignment** |
| Data-contract inventory: externally produced inputs; uneven validation coverage | **OPEN** - the M0 executable-contract work (PR #34 lineage) addresses new runs; older edges unaudited |
| Shared-utility consolidation plan | **DEFERRED** - frozen research runners prohibited from consolidation |
| Hygiene automation design | **PARTIALLY FIXED** (advisory checker merged, PR #12); automation design deferred |
| O-3 settlement exit-code contract | **PARTIALLY ADDRESSED** - characterization tests merged (PR #14); contract adoption pending |
| T6 prereg-draft dispositions | **PARTIALLY FIXED** - banners merged (PR #15); deeper disposition pending |
| Results dashboard diagnostics | **DEFERRED** - dashboard parked |
| Backlog 512 KB bloat | **SCHEDULED** - split approved in principle (PR #30 lineage); Chat 1 executes |

## 4. Residual risks (handed to the owner/architect)

1. **Governance publication pending** - the trailing-fixer workflow operates
   ahead of the canonical role map; ADR/PRD published here as PROPOSED only.
2. **M0 correctness** - Chat 2's repair batch is in review; execution remains
   owner-gated; no independent acceptance of the repair delta yet.
3. **Reproducibility unproven** - no accepted result has been reproduced from a
   clean environment; dependency-audit findings need closure evidence.
4. **Reading coverage (reconciled 2026-10-21, exact - supersedes earlier
   approximations):** 297 unique fully read = **295 in-scope read** + 2
   deferred-read (COUNT_EVAL_COMMANDS.md, owner-assigned status fix;
   scripts/review_verify.py - PR #25 touched-path exclusion). In-scope 692 =
   295 read + **397 remaining** (exact set difference). Deferred 290 = 2 read
   + 288 unread. Partition identity: 295 + 397 + 2 + 288 = 982; no
   double-count. The read lane is STOPPED per the owner's scope cut; remaining
   files are classified only.
5. **Agent efficiency unmeasured** - the builder/trailing-fixer arrangement is
   a hypothesis; the delivery measures in the PROPOSED PRD are the instrument.

## 5. Open-PR status against the CANONICAL cap (corrected 2026-10-21, later)

- **Operative rule: three open PRs repository-wide** (the previously recorded
  canonical limit). The two-PR cap quoted earlier lives in PROPOSED rules that
  are NOT operative; it is identified here separately as a proposal only.
- **Recorded against the canonical rule: FOUR open PRs** (#33 DECISIONS
  consolidation, #34 M0 research, #35 reports index, #36 this handoff) - one
  over the canonical limit. **Recording this exception does not authorize
  exceeding it.** No further cleanup PRs open until the count reconciles.
- Reconciliation path: #33 and #35 are completed deliverables awaiting
  review/merge; #36 carries this handoff (disposition below).

## 6. Current gate-status pointer (kept current; not a re-audit)

- The M0 gate report corrections (test-total inconsistency; preflight
  dependency boundary as an execution-readiness blocker; the descriptive-count
  obligation to be resolved against the registered card language; CLI wiring
  ambiguity; repair-authorship attribution) are **research-lane items** owned
  by Chat 2 (bounded repair) and Chat 1 (independent closure check) per the
  architect's assignment - recorded here as the current risks, not cleaned up
  by this lane.
- Real-data-input identities remain UNVERIFIED (implemented and
  synthetic-exercised assertions only) - no claim of real-input verification
  is made anywhere in this lane's records.

## 6b. Folder 3-6 classification evidence (attached 2026-10-21; per owner instruction)

**Repository SHA the classification ran against:** `3637ed1bbc08dd7a5101da126d0ff899f83848b5` (origin/main at run time).

**Command:** one-pass `git grep -F -f <candidate-basenames>` over `*.py *.md *.ps1 *.json *.yml *.toml` at that SHA (278 candidate .py files across `production/ops/market_research`, `tests`, `models`, `scripts`; basenames deduplicated into the pattern file), cross-referenced against the session registry and the gc skill outputs (`duplicate_finder` 0 exact dupes; `reference_graph` 488 py / 73 entry hints; `find_doc_claims` 4,512 claims).

**Original assignment reference (depth):** the owner's folder directive ordered "market_research, tests and models come after the docs set is done, and only as classify-and-propose tasks," with the folder deliverable defined as "a short table of keep, archive, fix, and propose-delete" - i.e. classification, not full implementation-correctness reads, for folders 3-6. Folders 1-2 (docs/reference; docs/research + docs/archive) were assigned full reads and were fully read.

**Narrow conclusion:** "No deletion/archive candidates identified by the consumer-reference review; unread files were not audited for implementation correctness." Zero-inbound exceptions: `tests/test_count_agg_eval.py` and `tests/test_count_aggregation_exact.py` - both files of the ACTIVE research lane (PR #34 lineage, M0/decision-flip), excluded from cleanup scope.

**Registry reconciliation (the unread-count discrepancy, from the existing registry - census not restarted):** the intermediate figures (176 -> 194 -> 199 -> 204 -> 218 -> 235 -> 239 -> 275/417) were running states of one evolving registry, not independent counts. Three concrete events explain every change: (1) reads added across passes (governance family +5; OPS5 +14; OPS-CORE +4; READ5 +5; folder-1/2 +58); (2) a registration gap - 12 daily-chain scripts fully read but not registered until the fix (registered as OPS-CORE); (3) one pollution event - 110 relative-path keys added by a stripped `ls-tree` prefix, then removed. Current verified partition: **295 in-scope read + 397 in-scope remaining + 2 deferred-read + 288 deferred-unread = 982** (in-scope 692 + deferred 290; disjoint and complete).

**Unfinished assigned scope (identified, not redefined as complete):** (a) `docs/PROJECT_STORY.md` (due 2026-11-21; to be assembled from PAPER_NOTES.md, the statistical audit, and this decision log); (b) `docs/diagrams` index reduction to one table + retiring restating diagrams (due 2026-11-21); (c) archiving the superseded reports marked in the reports index (pending owner approval - the canonical register cites those paths). These remain assigned to this lane and are NOT complete.

## 6c. Six-folder completion map (2026-10-21; requirement vs performed vs unmet)

Cites the assignment establishing depth per folder: the living-documents
consolidation order ("market_research, tests and models come after the docs
set is done, and only as classify-and-propose tasks") plus the folder
directive ("for each folder, produce one deliverable: a short table of keep,
archive, fix, and propose-delete"). Folders 1-2 carried full reads; folders
3-6 carried classification with consumer evidence.

| Folder | Original requirement | Work performed | Evidence | Unmet obligations |
|---|---|---|---|---|
| 1. `docs/reference` | full read + keep/archive/fix/propose-delete table | 36/36 living-standards docs + reports survey fully read; links validated (0 broken, 0 missing paths); 1 fix (PROPOSED_COMMITS supersession label); navigation rules added to reference README | reference README section; sweep records in cleanup_execution_plan | none |
| 2. `docs/research` + `docs/archive` | full read + table | 22/22 files fully read (3,154 lines); 0 broken references; 0 fixes needed | folder-2 table on PR #30 thread; registry | none |
| 3. `production/ops/market_research` | classify-and-propose | ~85 scripts classified by one-pass consumer grep + gc outputs; every script referenced by its dated report | classification evidence (section 6b) | deep reads remain OUTSIDE the assignment (explicitly classify-and-propose) |
| 4. `tests` | classify-and-propose | 96 py files classified; CI-consumed; 2 zero-inbound files belong to active research (PR #34), excluded | classification evidence | none within assignment |
| 5. `models` | classify-and-propose | 70 py files classified; dated lineage + trainers, all cited | classification evidence | none within assignment |
| 6. `scripts` + dotfiles | full read (batch A) + classification | 28 scripts + 12 dotfiles fully read; both prune utilities verified distinct; intentional mirror documented | batch A records | none |

**Unmet obligations from the six-folder assignment: none.** Open items from
the LARGER living-documents assignment, with explicit dispositions (2026-10-21):

- `PROJECT_STORY.md`: **DELIVERED as a PROPOSED draft in this PR** (evidence-linked
  narrative; dated M0 status - "NOT READY" as of 2026-10-21, to be re-dated as
  implementation advances so the narrative does not go stale).
- **Diagrams index reduction + restating-diagram retirement: DEFERRED -
  approval-gated.** Navigation review recorded in 00-index (09 retirement
  candidate subsumed by 13; 07/12 consolidation direction); retirement requires
  semantic + consumer checks and is NOT a prerequisite for M0 progress.
- **Superseded-reports archive: OWNER-BLOCKED PROPOSAL** - no moves or
  deletions without approval; the reports index carries the candidate marks.
- The read-lane remains STOPPED; un-read files are classified only (recorded
  in the registry, not silently complete).

## 7. Lane status and closure condition

**Lane status: no implementation blockers; closure awaits review/merge of
#33/#35 and owner acceptance of this handoff.**

**#36 disposition (explicit): review and merge as PROPOSED documentation.**
This handoff is documentation of record for the cleanup lane; adopting the
PROPOSED ADR/PRD decisions inside it remains a separate owner/architect act.
Merging #36 closes the lane's documentation deliverable without activating
any proposed rule or authorizing any execution.

## 8. Closure condition

The temporary cleanup lane closes when: (a) #33 and #35 are reviewed and
merged; (b) the owner accepts this handoff (including the disposition map,
residual risks, the open-PR record, and #36's review-and-merge disposition);
and (c) no new cleanup scope is assigned. Until then the lane continues on
assigned, bounded deliverables only.
