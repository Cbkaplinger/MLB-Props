# 2024 Transfer Evaluation — Preregistration (frozen, proposed)

Parent runs: corrected-history diagnostic + April extension (same
challenger, same config). Status: FROZEN BEFORE EVALUATION. One
developmental transfer diagnostic. No promotion, no betting claim.

Question: does the corrected-history Ridge advantage persist on
2024 starts under strictly pregame information?

## 1. What is frozen vs what evolves

A. FROZEN FITTED PARAMETERS: Ridge pipeline (median imputer,
standard scaler, Ridge), alpha grid `logspace(-2, 3, 12)`,
earliest-alpha tie-break, clip rule, and the 10-feature list are
unchanged. One fit on full-2023 BF>=1 starts (all 2023 labels;
inner split = last 20% distinct 2023 dates; unformable = BLOCKED).
No 2024 label enters any fit, scaler, imputer, clip, or alpha
choice. No selection, calibration, or tuning on 2024 outcomes.

B. EVOLVING HISTORIES: per-forecast histories update as 2024
unfolds from 2022 + 2023 + prior-2024 appearances (strictly prior
dates, same-game and same-date excluded, canonical keys). Prior
completed 2024 outings entering later histories is explicitly
permitted: history updating, not model refitting.

## 2. Windows and population

Origins (proposed, mirror development comparability): 2024-07-01,
2024-08-01, 2024-09-01; final eval date 2024-10-01. Evaluation
rows: 2024 first-pitcher BF>=1 starts in-window (canonical keys,
zero-BF quarantine, eligible=False, UNVERIFIED labels — same
definitions as the development lane).
Baselines on identical rows: corrected trailing (updated
histories, min 3, fallback counted), train-mean (full-2023 mean,
fixed), team-rate two-feature Ridge (full-2023 fit, same config).

## 3. Team-rate levels for 2024 forecasts

Current level: strictly-prior 2024 aggregates. Prior level:
complete-2023-season aggregates (2023 complete before every 2024
forecast date: cutoff-free, same pattern the 2022 priors used).
League levels likewise. Chain exhaustion = BLOCKED. Hand from
realized game record (limitation preserved).

## 4. Fallback (proposed, needs approval)

RETAIN the derived 2022 constant (mean BF 21.9259, n=4,859,
derivation record in the base-run manifest): strictly prior to all
2024 forecasts, already recorded, zero new leakage surface.
Alternative (2023-derived expanding fallback) rejected: added
complexity without benefit. The constant enters ONLY the spine
shrunk-fallback term; rows flagged and counted. If the owner
requires otherwise, this preregistration is void for that choice.

## 5. Metrics, intervals, slices, kills (unchanged)

MAE/RMSE/bias per origin + pooled; paired challenger-minus-baseline
diffs; date-clustered primary + pitcher sensitivity CIs (2000,
seed 20261001); registered comparisons (vs trailing PRIMARY,
vs teamrate kill, vs trainmean descriptive); oracle-gap
NOT_COMPUTED (no matched ablation); baseline-kill rule applies;
tail flag descriptive; mandatory slices incl. experience,
missing-history, fallback, per-origin coverage.

## 6. Inputs and hashes

2024: `data/Savant-Data/regular/2024/statcast_2024_regular.parquet`
(path per repo layout convention; NO verified digest on record —
fresh hash + record at execution, first measurement, no comparison
target). Histories: verified 2022 + 2023 artifacts (digests on
record; re-verify fresh at execution). No 2025/2026 access.
No approved BF reference: run is diagnostic; independent
reconstruction-validation gate NOT passed by it.

## 7. Exposure disclosure (verified repo records only)

2024 is NOT pristine: Savant 2024 pulled + inventoried (funnel
manifest pattern); PA program trained/evaluated on 2024 chrono
blocks (E1 55,815 / E2 50,252 rows); shared processed artifacts
physically span 2024-2026 (prior deviation record). Label:
non-pristine developmental transfer evidence. Never a pristine
holdout. 2025/2026 remain closed and untouched.

## 8. Outputs and run policy

System-temp (or task-authorized research-root) run dir only:
manifest, predictions, metrics, paired, slices, exclusions,
report, next-steps. Single-run policy (mechanical repair only on
owner review; valid run never rerun). Stop on hash/period/
population/duplicate/nonfinite/incomplete-manifest violations.
