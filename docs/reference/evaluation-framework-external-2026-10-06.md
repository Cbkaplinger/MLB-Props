# Evaluation framework (external research intake) — 2026-10-06

> **Status:** CURRENT canonical reference for evaluation/reporting conventions.
> **Provenance:** owner-supplied external research handoff 2026-10-06
> ("Professional-Grade Evaluation Framework for MLB Prop Forecasting",
> synthesizing a public CBB supercomputer comparison + scikit-learn /
> forecast-evaluation literature). Key points reconciled into
> `docs/EXECUTION_BACKLOG.md`; the normative content lives here.
> **Not** a queue — work items live in the backlog only.

## Why this exists

When outside research (Muse outputs, articles, papers) is handed to the
project, its durable norms get captured here or in a sibling dated
reference doc, then the backlog points at it. Past examples of this
pattern: `reports/historical_clv_odds_apis_2026-09-02.md` (Perplexity
vendor research -> dated report + AGENTS.md pointer),
`oddsapi_replay_architecture.md` (external spec -> standing reference),
`research_assistant_instructions.md` (external constraints doc). The gap
this file closes: no canonical home existed for *evaluation-methodology*
norms from outside sources — until now.

## 1. Metric contract by layer (normative)

| Layer | Primary | Secondary | Key diagnostic |
| --- | --- | --- | --- |
| BF point | MAE | RMSE, signed bias, R2_OOS, MAE/RMSE skill | short-outing + tail errors |
| BF distribution | RPS | NLL, BF<9 Brier, 50/80% coverage **and width** | CDF/threshold reliability |
| PA K probability | log loss or Brier | calibration intercept/slope, resolution, AUC (discrimination only) | reliability curve, probability bands |
| Pitcher K point | MAE | RMSE, bias, R2_OOS | workload-vs-rate error budget |
| K distribution | RPS or discrete log score | count MAE/RMSE from a declared functional, interval coverage/width | count + tail calibration |
| Line probability | Brier/log loss vs de-vigged market | calibration, line-specific skill, disagreement buckets | model-minus-market probability |
| Betting policy | CLV + EV diagnostics | ROI, PnL, Sharpe, drawdown, Calmar with uncertainty | performance by frozen edge threshold |

Rules: MAE primary for BF point unless a frozen spec says otherwise; MAE
targets the conditional median, squared loss the mean — say which one an
output is. RPS for ordered counts. Proper scores (Brier/log loss) for
probabilities; AUC is discrimination-only, never calibration evidence.
Coverage without width is incomplete. Every metric computed on identical
retained rows across challenger and baselines (row-identity hashes).

## 2. R2_OOS definition (replaces the ambiguous "variance explained")

**Out-of-sample squared-error skill:** `R2_OOS = 1 - SSE_model /
SSE_reference`, with the reference forecast and its information cutoff
stated explicitly. Two labeled versions: *train-mean R2_OOS* (reference =
origin-specific training mean, forecast-available) and *baseline skill*
(reference = deployed comparator such as trailing history or market).
Never use the test-set mean as an operational forecast. Never substitute
squared correlation `Cor(y, yhat)^2` — it hides systematic bias. R2_OOS is
contextual: it ranks identically to MSE on one frame and can be negative.

## 3. Oracle error-budget decomposition (non-deployable diagnostics)

| Arm | BF | PA K | Meaning |
| --- | --- | --- | --- |
| 1 | predicted | predicted | deployable system |
| 2 | realized | predicted | ceiling for the K-probability component |
| 3 | predicted | realized rate | ceiling for workload |
| 4 | realized | realized | identity check, not a model |

All oracle arms labeled non-deployable; never used for model selection.

## 4. Baselines and comparisons (normative)

- Identical scored rows, enforced by hashes; paired date-clustered
  bootstrap for differences (same-date forecasts are not independent).
- Naive baselines always: trailing history, team-rate, train mean,
  market probabilities where they exist.
- Skill scores `1 - L_model/L_baseline` with the reference named; report
  outcome dispersion by window so raw-error changes across difficulty
  regimes are interpretable.
- Ensemble/blend weights frozen on training or inner temporal validation;
  first ensemble baseline is the equal-weight average; optimized weights
  must beat it out of sample on a later untouched window.
- Full-precision forecasts for primary scoring; rounding only in a
  labeled operational analysis.
- DM/Clark-West tests only if they match the design; never to
  manufacture p-values.

## 5. Slices and diagnostics (prespecified)

Mandatory slices, each with count + uncertainty: short outings (retrospective
label — never "openers" without timestamp-valid role evidence), history
depth/cold start, month/season, predicted workload bands (operational),
handedness if genuinely pregame, pitcher/team concentration, market
availability (market-layer reports only). **Slicing by observed BF is
diagnostic/retrospective; slicing by predicted risk is operational — label
the use.** Also: error quantiles (median/q90 AE, within-1/2/3/5 rates),
signed-error quantiles, residual clustering by date/pitcher/team, Murphy
diagrams for threshold-domain calibration at decision points (e.g., P(BF<9),
P(K>=5), sportsbook lines).

## 6. Validation-report structure (generated, versioned)

Front matter (experiment ID + status preregistered/developmental/transfer/
independent, target, information contract, population/exclusions, windows,
data+code+env identities, exposure disclosure) -> four-line executive
result (model, comparator, identical n, paired change + decision) -> main
point table (n, MAE, RMSE, bias, R2_OOS, MAE/RMSE skill) -> distribution
table (n, RPS, NLL, short-BF Brier, 50/80% coverage/width) -> stability
table (per origin/season + pooled computed from pooled row-level losses,
never averaged origin metrics) -> mandatory slices -> calibration section
-> failure analysis (cases paired with aggregate evidence) -> **exactly one
decision** citing frozen gates (promote / retain-as-benchmark / repair
defect / reject / inconclusive). Exploratory findings go to a hypothesis
backlog; they never retroactively change the evaluated model.

## 7. Canonical evidence schema (per run)

`manifest.json` (immutable provenance + information contract),
`predictions.parquet` (row identity, observations, every model prediction,
loss contributions, slices), `metrics.csv`, `paired_differences.csv`,
`calibration.csv`, `slices.csv`, `exclusions.csv`, `claim_ledger.csv`,
generated `validation_report.md`. Manuscript claims get durable IDs (e.g.,
`BF-POINT-2024-TRANSFER-01`); paper sentences reference the ID; the ledger
carries exact values, hashes, populations, limitations. Dated markdown
reports declare CURRENT / SUPERSEDED / HISTORICAL / EXPLORATORY and point
to the canonical successor. Main paper table leads with effect sizes
(challenger vs baseline, paired change, CI, skill, status); RMSE/bias/
R2_OOS/slices/provenance go to the appendix table.

## 8. Exposure boundaries

If 2023-2024 odds or any window informs model/feature/threshold/policy
selection, that window becomes development data for that layer — never
clean validation. Label repeatedly examined windows developmental. Select
one candidate for transfer; do not repeatedly select against transfer
results. Market availability/lines stay in market-informed secondary
models; the independent baseball model never consumes them.

## 9. Recommended evaluation sequence (from the framework)

1. Frozen BF-distribution diagnostic (DONE 2026-10-06, developmental).
2. BF-distribution failure audit (DONE 2026-10-06, this framework's
   outcome-selected vs conditional-coverage distinction applied).
3. Workload error budget (oracle arms 2-3).
4. Same-feature Ridge-vs-LightGBM BF comparison (benchmark, not ablation).
5. Complementarity analysis before any ensembling (residual correlation,
   equal-weight blend, training-only optimized weights).
6. Chronological PA-K probability model (Brier/log loss + calibration).
7. K error-budget oracle diagnostics.
8. Full K distribution (count proper scores, line-event calibration).
9. De-vigged market benchmark (separate layer).
10. Frozen betting-policy evaluation (CLV with uncertainty before ROI).

## Implementation-status matrix (added 2026-10-06, owner-directed)

A CURRENT reference is NOT evidence its contracts are operational. Actual
statuses, with implementation paths inspected in `main-active`:

| Framework element | Status | Path / evidence |
| --- | --- | --- |
| RPS / NLL / short-BF Brier / 50-80% coverage+width / empirical baseline | **IMPLEMENTED** (research lane) | `research/offseason_2026/bf_distribution.py`; used by `run_bf_distribution_2023.py`; verified by `tests/test_bf_distribution.py` |
| MAE / signed bias / paired date-clustered bootstrap / per-origin slices | **IMPLEMENTED** (research lane) | `run_corrected_history_2023.py` (`cluster_bootstrap`, slice writer); `tests/test_corrected_history_2023.py` |
| Canonical run artifacts: manifest / predictions / metrics / paired_differences / slices / exclusions / report | **IMPLEMENTED (point-model runs, de facto)** | e.g. `MLB-Props-Research\workload-corrected-history-20261005_215556\` (corrected_history_manifest.json, predictions.csv, metrics.csv, paired_comparisons.csv, slices.csv, exclusions.csv, report.md) |
| predictions.parquet (vs csv) + loss-contribution columns | **PROPOSED** | runs emit csv; pmfs.parquet exists only in the BF-distribution lane |
| calibration.csv as a run artifact (reliability bins/thresholds) | **PROPOSED** | produced only as derived audit output (`workload-bfdist-failure-audit-20261006\q_reliability_bands.csv`), not by runners |
| Row-identity hashes across challenger and every baseline | **PROPOSED** | manifests record code/input hashes; explicit eval-row-identity hash across arms not yet emitted |
| claim_ledger.csv + durable claim IDs (e.g. BF-POINT-2024-TRANSFER-01) | **PROPOSED** | documented here only; no generator exists |
| Generated validation_report.md (schema-driven) | **PROPOSED** | current report.md files are runner-written free-form summaries |
| R2_OOS (1 - SSE_model/SSE_reference, named reference) | **PROPOSED** | not implemented anywhere; corrected-history runs record oracle-gap NOT_COMPUTED |
| MAE/RMSE skill scores (1 - L_model/L_baseline) | **PROPOSED** | ratios derivable from metrics.csv; not emitted as named metrics |
| Oracle error-budget arms (2-3) | **PROPOSED / BLOCKED on design** | needs matched-population oracle inputs; deliberately not computed (marked non-deployable in spec) |
| DM / Clark-West formal tests | **PROPOSED (deliberately not implemented)** | paired cluster bootstrap is the frozen comparison method; tests only if a design requires them |
| Blend weights frozen on training / equal-weight first baseline | **PARKED** | gated behind the Ridge-vs-LightGBM benchmark (not built) |
| Market / betting-layer metrics (de-vig, CLV, ROI uncertainty) | **OUT OF SCOPE here** | live in production grading/CLV stack; separate layer |
| History-depth coverage bands | **BLOCKED** | run artifacts lack per-row features; fix specified in `research/offseason_2026/expanding-training-prereg-draft.md` readiness section |

Rule going forward: a framework element may be cited in the paper only at
IMPLEMENTED status with its path named; DOCUMENTED/PROPOSED items are plan,
not evidence.
