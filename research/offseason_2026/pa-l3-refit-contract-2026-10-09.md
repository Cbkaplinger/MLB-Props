# PA L3-style refit contract (2026-10-09) — frozen before fitting

> **Status: FROZEN.** Owner authorization 2026-10-09: one bounded
> chronological L3-style refit, conditional on readiness checks. This is an
> **L3-style v1 ADAPTATION**, not a reproduction — every deviation from the
> serialized L3 recipe is listed below. No tuning, no feature search, no
> multiclass, no aggregation, no production edits, no 2025/2026 reads.

## Question

Does the L3 advantage (stored D beat log5 by −0.000614 [-0.001216, -0.000031]
on 2024 matched rows) survive correct pa_completed_v1 labels, explicit
features, and strictly chronological per-origin fitting?

## Arms and family

- **A** = shrunk log5 (w=150), unchanged from the corrected PA lane.
- **D3** = newly fitted L3-style logistic (below), per chronological origin.
- Stored L3 (D) remains a matched-row diagnostic reference only; it is NOT
  an interchangeable newly fitted arm.
- Primary family: {D3−A}, paired per-PA log loss, slate-date clustered
  bootstrap (2000, seed 20261001). Secondary: Brier, reliability bands,
  start-weighted, coverage, cold-start and short-outing slices. All results
  labeled development evidence.

## Frozen feature manifest (24 columns, exact order)

`same_hand, b_hand_rate, b_whiff, b_swstr, b_chase, p_whiff_P5, p_swstr_P5,
p_chase_P5, p_zone_P5, p_contact_P5, p_whiff_std, p_swstr_std, p_chase_std,
p_zone_std, p_contact_std, log_pa_curr, log_pa_prior, park_k, rest, debut,
trip_eq_2, trip_eq_3, trip_ge_4, spi_over_9`

Definitions (v1 adaptation; observation unit, denominator, window):

| Feature | Definition |
| --- | --- |
| same_hand | 1{p_throws == stand} on the PA row |
| b_hand_rate | batter pooled prior K rate vs the pitcher's hand, shrunk (k+w*lg)/(n+w), w=150, lg = origin league rate; n_prior counts carried; cold start → lg |
| b_whiff / b_swstr / b_chase | batter pooled prior whiffs / swinging strikes / chases over swings (chase = swing with zone >= 11), all prior seasons pooled, game_date < cutoff; counts carried; fill 0 when denominator 0 |
| p_*_P5 | pitcher rates over the LAST 5 PRIOR STARTS (by game_date < cutoff), pooled counts within the window; <5 prior starts → null → fill 0 |
| p_*_std | pitcher current-season-to-date pooled rates (same season, strictly prior starts); no in-season prior start → null → fill 0 |
| log_pa_curr | log1p(pitcher same-season prior completed PAs) |
| log_pa_prior | log1p(pitcher career prior completed PAs) — stored L3 zeroed this column; the refit learns its weight (declared deviation) |
| park_k | PRIOR-SEASON EB park K factor: ((K_park + 500*lg_s)/(N_park + 500)) / lg_s, computed from the prior season's raw data only (2022→2023 block; 2023→2024 block); no current-season data touches it |
| rest | days since previous start, clipped to [1,15]; no prior start → 15 |
| debut | 1{no prior start in the current season} |
| trip_* / spi_over_9 | trip = 1 + (spi−1)//9, spi = within-game PA index by at_bat_number for the attributed pitcher; dummies for trip 2/3/4+ and spi/9 |

Imputation (frozen, mirror of the bundle manifest): nan_to_num(0) for all
columns except b_hand_rate → lg, park_k → 1.0, rest → 15. All fills applied
before scaling; scaling constants (mean/std) from TRAINING ROWS ONLY per
origin.

## Estimator (frozen)

sklearn LogisticRegression(penalty=l2, C=0.01, solver=lbfgs, max_iter=2000)
— the stored L3 settings; NO C search, no class balancing, no calibration.
Convergence status recorded per origin; no parameter changes after viewing
scores. sklearn/LightGBM versions recorded in the manifest.

## Chronology and population

- Population: pa_completed_v1 completed first-PA rows (per-side starters;
  short outings RETAINED — deviation from their Q-D4 PA>=9 cohort).
- 2023 block: origins 04-15/07-01/08-01/09-01; training = 2023 pre-origin
  rows only; 2022 enters via prior aggregates (feature histories + lg).
- 2024 block: training = 2023 full + 2024 pre-origin rows.
- Per-origin scaler and per-origin league rate; eval windows identical to
  the corrected PA lane. 2024 = chronological development transfer.

## Permanent join guards (preflight ledger, every run)

Recorded per season and asserted fail-loud: n_pa_input, n_unique_pa,
n_duplicate_pa (=0), n_snapshot_keys, n_duplicate_snapshot_keys (=0),
n_snapshot_pitcher_mismatch (=0; snapshot key set must equal the
(game_pk, pitcher) pairs of scored rows), join_expansion (=0), exclusions
(incomplete/baserunning/mixed-batter counts), arm coverage per origin.
These gates ship in the runner, not only in standalone tests.

## Deviations from the serialized L3 recipe (adaptation ledger)

1. Labels/population: pa_completed_v1 (corrected) vs their primary rows;
   short outings retained vs PA>=9 cohort; mixed-batter excluded.
2. Per-origin refits + per-origin scaler vs their single 2023 fit with
   2023-frozen scaler.
3. Discipline/P5/std features rebuilt from pooled raw counts with declared
   windows (above) vs production rolling-table columns.
4. park_k EB recomputed from prior-season raw (w=500) vs their processed
   park_factors artifact (vintage unverified — this substitution REMOVES a
   potential availability ambiguity rather than adding one).
5. b_hand_rate shrinkage w=150 (v1 lane constant) vs their w=200 EB.
6. log_pa_prior = career prior PAs (stored recipe zeroed it).
7. Feature values come only from the v1 pool (2022-2024 raw + labels).

Anything not listed is reproduced as specified above. The result answers
"does an L3-style recipe survive the corrected lane", NOT "is the stored L3
reproduced bit-for-bit".

## Files

Own: this contract, `run_pa_l3_refit.py`, `tests/test_pa_l3_refit.py`,
backlog receipt. Reuse (read-only): pa_lgbm_scaffold,
run_pa_lgbm_comparison helpers, provenance machinery. Stop on correctness
problems; preserve attempts and amendments.

## Amendment 1 (2026-10-09, pre-fit) — exact discipline denominators

Plate-discipline conventions (match standard CSW usage and the production
builder): **whiff = whiffs / swings**; **swstr = (called_strike +
swinging_strike + swinging_strike_blocked + foul_tip) / all pitches**;
**chase = chases (swing, zone >= 11) / swings**; **zone = in-zone
(zone 1-9, non-null) / all pitches**; **contact = contacts (foul,
hit_into_play) / swings**. P5/std variants use the same numerators and
denominators over their respective windows (counts pooled inside the
window; denominators carried alongside).
