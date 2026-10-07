# Corrected-History Workload Experiment — Preregistration (frozen)

Experiment ID: `corrected_history_workload_2023`.
Status: FROZEN BEFORE EVALUATION. One development diagnostic on 2023
with 2022 history. Not season-transfer validation, not a calibrated
strikeout distribution, not a promotion, not betting evidence.

Question: does correcting strictly-prior history construction improve
workload predictions relative to a properly reconstructed
trailing-history baseline?

## 1. Population and identity (frozen)

- 2023 first-pitcher appearances with BF >= 1, both team-side openers
  via canonical `_starter_keys` delegation (committed audit runner).
  NOT the legacy PA>=9 outcome-selected population.
- Zero-BF identity: raw = retained BF>=1 + quarantined zero-BF;
  `n_zero_bf` always reported. Quarantine with reason, never coerce.
- Every record: eligible=False, availability/role UNVERIFIED, no
  lineup evidence. Retrospective identity is NOT pregame knowability
  (disclosed limitation).
- Short outings preserved. No opener/early-hook intent inferred from
  workload. No career-debut labels from 2022-2023 absence.
- Forecast rows exist independent of current BF/K. Doubleheaders are
  separate games; same-game rows never enter a forecast's history;
  same-date rows never enter (strict `<` on game_date everywhere).

## 2. BF target (frozen)

BF per (game_pk, pitcher) = distinct at_bat_number whose terminal pitch
row (max pitch_number) has events non-null, not in canonical
NON_PA_EVENTS, and not `truncated_pa` (tracked `src/Python/statcast.py`
sets). Excluded at_bats are counted as quarantine, never silently
dropped. Column name in frames: `PA` (matches Run 1 naming; means BF
per this definition).

## 3. Origins and boundaries (exact, from frozen addendum)

Origins 2023-07-01, 2023-08-01, 2023-09-01; season window
2023-03-30..2023-10-01. Training: `2023-03-30 <= game_date < o`.
Inner validation: last 20% of DISTINCT training dates
(floor index `int(0.8 * n_dates)`); `<3` dates or empty side =
BLOCKED lane. Evaluation: `[o, min(o', 2023-10-01)]`, latest
preceding origin owns each start; windows disjoint; one prediction
per (origin, game_pk, pitcher) or mechanical failure.

## 4. Histories (frozen)

Built by committed `workload_spine.build_appearance_history` from
Savant-derived appearances (both seasons): is_start from canonical
keys per game, pitches = pitch-row count, outs recorded 0 (builder
v2.2 never reads outs; documented). 2022 + 2023 appearances;
strictly-prior + same-game exclusion enforced by builder construction.
History labels (no-prior/season-debut/left-censored/join-failed kept
distinct) feed slices and fallback accounting only.

## 5. Challenger and baselines (frozen)

Ridge pipeline (median imputer, standard scaler, Ridge), alpha grid
`logspace(-2, 3, 12)`, tie-break earliest alpha on inner MAE, clip =
training BF q0.999 upper / 0.0 lower, refit on full origin-train.
No search, no variants after scores.

Challenger `corrected_ridge_v1` features (10, frozen):
`start_capacity_shrunk_bf`, `start_capacity_median_bf_5`,
`start_capacity_mean_bf`, `n_capacity_appearances`,
`relief_mean_bf`, `actual_bf_mean_last5`,
`actual_expanding_mean_bf`, `days_since_last_capacity`,
`opp_team_k_rate_std`, `opp_team_k_rate_vs_hand`
(nulls via training-fitted median imputer; team rates by frozen
fallback chain from Savant batting rows; hand from realized game
record, limitation preserved).

Baselines on IDENTICAL rows/cutoffs: corrected trailing
expanding-mean over strictly-prior START appearances 2022+2023
(min history 3, train-mean fallback counted; starts-only estimand
kept, window widened vs Run 1's 2023-only — disclosed, so this is a
methods comparison, not a clean causal ablation); train-only
population mean; team-rate two-feature Ridge (same machinery).
Legacy rolling-artifact trailing is NOT reproducible without
multi-season opens: omitted by rule, stated here.

## 6. Fallback (frozen policy)

ONE constant: mean BF over the matching 2022 first-pitcher BF>=1
population (same keys, same BF definition). Record n, sum, mean,
source hash, code hash, cutoff (all source dates < 2023-01-01).
Enters ONLY as `population_mean_bf` into the spine builder's
shrunk-fallback term. Rows receiving fallback counted by origin
and slice via `no_prior_start_fallback`. Never hides failed joins,
invalid keys, or corrupted histories. If the 2022 population cannot
be built reliably: STOP, no 2023-mean or arbitrary substitute.

## 7. Metrics, intervals, slices, kills (frozen)

Per origin + pooled: MAE, RMSE, signed bias (prediction - expected)
per arm; paired challenger-minus-baseline diffs. Bootstrap:
date-clustered primary + pitcher sensitivity, 2,000 resamples, seed
20261001, percentile 95%. Registered comparisons:
challenger-vs-trailing (PRIMARY), challenger-vs-teamrate (kill),
challenger-vs-trainmean (descriptive). Oracle-gap NOT_COMPUTED
(reason: no matched ablation). Baseline kill: challenger MAE >=
team-rate MAE in >=2/3 origins => lane STOPS. Tail flag descriptive
only. Slices (counts + metrics, point estimates): BF<9, BF<=6,
7-8, BF>=9, month, experience (debut/<10/>=10 priors),
missing-history flag, fallback usage, per-origin coverage.
Outcome-defined slices are retrospective diagnostics, never
features. Empty/unstable slices shown, never imputed.

## 8. Outputs and run policy

Run dir under system temp only. manifest.json (provenance, all
hashes incl. this prereg, versions, command, status),
predictions (one row per evaluated identity/origin/target/forecast),
metrics.csv, paired_comparisons.csv, slices.csv, exclusions.csv,
report.md, next_steps.md. Single-run policy: mechanical failure may
be repaired+retried on owner review with receipt preserved; valid
run never rerun. Stop conditions: hash/period/population/duplicate
violations, nonfinite predictions, incomplete manifest.

## 9. Provenance inventory (reviewed reuse)

| Source path | SHA-256 (verify at implement) | Reused destination | Substantive changes |
|---|---|---|---|
| research/offseason_2026/tbf_reconstruct.py: ALPHA_GRID, INNER_VAL_FRACTION(0.2), ORIGINS_2023, FINAL_EVAL_DATE, assign_origins, _inner_chrono_split, fit_origin | (recorded in manifest) | new run_corrected_history_2023.py | NONE (verbatim; target column `PA` = BF per section 2, same as Run 1) |
| research/offseason_2026/tbf_nonoracle.py: BOOTSTRAP_*, TRAILING_MIN_HISTORY(3), TEAMRATE_FEATURES, build_rate_tables, team_rate, build_team_rate_features, prior_season_rates, build_batting_rows, evaluate_arm, cluster_bootstrap, assert_unique_predictions, assert_finite_predictions, evaluate_kill_rules | (recorded in manifest) | same new module | NONE except trailing: strict date-inequality expanding mean implemented separately (shift(1) version admits same-date DH rows; difference documented in section 5) |
| research/offseason_2026/run_reconstruction_audit_2023.py (committed 52379dd) | e90955dd... | imported, not copied | NONE |
| research/offseason_2026/workload_spine.py (committed 6318b95) | dcb5e776... | imported, not copied | NONE |
| src/Python/statcast.py NON_PA_EVENTS/STRIKEOUT_EVENTS (tracked) | (recorded in manifest) | imported, not copied | NONE |
| research/offseason_2026/run_nonoracle_2023.py: origin/pool/manifest conventions | — | adapted (no oracle arms, no rolling artifacts) | documented in sections 3/7/8 |

No 2025/2026 access. No tuning. No promotion claims.
