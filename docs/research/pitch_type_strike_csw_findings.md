# Per-pitch-type strike% / CSW% / SwStr% (Tier 1) — findings

> Metric lane note: this is a historical candidate-screening note. Current
> deployment winners/champions are tracked in
> `docs/reference/governance_metric_stack.md`.

## Motivation

Every per-pitch-type feature in the legacy frozen single-model registry is physics/usage
only: velo, spin, IVB, HB, VAA, and usage vs R/L. The model has no signal on whether a
given pitch type is actually *good* by outcome (command + stuff blended into one
number), which is a plausible explanation for pitchers whose secondary-pitch shape
looks ordinary by Stuff+-style physics metrics but who outperform on results (e.g. an
elite low-usage changeup). This note documents the Tier-1 pass: per-pitch-type
`strike%`, `CSW%`, and `SwStr%`, built with the same empirical-Bayes shrinkage
machinery already proven on per-pitch-type RV
(`Python.pitcher_rolling.add_pitch_type_rv_features`), then screened with the
project's standard nested walk-forward lift test.

**Verdict: HOLD.** The candidates do not clear the predeclared both-outer-fold MAE
bar. No registry change was made. Details and the exact numbers below.

## What was built

1. **Level 1** (`src/Python/pitcher_features.py`, `build_pitch_type_games`): added
   `StrikesPlusBIP` and `strike_rate` (= `(Strikes + BIP) / Pitches`, mirroring the
   aggregate `strike_rate` definition in `build_pitcher_starts`) per
   `(game_pk, pitcher, pitch_type)` row. `csw_rate` and `swstr_rate` were already
   computed there but unused downstream.
2. **Stabilization** (`models/Strikeout-Model/research/run_pitch_type_stabilization.py`):
   added a `strike_rate` spec and ran the existing split-half/bootstrap stabilization
   harness (`run_stabilization.analyze`) separately for every pitch type x
   {`strike_rate`, `csw_rate`, `swstr_rate`}. This had never been executed before —
   `artifacts/stabilization/expanded/pitch_type/` was empty.
3. **Level 2** (`src/Python/pitcher_rolling.py`, `add_pitch_type_rate_features`):
   generalized `add_pitch_type_rv_features` into a reusable
   `{name: (numerator_col, denominator_col)}`-driven helper. For each pitch type,
   stat, and window it emits:
   - `{pt}_{stat}_shrunk_P{w}` — empirical-Bayes shrunk toward the pitch-type league
     rate as of strictly prior dates: `(Σnum + m·league_prior) / (Σden + m)`.
   - `{pt}_{stat}_P{w}` — the plain pitch-weighted rolling rate, no shrinkage, to
     measure whether shrinkage is actually pulling its weight.

   Stats are named `strike`/`csw`/`swstr_rate` (not `strike_rate`/`csw_rate`) because
   `src/Python/features.py` reserves the literal names `strike_rate`/`csw_rate` (with
   an optional 2-letter prefix) as deterministically-redundant identities of other
   already-modeled rates; that identity doesn't actually hold at the pitch-type grain
   yet (no per-pitch-type `cs_rate`/`ball_rate` exist to complete it), so the new
   columns were named to avoid colliding with that reserved pattern while keeping the
   exact same underlying definitions. `is_experimental_feature` was extended to
   recognize the new `{pt}_(strike|csw|swstr_rate)(_shrunk)?_P\d+` pattern so these
   stay out of the frozen baseline until/unless promoted.
4. **Level 3 (research only)**: `pitch_type_strike_csw_lift.py` joins the candidate
   columns onto the `pitcher_training.parquet` frame for the lift test; the
   production `pipeline/training.py` join was **not** touched.
5. **Lift test** (`models/Strikeout-Model/research/pitch_type_strike_csw_lift.py`):
   LightGBM-only nested walk-forward screen against frozen `production` (184),
   mirroring `lgbm_lift_promotion.py`'s promotion bar exactly (inner selection by mean
   MAE, both outer folds must improve MAE vs. core, optional chrono bake-off).

## Stabilization results (does the small-sample-pitch-type hypothesis hold?)

Yes — clearly. Split-half reliability (`r ≈ 0.5` crossing, lower 95% player-bootstrap
CI) for the fastball is reached quickly, but most secondary pitch types never reach it
at all within the pitch-count range tested (up to 2,000 pitches):

| pitch_type | stat | reliably estimable (CI-low crosses r=.50)? | typical starts at median crossing |
|---|---|---|---|
| ff | swstr_rate | **yes** | 6.5 |
| ff | strike | **yes** | 3.2 |
| ff | csw | **yes** | 11.3 |
| sl | swstr_rate | **yes** | 8.8 |
| ch | swstr_rate | **yes** | 8.3 |
| ch | strike | **yes** | 16.7 |
| si, fc, st, cu, fs | (all stats) | **no** | 8–27 (median crossed but CI-low never did) |
| sl, ch | csw, strike (sl); csw (ch) | **no** | 8–12 |

Full detail: `artifacts/stabilization/expanded/pitch_type/pitch_type_crossings_summary.csv`
and `pitch_type_descriptive_summary.csv`.

This confirms the caveat raised before building anything: only the fastball (and, for
`swstr_rate` specifically, slider/changeup) reliably stabilizes within realistic
in-season sample sizes. Every other pitch type x stat combination needs either a much
wider window than is practical (>30 starts, i.e. most of a season) or shrinkage toward
a population prior to be usable at all — exactly the empirical-Bayes treatment that
was built.

## Window nominees used for the lift test

Per (pitch_type, stat), nearest window in `{5, 10, 20, 30}` to
`typical_starts_at_median_crossing`, falling back to the longest window (30) when the
CI-low crossing was never reached in-range:

```
pitch_type  stat         nominee_window  reliably_estimable
ff          swstr_rate   5               True
ff          strike       5               True
ff          csw          10              True
si          swstr_rate   10              False
si          strike       30              False
si          csw          10              False
fc          swstr_rate   20              False
fc          strike       20              False
fc          csw          20              False
sl          swstr_rate   10              True
sl          strike       10              False
sl          csw          10              False
st          swstr_rate   20              False
st          strike       10              False
st          csw          20              False
cu          swstr_rate   10              False
cu          strike       30              False
cu          csw          20              False
ch          swstr_rate   10              True
ch          strike       20              True
ch          csw          10              False
fs          swstr_rate   20              False
fs          strike       10              False
fs          csw          20              False
```

(`artifacts/feature_research/pitch_type_strike_csw_lift/pitch_type_window_nominees.csv`)

## Lift test results

Empirical-Bayes prior strength was fixed at 200 pitches (mid-range of the observed
r=.50 crossing pitch counts across stats/pitch types; not separately tuned per stat —
flagged as a limitation below). Candidate sets tested, each layered on top of the
legacy single-model freeze core:

| configuration | n features | mean MAE improvement | min MAE improvement (worst fold) | both folds improve? |
|---|---|---|---|---|
| `production_plus_pitch_type_shrunk` (all 8 pitch types x 3 stats, shrunk) | 208 | **+0.000106** | -0.000086 | **No** |
| `production_plus_pitch_type_unshrunk` (same, no shrinkage) | 208 | -0.000141 | -0.000145 | No |
| `production_plus_pitch_type_shrunk_top3` (ff/si/sl only, shrunk) | 193 | -0.000183 | -0.000602 | No |

None clear the both-outer-fold MAE improvement bar. `production_plus_pitch_type_shrunk`
came closest: it improved MAE on `outer_2024_h2` (+0.000297) but slightly *hurt*
`outer_2024_h1` (-0.000086), and it was the inner-selected configuration on
**both** outer folds (i.e. LightGBM's own inner-fold model selection preferred it over
plain `production` every time it was inner-tested), which is a mildly encouraging sign
even though it didn't hold up on both outer confirmations.

Directionally consistent with the shrinkage hypothesis: shrunk beats unshrunk on both
outer folds (production_plus_pitch_type_shrunk mean MAE 0.078307 vs. unshrunk's
0.078554), and restricting to only the three highest-usage pitch types performed worse
than including all eight — i.e. shrinkage toward the league prior, not usage
filtering, is doing the useful work for the low-sample pitch types, matching the
stabilization data above.

Chrono bake-off (train ≤ 2024-08-05, test on the remainder) shows the same small,
directionally positive but inconclusive pattern — all three candidate sets beat plain
`production` on this single split, with `production_plus_pitch_type_shrunk_top3`
narrowly best (MAE 0.079099 vs. production's 0.079355), but a single train/test split
is not a promotion criterion on its own and both outer folds must agree, which they did
not.

Full detail: `artifacts/feature_research/pitch_type_strike_csw_lift/` (`inner_results.csv`,
`outer_results.csv`, `promotion_summary.csv`, `chrono_bakeoff.csv`, `metadata.json`).

The secondary `expected_K` product-level check (per `historical-step-findings-summary.md`'s
two-stage yardstick) was not run, since the primary `k_rate` MAE gate did not clear.

## Verdict: HOLD

Per the predeclared bar (both outer folds must improve `k_rate` MAE vs. frozen
`production`), **none of the candidate sets are promoted**. `registries.py` and the
production model were not touched.

This is a genuine "prove me wrong" answer, not a shrug: the underlying hypothesis (most
secondary pitch types need heavy shrinkage, and shrunk beats unshrunk) held up exactly
as predicted in both the stabilization pass and the lift test's internal comparisons.
What didn't hold up is the size of the resulting signal — even with correctly-shrunk
per-pitch-type command/stuff rates, the marginal information beyond the existing 184
physics/usage/wOBA-adjacent features is too small and inconsistent across outer folds
to move `k_rate` MAE reliably. This is consistent with per-pitch-type wOBA/xwOBA/RV
(the next-cheapest tier, already computed at Level 1 but never rolled) likely carrying
similar or better signal per feature added, since RV already blends location, count
state, and pitch-type shape into a single outcome-weighted number — a natural next
step if this line of research continues.

## Known limitations / follow-ups if revisited

- **Prior strength was not tuned.** 200 pitches was chosen as a reasonable single value
  across all three stats and eight pitch types; a per-stat (or per-pitch-type) sweep
  might recover more signal, particularly for pitch types whose crossing pitch counts
  are far from 200 (e.g. `ff` stats cross around 100-350, `cu`/`fc` don't reliably
  cross at all in range).
- **Window choice used the nearest-candidate heuristic**, not a full nested inner
  selection per pitch type/stat (the standard Step-9 protocol). A proper per-family
  nested window search, as used for the aggregate rates, was out of scope for this
  Tier-1 pass but is the natural next step if the signal looked more promising.
- **Two-strike put-away rate by pitch type and CSW%/whiff splits vs. R/L** (flagged as
  lower priority in the original proposal) were not attempted here and remain
  untouched.
- Tier 2 (wire the already-computed `{pt}_woba` / `{pt}_xwoba` into rolling) and Tier 3
  (`{pt}_hard_hit_rate` / `{pt}_barrel_rate`) were explicitly out of scope for this pass
  per the agreed plan; Tier 2 was subsequently run (see below), Tier 3 was not
  attempted.

## Update: Tier 2 — per-pitch-type wOBA / xwOBA

Ran the identical analysis loop for `{pt}_wOBA` / `{pt}_xwOBA` (already computed at
Level 1, never rolled). Same generalized rolling helper
(`add_pitch_type_rate_features`), same nested lift-test harness
(`models/Strikeout-Model/research/pitch_type_woba_lift.py`), same predeclared bar.

### Stabilization: even worse-sampled than Tier 1, as expected

`{pt}_wOBA`/`{pt}_xwOBA` are denominated in **PAs ending on that pitch type**, not
pitches thrown — a median of 2-7 PA per start vs. 12-31 pitches/start for the Tier 1
rate stats. Result: **none** of the 16 (pitch type x stat) combinations reliably
stabilize (`ci_low` never crosses `r=.50`) even at the widest tested denominator (400
PA, i.e. 20-45 typical starts). Several combinations (`ff`/`si`/`fc`/`sl`/`ch`/`fs`
`wOBA`) don't even reach the **median** crossing in range. This is the most extreme
version of the small-sample problem in this whole research line — confirmed, not
assumed.

### Lift test: `top3`-usage shrunk variant clears the mechanical bar (but marginally, and fragile)

| configuration | n features | mean MAE improvement | min MAE improvement (worst fold) | both folds improve? |
|---|---|---|---|---|
| `production_plus_pitch_type_woba_shrunk_top3` (ff/si/sl only, shrunk) | 190 | **+0.000028** | **+0.000020** | **Yes** |
| `production_plus_pitch_type_woba_unshrunk` (all 8 types, no shrinkage) | 200 | -0.000053 | -0.000142 | No |
| `production_plus_pitch_type_woba_shrunk` (all 8 types, shrunk) | 200 | -0.000258 | -0.000410 | No |

`production_plus_pitch_type_woba_shrunk_top3` is the **first configuration across
both tiers to mechanically clear the predeclared both-outer-fold MAE bar.** Flagging
several reasons for caution before treating this as a real promotion:

- **The improvement is tiny in absolute terms** (0.00002-0.000035 MAE on a target with
  mean MAE ≈0.078, i.e. roughly a 0.03-0.04% relative improvement) — an order of
  magnitude smaller than the discipline-lift promotion that produced the current 184
  (`step11_discipline_registry_freeze.md`).
- **Inner selection did not consistently prefer this configuration.** LightGBM's own
  inner-fold model selection picked `production_plus_pitch_type_woba_shrunk` (the
  full 8-pitch-type set, which then *failed* both outer folds) on `outer_2024_h1`, and
  only picked `..._shrunk_top3` on `outer_2024_h2`. The promotion rule as coded checks
  raw outer MAE per configuration regardless of inner selection (matching
  `lgbm_lift_promotion.py`'s existing methodology exactly), so it clears mechanically,
  but a human reading the inner-selection column would not have picked this
  configuration with foresight on the first fold.
- Restricting to the three highest-usage pitch types (not shrinkage) was what mattered
  here — full-8-type shrunk *lost* to production on both folds. That is a different
  conclusion from Tier 1, where shrinkage (not usage-restriction) was the thing that
  helped.
- Chrono bake-off does **not** support this configuration: on the single train
  ≤2024-08-05 / test >2024-08-05 split, `..._shrunk_top3` is the **worst** of the four
  configurations (MAE 0.079412, worse than plain production's 0.079355), while the
  *unshrunk all-8-type* set is best there (0.078999) — the opposite ranking from the
  nested outer-fold result.

Full detail: `artifacts/feature_research/pitch_type_woba_lift/`.

### Verdict: HOLD, do not promote without your sign-off

Per the plan, a clearing result should be reported and confirmed with you before any
`registries.py`/freeze change — not auto-promoted. Given the inconsistency between the
nested outer-fold result (top3 clears) and the chrono bake-off (top3 is worst), and
the tiny absolute effect size, my recommendation is **do not promote this** as-is. If
you want to pursue it further before deciding, the next steps would be: (1) a proper
per-pitch-type nested window search instead of the nearest-candidate heuristic used
here, (2) a prior-strength sweep (100 PA was not tuned), and (3) the secondary
`expected_K` product-level check, none of which were run given how fragile the outer
result already looks.
