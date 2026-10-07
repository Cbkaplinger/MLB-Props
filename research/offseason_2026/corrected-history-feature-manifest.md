# Corrected-History Workload Feature Manifest (frozen)

Covers the corrected-history challenger (10 features) and the frozen
Run 1 BF-model feature set (22 + 2) for comparison. No additions or
removals. History-construction changes are separate from feature
changes: identical names below may carry different values across runs
because the histories feeding them were rebuilt.

Conventions: all lookbacks strictly prior (`game_date <` forecast
date; same date excluded, doubleheaders included in the exclusion);
nulls handled by training-fitted median imputation unless stated;
usage BF = frozen Run 1 non-oracle Ridge, CH = corrected-history
challenger.

## Spine history summaries (CH only; Savant-derived via workload_spine)

| Name | Definition | Source | Lookback | Cutoff | Missingness |
|---|---|---|---|---|---|
| start_capacity_shrunk_bf | Start-BF mean shrunk to population mean (K=20 appearances) | prior start appearances, canonical keys | all strictly-prior starts | forecast date | never null (falls back to population mean, flagged) |
| start_capacity_median_bf_5 | Median BF of last <=5 starts | same | last 5 starts | forecast date | null if no prior starts (imputed) |
| start_capacity_mean_bf | Mean BF of prior starts | same | all strictly-prior starts | forecast date | null if no prior starts (imputed) |
| n_capacity_appearances | Count of post-reset appearances | same | post-reset window | forecast date | 0 allowed |
| relief_mean_bf | Mean BF of prior relief appearances | prior relief appearances | all strictly-prior relief | forecast date | null if none (imputed) |
| actual_bf_mean_last5 | Mean BF of last <=5 appearances (any role) | all prior appearances | last 5 | forecast date | null if none (imputed) |
| actual_expanding_mean_bf | Expanding mean BF, all appearances | all prior appearances | all strictly-prior | forecast date | null if none (imputed) |
| days_since_last_capacity | Days since last capacity appearance | post-reset history | last event | forecast date | null if none (imputed) |

## Team-rate features (BF + CH; Savant batting rows only)

| Name | Definition | Source | Lookback | Cutoff | Missingness |
|---|---|---|---|---|---|
| opp_team_k_rate_std | Opponent team K/PA, all hands | batting rows, schedule-side opponent | strictly-prior dates + 2022 season fallback chain | forecast date | frozen fallback chain (team->league, current->prior); exhaustion = BLOCKED |
| opp_team_k_rate_vs_hand | Same, vs pitcher's throwing hand | same + bio hand attribute | same | forecast date | hand-unknown uses std chain, flagged |

Hand comes from the realized game record (limitation preserved in
labels), never timestamped pregame evidence.

## Frozen BF-model features (BF only; prior-data artifacts, Run 1)

Rest/volume: `days_rest_capped`, `is_season_debut`,
`rest_is_long_gap`, `rest_gap_severity`, `is_career_mlb_debut`
(pitcher_rolling shift(1) constructs; 525 missingness cases in Run 1:
197 no-rolling-row short outings + 328 debut-nulls, median-imputed,
rows never dropped). Trailing workload: `PA_P5/P10/P20`,
`Outs_P5/P10/P20`, `Pitches_P5/P10/P20` (same artifact source).
Context: `is_home` (schedule side), `park_k_factor`
(prior-season park factors). Bullpen: `bullpen_pitches_L1/2/3d`,
`bullpen_pitchers_used_L1/2/3d` (prior team games). Removed in CH:
`opp_lineup_k`, `opp_lineup_k_vs_hand` (realized-lineup oracle
lineage; replaced by the team-rate pair above).

## Usage matrix

- Frozen BF model (Run 1): 22 above + 2 team rates. NOT reused in CH.
- Corrected challenger: 8 spine + 2 team rates. No rolling-artifact
  inputs. No lineup inputs.
- Baselines use no features (trailing/train-mean) or the 2 team
  rates (team-rate Ridge, same fit machinery).
