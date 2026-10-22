# ACCEPTANCE CHECKLIST — M0 bounded repair verification
# Prepared by Chat 1 (builder) for independent delta verification
# after Chat 2 publishes the bounded repair batch.
# Each check has a unique identifier (M0RC-##) for unambiguous mapping.

## Population: pinned registration
- Card: card_m0_multiclass_2026-10-21.md (v3 + execution contract §11)
- Eval spec: eval_spec_count_aggregation_A_2026-10-20.md
- Frozen binary recipe: adapter.py (FEAT_H3, build_feature_frame)
- Registered count metrics: kcount_combiner.py (count_rps, milestone_brier)

## M0RC-01: Synthetic preflight — fresh subprocess
- Command: `python research/offseason_2026/pregame_pa_ext/m0_multiclass.py --verify-receipt-check`
- Requirement: succeeds in a fresh subprocess WITHOUT pytest import state
- Proof: exit code 0; receipt written to temporary storage; output artifacts exist
- Fail condition: ModuleNotFoundError, ImportError, or any exception
- Owner correction applied: the synthetic-input factory must be in
  importable support code beside the runner, NOT imported from a test
  module

## M0RC-02: Synthetic preflight — malformed receipt rejection
- Requirement: malformed or placeholder input identities are rejected
- Proof: a receipt with missing/empty consumed identities causes a
  fail-closed error; the failure record is preserved
- Negative test: verify the runner does NOT accept a receipt with
  "NOT_AVAILABLE" or empty consumed sections

## M0RC-03: No private-data fallback
- Requirement: the runner does not read from any undeclared real-data
  directory; all inputs come from the declared artifact_paths
- Proof: audit the import/loading paths in the runner; verify no
  hardcoded lake paths bypass the declared artifact_paths
- Correction applied: temporary output paths alone do not prove input
  isolation; the runner's data-loading boundaries must be observed

## M0RC-04: Receipt ordering — initial before computation
- Requirement: receipt_initial.json exists BEFORE any fitting or
  scoring computation begins (not merely before output files appear)
- Proof: mock or spy on the computation entry point; assert the
  receipt_initial write happens first
- Correction applied: "before output files appear" is insufficient;
  the initial receipt must precede the computation itself

## M0RC-05: Descriptive count-RPS — registered PMF construction
- Requirement: the runner emits count-RPS using the REGISTERED
  aggregation machinery (cycled prefix mean + Binomial mixture over
  the BF extension), verified against a small independently calculated
  example
- Correction applied: calling `kcount_combiner.count_rps` verifies the
  scoring function, not the PMF construction. The PMF construction must
  be separately verified against an independently calculated example.
- Evidence: per-start PMF from the registered machinery compared with
  a hand-computed PMF for a small case (e.g., n=3, uniform BF)

## M0RC-06: Descriptive count-RPS — RPS scoring correctness
- Requirement: the registered count_rps function produces correct
  results on a hand-verifiable example
- Proof: compare count_rps output against a manual CDF-squared
  calculation for a small PMF and known realized count

## M0RC-07: Descriptive count-RPS — correct population and probabilities
- Requirement: the count-RPS is computed from the M0 multiclass model's
  implied K probabilities (P(class=0)), NOT from the H3-raw or L5 arm
  probabilities, UNLESS the pinned registration explicitly requires
  those comparisons
- Pinned card section: card_m0_multiclass_2026-10-21.md, "Count-RPS
  becomes DESCRIPTIVE" — states "multi-class-implied K probability vs
  the frozen binary K probability through the registered aggregation"
- Frozen aggregation contract: kcount_combiner.py declares
  "conditional independence of PAs declared as a v1 approximation" and
  uses Binom(k; n, p_bar)
- RESOLVED: the pinned card DOES specify the probabilities — they are
  the multi-class model's implied K probabilities (P(class=0)), NOT
  the H3-raw or L5 arm probabilities. The comparator is the frozen
  binary K probability (from the preserved ledger's p_h3_raw). No
  ambiguity to report.
- Correction applied: do not silently substitute H3/L5 probabilities
  for M0's probabilities

## M0RC-08: Frozen dev start-key set — exact identity
- Requirement: the evaluation population matches the frozen dev
  start-key set (sha256 618e8e75...), verified by exact key-set
  comparison (not a count)
- Proof: compute the canonical hash of the evaluation start keys and
  compare with the published hash
- Correction applied: verify exact identity, uniqueness, and
  exclusions — not merely a count of 4,823

## M0RC-09: Temporal safety — registered as-of rule
- Requirement: feature construction uses the registered availability
  rule (strictly-prior as-of, same as the frozen recipe)
- Correction applied: a blanket `src_date < game_date` assertion may
  incorrectly reject legitimately available same-day pregame
  information. The frozen recipe's convention is that the source date
  must be BEFORE the forecast date (src_date < game_date), which
  already excludes same-day rows. This IS the registered protocol —
  do not change it, but verify it is applied correctly (same-day rows
  are excluded because their source date equals the forecast date,
  not because of a separate same-day exclusion rule)

## M0RC-10: Block isolation
- Requirement: confirm_2025H2 rows never enter training or evaluation;
  changing their outcomes does not change development results
- Proof: synthetic fixture with confirm-block rows; flip their
  outcomes; verify dev results are unchanged

## M0RC-11: Five-class probability output
- Requirement: the runner produces 5-class probability vectors per
  evaluated row: correctly ordered (matching CLASS_NAMES), all finite,
  in [0, 1], summing to 1
- Proof: assert shape, finiteness, bounds, and normalization on the
  runner's actual output

## M0RC-12: Execution CLI dispatch
- Requirement: the CLI dispatches to the M0 runner (NOT to
  count_agg_eval, NOT to batt_recency, NOT to another experiment's
  runner) when the authorization flag is passed
- Proof: verify the dispatch target by inspecting the call graph or
  testing with a mock
- Correction applied: do not blindly wire main() to
  run_count_agg_eval(); first verify the intended callable is
  run_m0() or the equivalent M0 function

## M0RC-13: Refusal behavior
- Requirement: the CLI refuses without the authorization flag
  (exit != 0, refusal message)
- Proof: test the CLI without the flag and verify the refusal
- Correction applied: test absent authorization flags, invalid inputs,
  and existing output destinations

## M0RC-14: Unique checklist identifiers
- All checks use M0RC-## identifiers for unambiguous mapping from
  findings to tests
- No duplicate or ambiguous identifiers
