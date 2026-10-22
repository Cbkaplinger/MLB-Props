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
