# DRAFT prereg — BF hazard training-policy comparison (2026-10-06)

> **Status: DRAFT.** Not frozen, not authorized, not executed. Frozen prereg
> text is authored from this draft only after owner authorization, then
> hashed into the run manifest like every prior lane. Origin: owner order
> 2026-10-06 ("design a training-policy comparison before executing the
> interaction hazard"); audit evidence in
> `MLB-Props-Research\workload-bfdist-failure-audit-20261006\`.

## Question

Does the discrete termination hazard improve when fitted on **expanding,
strictly-pre-origin** training data instead of the frozen pre-04-15
window — holding features, support, loss, regularization, probability
conversion, and evaluation rows identical?

## Arms

| Arm | Training rows | Eval rows |
| --- | --- | --- |
| **A (reference)** | Frozen: all retained starts with `game_date < 2023-04-15` (n=414, 3 short outings) — identical for every origin, exactly as in `workload-bfdist-20261006_183844` | unchanged |
| **B (challenger)** | Expanding: all retained starts with `game_date < origin_ts` (no eval-window exclusion) | unchanged |

**Eval rows are identical to the frozen diagnostic and between arms:**
origin windows [04-15, 06-30] (n=2,046, labeled **Apr-Jun**), Jul
(n=734), Aug (n=822), Sep+10-01 (n=844). No evaluation dates are changed
or repaired. Row-identity hash required across arms and vs the audited run.

**April coincidence:** for origin 2023-04-15 the permissible strictly-prior
data are identical for both arms (pre-04-15 only). The April arm is fit
once and reported once for both arms; arms are asserted identical
(same features → same fit) at run time.

**Exact arm-B training sets (expected counts, enforced fail-loud):**

| Origin | Arm-B train rows | Arm-B train short events (BF<9) |
| --- | ---: | ---: |
| 2023-04-15 | 414 (= arm A) | 3 |
| 2023-07-01 | 2,460 (414 + Apr-Jun 2,046) | 72 (3 + 69) |
| 2023-08-01 | 3,194 (+ Jul 734) | 102 (+30) |
| 2023-09-01 | 4,016 (+ Aug 822) | 140 (+38) |

Counts derive from the audited run's per-origin eval counts/events; the
runner recomputes them and raises on any mismatch with the eval-window
row-identity hashes.

## Information contract (unchanged, both arms)

- Features: `CHALLENGER_FEATURES` exactly as frozen; strictly-prior spine
  histories; team rates with the existing prior-year fallback rules.
- Support/overflow: BF 1..36 + overflow bucket; `hazard_to_pmf` unchanged.
- Model: `fit_hazard` unchanged (L2 logistic, C=1.0, index one-hots,
  5,000 max iter). Probability conversion unchanged.
- Preprocessing: training-only median imputation + standardization, fitted
  **per origin per arm** on that fit's own rows only (`_fit_preprocess`).
- History/label cutoff: every training row's game_date < origin_ts;
  enforced by an explicit assertion over the training frame before fit.
- **No evaluation-window outcomes enter that origin's own fit** (training
  is strictly pre-origin by construction in both arms).
- Empirical baseline: unchanged frozen recipe (train-only Laplace). For
  arm B the baseline PMF is optionally re-fit on arm-B training counts as
  a **secondary reference only**; primary comparison is arm B vs arm A.

## Exposure disclosure (required in the report)

1. Arm B's Jul/Aug/Sep fits **consume the Apr-Jun rows that were scored
   under the 04-15 eval window** in the frozen diagnostic and in this run.
   Chronologically valid (strictly prior to those origins; no temporal
   leakage), but the Apr-Jun window becomes **development data for the
   Jul-Sep origins**: it can no longer serve as untouched validation for
   any later-origin comparison. The 04-15-origin scored result remains a
   valid standalone diagnostic; its "clean" status relative to later
   origins is relaxed by this design. Developmental lane only.
2. **Mechanism confound:** this comparison changes sample size, recency,
   and seasonal composition **together**. A win does not prove which of
   the three carried the gain; a loss does not prove sample size is
   irrelevant. It does not isolate the drift mechanism.
3. 2025/2026 remain untouched; no promotion claims; no production use.

## Scores (frozen)

- **Primary:** pooled paired RPS, arm B minus arm A, on identical eval
  rows; date-clustered bootstrap, 2,000 resamples, seed 20261001
  (pitcher-cluster sensitivity arm).
- **Secondary (pre-registered):** pooled NLL + clipped count; q = P(BF<9)
  mean calibration by origin and by month (the audited failure surface:
  origin q-gaps -0.009/-0.014/-0.034 for Jul/Aug/Sep under arm A); q-band
  reliability with counts + Wilson intervals; event ROC-AUC / PR-AUC;
  BF<9 slice RPS/NLL/Brier; 50/80% coverage + width overall and by
  predicted-q band; per-origin tables (pooled metrics from pooled
  row-level losses, never averaged origin metrics).
- **Oracle diagnostics:** none in this run (no realized-outcome arms).

## Gates (frozen, revised per owner correction 2026-10-06)

**Gate 1 (the ONLY pass/fail gate):** pooled paired RPS (B - A) improves
with 95% date-clustered CI excluding 0. Fail -> arm B recorded as
inferior/failed, retained as benchmark evidence only.

**Gate 2 - prespecified SECONDARY diagnostic, not pass/fail** (owner:
"if these cannot be frozen before scoring, treat them as secondary
diagnostics"; no scientific acceptance margin is justified a priori):
- Metric: pooled paired RPS on the BF>=9 slice only (identical rows).
- Exact formula: mean over eval rows with BF>=9 of (rps_B - rps_A);
  date-clustered bootstrap 2,000 resamples, seed 20261001; reported with
  CI. Tolerance stated but EXPLORATORY: degradation is flagged if the CI
  upper bound exceeds +1% of arm-A BF>=9 mean RPS.
- The BF>=9-slice NLL and Brier(FBF<9 within BF>=9 rows) are reported
  alongside, same status.

**Gate 3 - prespecified SECONDARY diagnostic, not pass/fail.**
- Exact definition: q_gap(origin) = mean q(origin) - event_freq(origin),
  where q = P(BF<9) from the arm's PMF and event_freq is the observed
  share in that origin's eval rows. Also q_gap by month.
- Improvement = |q_gap| smaller for arm B on Jul and Sep origins;
  reported with paired date-clustered uncertainty on mean q. EXPLORATORY
  (n=734/844, events 30/57 -> wide CIs); direction reported, never a
  promotion gate.

Kill rule: gate 1 fails -> no further arm-B development without a new
owner decision. No calibration layers, no threshold selection from eval
results, no reruns.

## Prohibited

2024+ data; feature changes; index interactions (parked); LightGBM
(parked); realized-BF role labels; changes to frozen run artifacts;
evaluation-date repairs; commits/pushes/production changes.

## Readiness (implementation, not executed in this task)

- Runner change (new sibling script or gated flag; frozen defaults
  unchanged): arm-B training mask `game_date < origin_ts` without the
  eval-window exclusion; per-arm preprocessing; fail-loud count/hash
  gates; manifest records arm definitions + prereg sha.
- Synthetic tests (required green before any scored run):
  1. origin-specific labels: arm-B fit for 07-01 contains 06-30 rows and
     excludes 07-01 rows (boundary rows on both sides).
  2. per-arm preprocessing: standardization stats differ between arms and
     are fitted on that arm's rows only.
  3. April coincidence: arms produce identical PMFs for the 04-15 origin
     on injected data.
  4. no-fit leakage probe: mutating a training-row outcome changes only
     that arm's PMFs, never another origin's eval PMFs.
  5. empty/insufficient training raises `MechanicalFailure` (min counts:
     >=50 rows and >=1 short event per arm-B fit; freeze exact minimums in
     the frozen prereg).
- Artifact additions (needed before the run): persist per-row pregame
  features + predicted-q bands (or a features parquet) in run outputs so
  history-depth coverage bands never require raw re-reads again. Additive
  columns only; existing consumers unaffected.
