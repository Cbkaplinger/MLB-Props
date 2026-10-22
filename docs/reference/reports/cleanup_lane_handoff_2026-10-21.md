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

## 5. Open-PR temporary exception (recorded 2026-10-21, later)

The lane currently has three open PRs (#33 DECISIONS consolidation, #35
reports index, #36 this handoff) against the two-PR cap in the PROPOSED PR
rules. Recorded as a **temporary exception requiring reconciliation, not a
merge justification**: #33 and #35 are completed deliverables awaiting
review/merge; #36 carries the handoff. No further cleanup PRs open until this
reconciles to the cap.

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

## 7. Closure condition

The temporary cleanup lane closes when: (a) #33 and #35 are reviewed and
merged; (b) the owner accepts this handoff (including the disposition map,
residual risks, and the open-PR exception record); and (c) no new cleanup
scope is assigned. Until then the lane continues on assigned, bounded
deliverables only.
