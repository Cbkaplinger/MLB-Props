# DRAFT prereg — PA-K chronological baseline (2026-10-07)

> **Status: DRAFT.** Not frozen, not authorized, not scored. Frozen prereg is
> authored from this draft only after owner authorization. Origin: owner
> order 2026-10-07 ("PA-K Chronological Baseline Readiness — Return and
> Stop"). No scored run before that authorization.

## Question

Given information available before the game, what is the probability that a
plate appearance against this (first) pitcher ends in a strikeout?

## 1. BF record closure (context)

The training-policy result (2026-10-07: pooled paired RPS −0.2629
[−0.3345, −0.1997], arm A reproduced to 4.0e-13) establishes **expanding
strictly-pre-origin training as the preferred research comparator** for
subsequent BF experiments — NOT a production promotion. Index-feature
interactions and LightGBM remain PARKED. September short-outing
underprediction remains an UNRESOLVED diagnostic (q-gap −0.0132 after
expansion). This PA lane adopts expanding training by default.

## 2. Identity and target (frozen)

- **Source:** approved sha-verified 2023 + 2022 Savant parquets, read via a
  dedicated explicit-column loader (`pa_frame`), NOT `_unified_pitches`
  (which collapses 119 → 11 columns and drops `batter`/`stand`).
- **PA identity:** (game_pk, at_bat_number) — verified unique in 2023
  (184,104 terminal PAs; uniqueness asserted fail-loud at build).
- **Terminal PAs:** rows with non-null `events`, excluding `truncated_pa`
  (272 rows; incomplete PAs are exclusions, never silent).
- **Target:** y = 1 iff `events ∈ {strikeout, strikeout_double_play}`
  (both count as a pitcher K and a batter K). All other terminal events 0.
- **Population (PRESPECIFIED): first-pitcher PAs only** — joined to the
  spine first-pitcher identity (4,860 appearance rows in 2023). Aligns the
  PA lane with the BF workload lane for the eventual K-count combination.
  All-pitcher PAs are a different population, deferred, never mixed.
- **Population counts (2023, measured):** 106,317 first-pitcher terminal
  PAs; 23,508 K (22.11%). Eval windows (identical to the BF lane):
  Apr-Jun [04-15, 07-01): 45,524 PAs / 9,987 K (21.94%); Jul: 16,065 /
  3,556 (22.14%); Aug: 17,954 / 4,003 (22.30%); Sep+ [09-01, 10-01):
  17,072 / 3,811 (22.32%). Training pre-04-15: 9,136 / 2,031 (22.23%).

## 3. Pregame information contract (frozen)

- Features use ONLY games with game_date strictly before the PA's game
  date. No same-game updates, realized BF, pitch count, score state,
  `n_priorpa_thisgame_player_at_bat`, or future outcomes.
- Completion rule: a prior game contributes only if the training window
  contains its completed record; a calendar-earlier but unfinished game is
  unavailable (enforced by training-window membership, tested).
- Cold-start taxonomy (prespecified, mutually exclusive):
  - `career_debut` / `season_debut` / `insufficient_history` (prior n
    below the frozen shrink weight) -> league/training-mean fallback;
  - `failed_join` (batter missing from the identity build) -> structural
    exclusion, counted in the manifest, never imputed.

## 4. Two baseline arms (frozen formulas)

Both arms use identical rows, identical eval windows, expanding
strictly-pre-origin training (per-origin refit; April inputs coincide).

**Comparison type (frozen statement):** this is a **baseline-versus-
richer-model comparison**, NOT a same-information architecture test.
Arm B's frozen feature list is a strict superset of arm A's inputs
(A consumes p_p, p_b, lg; B additionally consumes history-depth counts,
pitcher hand, batter hand, and the hand-mismatch flag). A win for B
therefore tests the combined model+information package; architecture is
not isolated. A loss for B does not invalidate the added information.

**April assertion (frozen, corrected per owner 2026-10-07):** arms are
DIFFERENT models — their predictions are NOT asserted equal. What is
asserted: (a) identical shared inputs (same league rate, same prior-rate
tables, same eval rows) for both arms in April; (b) repeated fits on the
same training frame reproduce identical predictions within 1e-12
(determinism check); (c) row identities identical across arms.

- **Arm A — shrunk matchup-rate baseline (train-only):**
  - pitcher rate p_p = (K_prior + w·lg) / (PA_prior + w), w = 150 (frozen);
  - batter rate p_b = (K_prior + w·lg) / (PA_prior + w), w = 150 (frozen);
  - league rate lg = training-window K share (prior rows strictly before
    the origin, from 2023 train rows + 2022 full season);
  - p_A = sigmoid(logit(p_p) + logit(p_b) − logit(lg)) (log5 additivity).
- **Arm B — regularized logistic:** L2 logistic (sklearn, C = 1.0 frozen,
  max_iter 5000; NO C search, no calibration layer) on train-standardized
  features (training-only medians/means/scales, same conventions as the
  hazard lane).
- **Feature list (frozen, all pregame):** logit(p_p), logit(p_b),
  logit(lg), log1p(pitcher_prior_PA), log1p(batter_prior_PA),
  p_throws (R=1/L=0), stand (L=1/R=0), mismatch = 1{p_throws=R &
  stand=L}. Batter hand (`stand`) IS available in the raw parquet.
- **2022 usage (frozen):** the logistic TRAINS on 2023 PAs strictly
  before the origin only (matching the BF lane's 2023-labels-only
  convention); 2022 enters ONLY through prior-rate aggregates (league
  rate + per-entity rates), never as training rows.

## 5. Evaluation contract (frozen)

- **Primary:** pooled paired log-loss difference (B − A) on identical
  rows; date-clustered bootstrap, 2,000 resamples, seed 20261001;
  pitcher-cluster sensitivity arm. **Gate (pass/fail): 95% CI entirely
  below 0 -> arm B is the research benchmark; otherwise arm A retained.**
- **Secondary:** Brier; reliability in prespecified bands
  ([0,.15),[.15,.20),[.20,.25),[.25,.30),[.30,1]) with counts + Wilson
  intervals; ROC-AUC (discrimination only); boundary-report counts.
- **Clipping:** probabilities clipped to [1e-6, 1−1e-6] for log loss;
  clip counts reported.
- Row-identity hash across arms; per-window tables; pooled metrics from
  pooled row-level losses. 2023 evaluation is DEVELOPMENTAL.

## 6. Matchup vs count claims (separation)

- Observed pitcher-batter matchups support **conditional PA diagnostics
  only**. They do NOT establish a deployable pregame xK: the realized
  batter identities and counts faced are not pregame knowledge.
- A deployable count forecast later requires a pregame lineup assumption/
  forecast combined with BF uncertainty (BF lane output). No summing
  over realized PAs may be presented as pregame xK.
- Ladder settlement convention (recorded): "6+" ≡ "over 5.5" (same event,
  minimum_k = 6); integer lines can push, half-lines cannot; original
  market labels preserved in the market layer.

## 7. Readiness tests (required green before any scored run)

1. identity uniqueness (duplicate (game_pk, at_bat_number) raises);
2. target mapping (strikeout & K-DP -> 1; walk/single/field_out -> 0;
   truncated_pa excluded and counted);
3. leakage: same-date game outcomes do not alter that game's features;
   a future-outcome perturbation leaves features unchanged;
4. cold starts: unseen pitcher/batter -> training-mean rates, prior_n=0;
   season-debut flag distinct from failed_join;
5. row parity: arms score identical rows (hash);
6. train-only transforms: standardization stats from train rows only;
7. April inputs: expanding and pre-04-15 training coincide for the April
   origin (identical training frames; shared inputs asserted equal);
   repeated fits reproduce identical predictions within 1e-12; cross-arm
   prediction equality is NOT asserted (different models by design).

## Blockers / notes

- `_unified_pitches` drops `batter`/`stand` -> PA lane uses its own
  explicit-column loader (raw parquet columns verified present).
- 2022 season file lacks... (no blocker: 2022 has batter/stand too).
- Parked-repo policy: all edits in main-active only; the copies made in
  the parked original repo during acquisition are frozen as-is and will
  be reconciled by review, not edited further.
