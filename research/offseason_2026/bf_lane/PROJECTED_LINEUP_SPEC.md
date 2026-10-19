# PROJECTED-LINEUP SPEC — candidate registration (2026-10-19)

**Status: SPECIFIED-NOT-IMPLEMENTED.** Everything in this file is a
registration of a CANDIDATE scientific question. No code exists for it, no
adapter is wired, no run is scheduled, and nothing here has been executed.
Execution remains owner-gated (see `docs/PROJECT_STATE.md` — projected-batter
scoring authorization gates this lane).

## 1. Candidate scientific question (hypothesis)

**Hypothesis:** replacing the frozen scalar per-start PA probability `p_bar`
with a projected-lineup **matchup-mean p̄ per slot** (a per-slot p̄ computed
from the projected lineup batter mix facing the start's pitcher) improves
**paired count-RPS** against the scalar-p̄ arm on the registered assessment
cohort.

- Treatment arm: per-slot matchup-mean p̄ derived from
  `projected_lineups_variant_v2` (frozen; 549,296 PA-rows + 7,194 start-rows,
  pregame-state-v1 lineage).
- Comparator arm: frozen scalar p̄ (shrunk pitcher K rate, w=150 log5 form,
  kcount-integration I3b prior construction, pa-k pool strictly before
  game_date; sha256 `b91486525988da836303d55dab2718164e214bb6679a41225fcc4d79147bf4c4`
  — identical to the closed B0/B1 comparison's p_bar).
- Everything else held identical, per the count-lane comparison convention
  (`COUNT_REGISTRATION.md` in this directory): same BF PMFs, same count
  integration, same calibration/aggregation, same observed outcomes.

## 2. Pregame-availability checks needed (before any run)

- Verify `projected_lineups_variant_v2` covers every row of the registered
  assessment cohort (7,194 starts, 2024-07-01..2025-12-31, 272 slate dates).
- Identify any missing lineup dates: enumerate slate dates in the cohort with
  no projected-lineup coverage and report the count per availability state.
- These checks are read-only audits of frozen artifacts. They are specified,
  not implemented.

## 3. Missing-lineup fallback

- Where a start has no projected lineup, fill per the **accepted recipe:
  league-rate fill** (league-rate p̄ per slot in place of a lineup-derived
  value), consistent with the league-pool fallback convention used for
  `insufficient_history` and `career_debut` availability states.
- The fallback is part of the registered design, not an ad hoc repair; the
  filled rows must be identifiable in per-row output (availability state
  recorded, never silently accepted).

## 4. Comparator

- **Scalar-p̄ arm = the I1/C1 reference structure:** the frozen
  kcount-integration I1 arm (hazard BF PMF + binomial + scalar log5 p̄),
  equivalently the C1 point-exposure E[N] binomial comparator at the same
  scalar p̄. This is the same scalar-p̄ reference that anchored the closed
  B0/B1 count comparison.
- No new comparator is introduced; the contrast is treatment-vs-scalar only.

## 5. Multiplicity treatment

- **One primary paired count-RPS contrast** (treatment − scalar).
- **Holm m=1** (family of one), matching the B0/B1 registration convention.
- Slate-date bootstrap n=2000, seed 20261001, block-stratified, one shared
  draw stream, null-centered two-sided p — same machinery as
  `COUNT_REGISTRATION.md`.
- Any secondary/descriptive metrics (milestone Briers, log score, realized
  event rates) are descriptive only, never gated.

## 6. Expected row accounting

- Full registered window: **7,194 starts / 272 slate dates** — or the
  **preregistered subset with available projected lineups** if the
  availability check (section 2) finds uncovered rows.
- If a subset is used, the subset definition must be frozen BEFORE any run
  (count by availability state, slate dates listed), and the fallback rows
  (section 3) counted inside it, not excluded silently.
- Row counts are asserted at run time against the frozen table; any mismatch
  fails loud (same convention as the B0/B1 registration).

## 7. What is NOT yet specified (open design gaps)

1. **Adapter wiring:** the exact adapter from the projected-lineup parquet
   (549,296 PA-rows / 7,194 start-rows) to the PA-probability scorer —
   including key join order, cutoff/tz handling, and where the per-slot p̄
   enters the count integration — is NOT specified.
2. **Out-of-pair scoring capability:** whether the frozen H3 checkpoint can
   score projected (pitcher, batter) pairs that never occurred in the
   training data (unseen matchup cells) is UNVERIFIED. The frozen ladder was
   fit on realized pairs; projected lineups can produce pair cells with no
   training support. How (or whether) such cells are scored — and what
   fallback applies — is NOT specified.

Both gaps must be specified and reviewed in a NEW registration before any
execution. This file does not amend any existing registration.

## 8. Execution gating

- **SPECIFIED-NOT-IMPLEMENTED** applies to every section above.
- Execution requires: explicit owner authorization (projected-batter scoring
  authorization per `docs/PROJECT_STATE.md`), a new frozen registration
  resolving sections 2 and 7, and exact-head CI + review.
- No promotion, no production change; confirm_2025H2 and 2026 stay closed.
