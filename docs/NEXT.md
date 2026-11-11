# NEXT - current action

Owner: architect. Updated 2026-11-11. Chat 3 closed; cleanup integrated.
Chat 1 active: parity lanes and the paired comparison are CLOSED
(reproduced bit-exactly); the baseline K-PMF diagnostic is implemented
and synthetic-tested; the proposed execution packet awaits an owner
decision. ROLES_REV 2026-10-28-r1. Read docs/roles/README.md and your
card. EXECUTION_BACKLOG remains the single queue.

## Ablation baseline decision (owner, 2026-11-09)

- Control: registered 8-feature multinomial plus pooled W0.
- Challenger: registered 12-feature platoon recipe; no production promotion
  or fresh-validation claim.
- Evaluation uses per-PA multiclass log loss, per-start means, paired
  slate-date bootstrap, and the K-count RPS guard; calibration remains absent.
- Full recipe and verified results: `docs/EXECUTION_BACKLOG.md` and
  `docs/reference/reports/experiment_impact_ledger_2026-10-22.md`.

## Prior completed milestones (this lane)

All VERIFIED; full records in `docs/EXECUTION_BACKLOG.md` and
`docs/reference/reports/experiment_impact_ledger_2026-10-22.md`:
workload w0v1 (pooled W0 favored), historical starter-outcome derivation
(9,714 starts), history-sensitivity scorecard, Ref0-vs-Ref1, Stage-A
reconciliation (implemented; real run authorization-gated), binary-K /
LGBM / platoon lanes (control retained / retained / challenger favored),
lane stack integrated at `2ca8aef`. Paired comparison reproduced
bit-exactly (checkpoint `7e6d03c`; every artifact byte-identical,
receipt_final = `b1b91357...224ba`); harness-to-market bridge
implemented and merged (PR #81).

## Current action: market-benchmark seam built (2026-11-11)

- **Implemented on this branch** (market_benchmark_seam.py): the two
  missing seams between the registered market-eval lane
  (market_eval_k.py) and today's harness outputs - (A) harness keyed
  24-bucket PMFs + assessment-derived observed K + declared eligible
  cohort (hash-checked) + declared start dates -> the registered
  market-eval model frame (block via ad.add_block; protected/unknown
  blocks refuse); (B) per-book two-sided de-vig probabilities +
  leave-target-book-out consensus (median over OTHER books at the
  SAME line; >= 2 other books; unavailable recorded, never filled) +
  all-book consensus (registered construction reused unchanged).
  7 synthetic tests green (hand de-vig, LTBO self-exclusion,
  unavailable accounting, cohort/date gates incl. protected block).
  Closing quotes remain benchmark-only. NOT RUN on real odds;
  execution needs the registered market-eval gate + delegated owner
  order.
- Baseline K-PMF diagnostic: executed once (execution of record in
  backlog); delta-decomposition + completed concentration analysis
  delivered on PR #83 comments.

## Current action: baseline K-PMF diagnostic built (2026-11-11)

- **Implemented on this branch** (`count_pmf_diagnostic.py`): thin
  keyed glue over the existing registered scorers (count_logscore with
  1e-12 clip - POSITIVE log loss confirmed from code; summed-CDF RPS;
  model_p_over at the eight canonical half-lines; check_pmf; strict
  bucket labels). Exact key equality with both-direction reporting;
  explicit accounting; equal weight per matched start; K >= 23 =
  declared overflow; fixed declared reliability bins [0,.1)...[.9,1];
  per-arm + paired challenger-minus-control deltas.
- **Label source established:** `prepare_assessment_2025H1.py`
  preserves every completed PA of requested starters, so
  `assessment_2025H1_v1.parquet` supplies complete full-start realized
  K (registered derivation: class_label == 0 count).
## Current action: K-PMF diagnostic - cohort contract amended (2026-11-11)

- First authorized execution (HEAD `a830dda`) hit the registered
  exact-key gate: the assessment covers all 2,532 requested 2025H1
  starts vs the 2,509-start eligible forecast cohort
  (`missing_from_observed=0; missing_from_forecast=23`). Execution of
  record; no output written; no retry.
- **Cohort contract amendment (this PR):** explicit `--cohort-keys` +
  `--expected-cohort-hash` (registered `bk._cohort_hash`); forecast ==
  cohort exactly; observations restricted to the cohort must cover it
  exactly; observed-only starts outside the cohort = declared
  exclusions with full key lists. Tests prove exclusions are exactly
  the cohort set difference (key identity, not counts). 16 diagnostic
  tests green (59 with trio + bridge).
- Revised execution packet (adds `--cohort-keys` + `--expected-cohort-
  hash`, registered eligible cohort `f77d7a66...`) in backlog FORWARD.
  Input byte hashes are PROCEDURAL preflight; the runner enforces the
  cohort hash + structural gates. NOT RUN; fresh owner authorization
  required for the one rerun.
