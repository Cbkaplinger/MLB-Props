# Granular open calibration challenger

**Dated:** 2026-09-01  
**Status:** research / shadow only — **no live calibrator or KING edit**.  
**Pre-registered pick rule:** maximize late-open holdout `brier_skill_vs_market` (start 2026-05-01).

## Data
- Open cache rows: **7920** (2025-03-27 → 2026-07-10)
- Fit (pre-holdout): n=6336
- Holdout: n=1584
- Frozen ensemble: `live_krate_ensemble.json` (raw p_over)

## Holdout metrics (selection universe)

| Scheme | n | Brier skill vs mkt | Logloss skill | ECE | bias_pp |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw | 1584 | -0.035 | -0.027 | 0.06802 | 0.3 |
| global_isotonic | 1584 | -0.0142 | -0.0101 | 0.01747 | -1.41 |
| global_platt | 1584 | -0.0158 | -0.0113 | 0.02187 | -1.3 |
| line_isotonic | 1584 | -0.0284 | -0.0314 | 0.05084 | -1.68 |
| line_bucket_isotonic | 1584 | -0.02 | -0.0144 | 0.02809 | -1.56 |

**Selected by holdout skill:** `global_isotonic` (skill=-0.0142).

### Holdout by line (selected scheme)

| Line | metrics |
| --- | --- |
| 2.5 | n=24 brier=0.25244 ece=0.12139 skill_brier=-0.0032 skill_ll=0.0021 bias_pp=9.14 |
| 3.5 | n=279 brier=0.24117 ece=0.03836 skill_brier=-0.0213 skill_ll=-0.0146 bias_pp=2.11 |
| 4.5 | n=553 brier=0.24344 ece=0.02891 skill_brier=-0.0066 skill_ll=-0.0048 bias_pp=-0.61 |
| 5.5 | n=470 brier=0.25001 ece=0.05128 skill_brier=-0.0192 skill_ll=-0.0142 bias_pp=-3.34 |
| 6.5 | n=196 brier=0.23557 ece=0.0518 skill_brier=-0.0063 skill_ll=-0.0042 bias_pp=-2.67 |
| 7.5 | n=48 brier=0.25264 ece=0.10794 skill_brier=-0.0485 skill_ll=-0.0336 bias_pp=-10.79 |
| 8.5 | n=13 (insufficient) |
| 9.5 | n=1 (insufficient) |

## Post-freeze OOS (scored after selection — do not re-pick)

Fixed KING tickets matched to graded raw p_over: n=73. Live ticket ROI: {'n': 73, 'stake': 5115.44, 'pnl': -122.01, 'roi': -0.0239}.

| Scheme | fixed skill (all) | over skill | under skill | CF floor0.12 ROI |
| --- | --- | --- | --- | --- |
| raw | skill=-0.1592 ece=0.18743 | -0.1724 | -0.1368 | n=101 roi=-0.0872 |
| global_isotonic | skill=-0.0816 ece=0.12052 | -0.0779 | -0.0878 | n=48 roi=-0.0535 |
| global_platt | skill=-0.0685 ece=0.11868 | -0.0579 | -0.0862 | n=40 roi=0.0587 |
| line_isotonic | skill=-0.0669 ece=0.12163 | -0.0765 | -0.0507 | n=56 roi=0.0439 |
| line_bucket_isotonic | skill=-0.0699 ece=0.1243 | -0.0734 | -0.064 | n=51 roi=0.0198 |

### Live `p_model` on same fixed KING set
n=73 brier=0.27756 ece=0.17937 skill_brier=-0.1253 skill_ll=-0.1016 bias_pp=17.94

## Overfitting watch

- Line-isotonic holdout skill ≈ global — granular maps may be noise; prefer global or buckets.
- OVERFIT WATCH: post-freeze CF ROI would prefer `global_platt` (roi=0.0587) vs holdout pick `global_isotonic` — do NOT switch; holdout rule stands.
- Frozen k-rate ensemble may have partially seen open-season games in train; calibrator chrono-split + post-freeze window remain the honest tests.
- Calib challenger does not replace 4.5-over veto / asym floors — selection toxicity can remain.

## Questions for user (before any promote)

- Accept holdout-selected `global_isotonic`, force `line_bucket_isotonic` for stability, or stay on live global transfer map?
- Is min_n=300 per line / 500 per bucket right, or raise further?
- Promote gate: require holdout skill > global by ≥X and post-freeze over skill not worse — what X?
- Apply new map under shadow only with current floors, or jointly with veto_4_5_over (separate A/B)?
- Rebuild full open→manual transfer stack with granular calib, or calib-only overlay on current p_raw?

## Reproduce
```bash
python production/ops/fit_granular_open_calibration.py
```

Artifacts: `artifacts/odds_log/granular_open_calibration_20260901.json`, cache `artifacts/odds_log/open_raw_p_over_blend_cache.parquet`.  
Script: `production/ops/fit_granular_open_calibration.py`.
