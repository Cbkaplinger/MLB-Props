# WF comparison contract - frozen 2026-10-09 (pre-fit)

One chronological walk-forward development comparison, four fixed arms.
Authorization: owner message 2026-10-09 (sections A-F quoted there).
NO promotion, NO production change, NO commit/push without a further
instruction. Label: **chronological OOF development evidence** - not a
fresh holdout (2024 outcomes informed the frozen ensemble's selection,
and the WF design itself was chosen after viewing bridge diagnostics).

## A. Bridge preservation record

- Canonical bridge diagnostic archived at
  `C:\Users\ckaplinger\MLB-Props-Research\lgbm-bridge-2024\`
  (bridge_manifest.json, predictions.csv, pmfs.parquet, eval_report.md,
  eval_metrics.json, eval_slices.json). Three scored-run attempts were
  written to that directory sequentially; each was preserved in the
  backlog receipt before the next overwrote the directory. The numbers
  were identical across attempts; only a safety boolean was relabeled.
- Matched-population limitation (recorded): n=1,413 scored rows are the
  intersection of I3b 2024 eval rows with the PA>=9 pipeline frame.
  64 eligible I3b rows were excluded because the frozen source cohort
  removes starts with eventual PA<9 (outcome-conditioned coverage).
  The bridge claim is therefore scoped to its matched, predominantly
  PA>=9 population. It does NOT generalize to debuts or short outings.
- Amendment timing (recorded, relative to viewing results):
  1. Reproduction tolerance 1e-8 -> 1e-6: BEFORE any bridge result was
     viewed. The first run aborted at the reproduction assert itself
     (no scores existed yet); the drift measured 5.3e-8 (multithread)
     and 8.4e-8 (single-thread) against the saved transfer-run PMFs.
  2. RPS-safety tolerance correction (spec-error fix, code + contract):
     AFTER the first scored result was viewed. The original wording
     ("challenger-reference full-window paired CI lower bound
     >= -0.0005") was a spec error: it fails ANY improvement larger
     than the floor. The corrected rule (fail only if ci_lo95 >
     +0.0005) was frozen before the final canonical evaluation. The
     original and amended wording are both preserved in
     lgbm-bridge-contract-2026-10-09.md. No numbers changed across
     attempts (verified: paired CI identical to 12 significant digits).
- No rescoring of the bridge will be performed to improve the
  historical claim. I3b remains retained. The bridge result is a
  selection-aware retrospective diagnostic only.

## B. Corrected population and denominator contract

### Completed-PA denominator (reconciled)

- **Chosen definition:** production `plate_appearances()`
  (src/Python/statcast.py) - NON_PA_EVENTS are filtered BEFORE terminal
  row selection. This counts an AB that ends on a baserunning-only
  event (caught stealing, pickoff) after a walk as a completed PA:
  the batter did face the pitcher. Baseball-correct.
- **Reconciliation vs canonical research BF** (from executed audits):
  - 2023 (n=20,628 pitcher-games): K numerator agreement 100.000%;
    PA mismatch 1.314% ... see bridge G4: 2024 (n matched to I3b
    starter rows): K 100.000%, all-pitcher PA mismatch 1.515%,
    starter-only 4.081%. Mechanism: research `bf_table_canonical`
    (run_corrected_history_2023.py:161-182) filters AFTER terminal
    selection and DROPS ABs ending on baserunning-only events; every
    mismatch is prod = research + 1 PA (one +2 case in 2023).
- **Target correction from the legacy denominator (documented):** the
  legacy frozen models (mono72 054127, final58 054126) were trained on
  K / production-PA (the same completed-PA definition chosen here).
  The WF lineage therefore does NOT change the denominator relative to
  the legacy models - it changes it relative to the RESEARCH BF used
  by the I3b workload layer (+1 PA on 1.5-4.1% of rows, documented).
  The real correction in this lane is the POPULATION (below).
  Never "correct" via realized-PA ratios (outcome leakage).

### Outcome-independent starter feature spine (short outings retained)

- Rebuild the production feature pipeline (L1 games -> L2 rolling ->
  L3 training) for seasons 2023+2024 with `min_batters_faced=0`
  instead of the frozen production 9. All outputs are redirected to
  `C:\Users\ckaplinger\MLB-Props-Research\wf_spine_2024\`; the parked
  repo's data/processed artifacts are NEVER overwritten. Production
  code files are not edited; `games.run(..., min_batters_faced=0)` is
  a public parameter.
- Retaining short outings at L1 automatically preserves them in the
  historical features of later starts (rolling windows see every prior
  appearance). This satisfies "preserve prior short outings in
  historical features too".
- **No primary PA>=9 filter** at any stage of this lane. The scored
  population is defined by the I3b 2024 eval rows (all starters),
  intersected with feature availability of the unfiltered spine.
- Debut / sparse-history cases use the pipeline's existing league
  fallbacks unchanged; coverage is verified and reported by slice
  (debut, sparse history, short outings <9 PA).
- Feature sets: the exact recovered 72-feature (mono72) and
  58-feature (final58) sidecar lists, unchanged. No feature selection,
  no new features.

## C. Chronological fitting (frozen before any fit)

- Windows (verified against the existing machinery
  `models/Strikeout-Model/research/walkforward_stack_backtest.py:55`):
  | window | scored block |
  |---|---|
  | wf_2024_apr_may | 2024-04-01 .. 2024-06-01 |
  | wf_2024_jun_jul | 2024-06-01 .. 2024-08-01 |
  | wf_2024_aug_sep | 2024-08-01 .. 2025-01-01 (season end) |
- Per window: training rows = game_date STRICTLY before window start
  (2023 full season + prior 2024 rows). Training rows are whole games;
  no game is split across train/score.
- **Early stopping uses an earlier internal validation block:** the
  LAST 15% (chronological) of the training rows - entirely before the
  scored block (verified `_chrono_val_split` semantics). Every
  early-stopping label precedes the scored block.
- **Frozen hyperparameters** (the frozen baseline defaults used by the
  legacy production lineage; NO tuning, NO Optuna, NO sweep):
  n_estimators 5000, learning_rate 0.03, num_leaves 31,
  min_child_samples 50, subsample 0.8, colsample_bytree 0.7,
  reg_alpha 0.1, reg_lambda 2.0, random_state 42, early_stopping 200
  on the internal val block. Tree count is selected by early stopping
  on the internal val block ONLY - never by scored-block performance;
  no scored-block tree count is reused.
- Arm A (72 features) adds the legacy monotone constraints
  (`monotone_constraints_method: "advanced"`, signs from
  `train._feature_constraints`); arm B (58 features) unconstrained.
  Target = K / completed-PA (production definition), B.0-1.
- Blend weights FIXED at 0.60 (A) + 0.40 (B), inherited from the
  frozen ensemble. No weight search.
- No 2025/2026 reads. No recalibration.

## D. Four fixed arms (common scored rows)

| arm | rate input | workload/count layer |
|---|---|---|
| REF | canonical log5 p* (I3b, unchanged) | identical I3b ext60 BF PMFs + combiner |
| A | newly fitted 72-feature monotone LGBM | identical |
| B | newly fitted 58-feature LGBM | identical |
| BLEND | fixed 0.60*A + 0.40*B (clip [0,1]) | identical |

- Common scored rows = I3b 2024 eval rows (all starters, 4/15..9/30
  2024) within the three scored blocks, intersected with unfiltered
  spine feature availability. **Frozen missing-prediction behavior:**
  a scored row missing spine features is EXCLUDED from ALL arms
  (paired comparability) and counted in the coverage report; REF is
  additionally reported over the FULL I3b eval population.
- Coverage over the entire eligible population is reported per window
  and overall, with reason counts for any exclusions.

## E. Frozen evaluation (declared before execution)

- **Primary comparisons (3, family):** A vs REF, B vs REF, BLEND vs
  REF - paired count-RPS slate-date bootstrap (2,000 resamples, seed
  20261001). **Multiplicity: Holm step-down at family alpha 0.05**
  across the 3 comparisons. Unadjusted 95% CIs reported alongside.
- **Family-level gate (development, not promotion):** BLEND beats REF
  with Holm-adjusted significance AND the degradation-safety rule
  holds for all three arms: fail only if the paired CI's lower bound
  exceeds +0.0005 (corrected rule from the bridge contract).
- Numerical safety tolerances (same as bridge contract, corrected):
  xK |mean bias| delta <= 0.05; xK MAE delta <= 0.02; floor rows
  challenger <= reference + 0; PIT tail bins <= 1.5x expected;
  milestone Brier max increase <= 0.0002; PMF mass |sum-1| <= 1e-9.
- Metrics reported per arm: count-RPS, log score, xK bias/MAE,
  milestone Brier (ge6/ge8/ge10/ge12), PIT, floor violations, xK.
- **Slices (permanent set + short outings, now non-empty):** april,
  september, career_debut, season_debut, sparse_history,
  short_outing_lt9 (current-game eventual PA < 9 - the previously
  excluded population), upper_milestone_ge12. Slice results are
  descriptive (small n expected); no slice-based selection.
- **No automatic promotion.** A pass opens the clean PA-level
  classifier lane as the next experiment; it does not promote any
  rate model into the research default.

## F. Execution gates

1. Focused correctness + leakage tests (label-precedes-window,
   chronological val split, monotone constraints only on arm A,
   missing-row exclusion behavior, blend weights fixed).
2. Readiness check: spine row counts (2023+2024, all starters),
   feature completeness for both sets, coverage >= 95% of I3b eval
   rows (with the unfiltered spine this is expected ~100%; if the
   spine build itself fails or coverage < 95%, STOP with the specific
   blocker - do not relax the contract).
3. Run the predeclared WF experiment ONCE.
4. Return: contract, tests, run receipts, coverage, results, one next
   action.

## Provenance

- Unfiltered spine: built in-process from tracked pipeline code
  (games.run / rolling.run / training.run) with min_batters_faced=0,
  seasons 2023+2024, outputs under
  `C:\Users\ckaplinger\MLB-Props-Research\wf_spine_2024\`.
- I3b ext60 BF PMFs: rebuilt via the bridge runner's verified
  machinery (reference reproduction assert vs the saved transfer run).
- Frozen artifact hashes, feature sidecars, and the corrected safety
  tolerances: see lgbm-bridge-contract-2026-10-09.md (unchanged).

## Checkpoint amendments (2026-10-09, post-run, recorded at owner instruction)

- Equivalence NOT established: crossing-zero CIs mean superiority was not
  demonstrated, not that arms are equivalent.
- Selection-bias causality NOT isolated: the WF changed fitted models,
  population, and fitting policy together vs the bridge.
- Denominator correction NOT implemented: population eligibility was
  corrected (short outings retained); the target remained production PA.
  The reconciled completed-PA definition must be resolved and tested
  before PA-lane fitting.
- A/BLEND xK safety-cap breaches (improvement side) are mechanical
  contract results under the frozen two-sided tolerance; gates are not
  revised retrospectively.
