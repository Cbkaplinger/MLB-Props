# docs/reference — specs, briefs, and dated evidence (read-only contracts)

## Purpose

The paper's and the agents' source of truth for HOW things must be built.
Nothing here is a work queue — approvals live only in
`docs/EXECUTION_BACKLOG.md`. If this directory disagrees with the Snapshot,
the Snapshot wins.

## Start here (in order)

1. `opencode_handoff.md` — coworker briefing (replay era). Paste into a new session.
2. `oddsapi_replay_architecture.md` — frozen-model replay spec (freeze/work/product).
3. `golden_metrics.md` — canonical numbers + JSON sources. Cite, do not recompute.
4. `experiment_sop.md` — challenger discipline (§8: same-subset, nested-hole, envelopes, juiced book rule).
5. `repo_canonical_map.md` — canonical vs archive surfaces.

## Dated evidence (`reports/`)

Point-in-time verdicts (juiced ledger, selection, audits, gates, cloud).
Each says what it measured and what followed. History, not instructions.

## Standing constraints

- `research_assistant_instructions.md` — leakage-safe research rules.
- Free-only forever; no retrains; model frozen (reopen: new data/offseason).

## Authoritative vs historical (navigation rule, 2026-10-20 sweep)

- **Current guidance (read these first, trust these):** the five "Start here"
  docs above, `current_state_2026-10-16.md` (research model-stack state),
  `pr_workflow.md`, `AGENTS_ROLES.md` (in `docs/`), `repo_canonical_map.md`.
- **Historical evidence (cite, do not obey):** everything under `reports/`
  with a date in its name. Dated reports describe what was true at their
  timestamp; later merged work supersedes individual claims. When a dated
  report conflicts with a living doc above on a current-state claim, the
  living doc wins and the conflict should be labeled in the living doc (not
  by editing the dated report).
- **Hard limit on that rule:** living docs NEVER override frozen
  registrations, pre-registration protocols (experiment SOP), frozen
  packets, registered pins/hashes, or historical RESULTS. Those are
  immutable evidence; where prose and a frozen artifact disagree, the
  frozen artifact is authoritative and the prose gets a supersession
  label (precedent: the freeze JSON status string left byte-identical,
  supersession recorded in prose).
- The 2026-10-16 census/sweep cluster (`*_2026-10-16.md`, ~20 files) is
  point-in-time evidence for that date's repository state; use it as a map of
  what existed then, not as current counts.
