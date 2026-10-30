# PA model briefing: baseline mechanics + architecture direction

> Point-in-time briefing captured 2026-10-29. Live plan lives in
> `docs/EXECUTION_BACKLOG.md` (Session Snapshot). This file is reference
> material only — it authorizes no fitting, no execution, and no policy change.
>
> Provenance: two coworker briefings (2026-10-29), code inspected at commit
> `0cd8175c`. Part A **corrects earlier explanations — including earlier
> briefings by the same author — that blurred the aggregation distinction**:
> the registered baseline mixes binomial conditionals at averaged slot
> probabilities, and is NOT a fully heterogeneous Poisson-binomial model.

---

# Part A — How the current baseline works

Establish a trustworthy score first, then improve one part at a time. The key
is to separate **probability**, opportunity, and aggregation: how likely is a
strikeout on a PA, how many PAs will the starter face, and how do those
combine into a K-count distribution?

## A1. What feeds the current predictions?

The baseline combines three inputs:

| Input | What it supplies | Current limitation |
|---|---|---|
| Historical completed-PA table | Pitcher, batter, dates, PA identities, strikeout indicators and event labels | Not a pitch-by-pitch forecasting model |
| Reconstructed projected lineups | Nine ordered opposing hitters, reconstructed from prior team-games | Not an archived, posted pregame lineup |
| Existing BF forecast parquet | A probability distribution over starter batters faced | Simple empirical workload model, not a rich hook-point model |

The outcome-label code maps Statcast events into four classes: strikeout;
walk/HBP/interference; in-play-out/error-related outcomes; and hit. The exact
mapping — not the abbreviated class name — is authoritative. Player IDs
identify whose history to retrieve; they are not themselves numeric model
features. [Model and taxonomy code](https://github.com/Cbkaplinger/MLB-Props/blob/0cd8175c591dcae6af162ee360d5d76c3ff14e9f/research/offseason_2026/pregame_pa_ext/m0_multiclass.py)

The new runner consumes existing parquets. It does not itself scrape Statcast,
predict roster availability, or train a workload model.

## A2. What are the historical features?

The learned reference currently uses just eight features:

| Feature | Meaning |
|---|---|
| `p_pitcher_prior_w150` | Pitcher's historical K rate, shrunk toward the league rate |
| `p_batter_prior_w150` | Batter's historical strikeout rate, similarly shrunk |
| `lg_rate` | League historical strikeout rate |
| `n_prior_pitcher` | Pitcher PA support behind the history |
| `n_prior_batter` | Batter PA support behind the history |
| `cold_start` | Whether either player lacks prior observations |
| `ew_pitcher` | Pitcher's exponentially weighted K rate |
| `ew_batter` | Batter's exponentially weighted strikeout rate |

These are explicitly defined in the [shared feature
constructor](https://github.com/Cbkaplinger/MLB-Props/blob/0cd8175c591dcae6af162ee360d5d76c3ff14e9f/research/offseason_2026/pregame_pa_ext/adapter.py).

### Shrinkage

For a player with k prior strikeouts in n eligible PAs and league rate p_L:

    p_hat = (k + 150 * p_L) / (n + 150)

The 150 acts as league-rate pseudo-observations. A small sample stays near the
league rate; a large sample is driven more by the player's history.

That is why retaining denominators matters. Two 30% rates supported by 10 and
1,000 PAs should not be treated as equally established.

### Recent form

The EW features use a 90-day half-life. Their ratio is equivalent to:

    p_hat_EW(t) = sum_i 2^(-(t-t_i)/90) * y_i  /  sum_i 2^(-(t-t_i)/90)

Recent observations receive more weight, but the current construction has no
hard rolling-lookback cap. The corrected state builder filters observations
strictly before each requested date. [Forecast-state
implementation](https://github.com/Cbkaplinger/MLB-Props/blob/0cd8175c591dcae6af162ee360d5d76c3ff14e9f/research/offseason_2026/pregame_pa_ext/forecast_states_v2.py)

These are not yet handedness splits, arsenal features, velocity trends, or
pitch-location statistics.

## A3. What does regularized multinomial logistic mean?

It learns how those eight features relate to the four possible outcome
classes.

For each class c, it forms a linear score:

    z_c = b_c + beta_c^T x

Softmax converts the scores into coherent probabilities:

    P(Y=c | x) = exp(z_c) / sum_j exp(z_j)

The probabilities sum to one. The strikeout forecast is simply the probability
assigned to class 0.

The implementation:

1. Fits a `StandardScaler` on training features.
2. Fits logistic regression with `C=1.0`, `solver="lbfgs"`, and
   `max_iter=1000`.
3. Applies the stored training scaling and fitted coefficients to forecast
   rows. [Fitting and prediction
   functions](https://github.com/Cbkaplinger/MLB-Props/blob/0cd8175c591dcae6af162ee360d5d76c3ff14e9f/research/offseason_2026/pregame_pa_ext/m0_multiclass.py)

Regularization penalizes overly large coefficients, reducing the incentive to
fit unstable relationships. In scikit-learn, smaller `C` means stronger
regularization. This is a fixed-hyperparameter baseline, not a tuned model.
[scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html)

It learns weights; it does not memorize a separate empirical rate for every
sparse pitcher-batter pair.

## A4. How does workload become a distribution?

The current BF artifact is an empirical forecast based on earlier starts:

- Use the pitcher's historical workload distribution when sufficient history
  exists.
- Otherwise use the pooled league distribution.
- Smooth the category probabilities.
- Preserve an overflow category and apply the declared tail extension.

It is lineup-free and uses starts strictly before the forecast date. It does
not currently predict the hook from pitch count, bullpen availability, injury
restrictions, or the developing game state. [Workload
definitions](https://github.com/Cbkaplinger/MLB-Props/blob/main/research/offseason_2026/bf_workload_v1/report_v2.json)

Conceptually, it produces:

    P(BF = 15), P(BF = 16), ..., P(BF = 25), ...

Both references receive the identical forecast. Therefore, the upcoming
comparison cannot tell us whether that workload model is good — it isolates
the PA-probability component.

## A5. How do PA probabilities become total Ks?

### Current baseline

Suppose the projected lineup provides nine strikeout probabilities:

    p_1, p_2, ..., p_9

For each possible workload n, the registered H3-style aggregation cycles
through the lineup and takes the mean probability over the first n
opportunities:

    p_bar_n = (1/n) * sum_{j=1..n} p_slot(j)

It then uses a binomial conditional:

    K | N=n ~ Binomial(n, p_bar_n)

and mixes over workload:

    P(K=k) = sum_n P(N=n) * P(K=k | N=n)

That construction is documented in the [adapter's registered aggregation
description](https://github.com/Cbkaplinger/MLB-Props/blob/0cd8175c591dcae6af162ee360d5d76c3ff14e9f/research/offseason_2026/pregame_pa_ext/adapter.py).

We are not just adding nine probabilities and calling the sum the final
forecast. We evaluate many possible workloads, obtain a conditional K
distribution for each, and weight them.

### What that approximation loses

A binomial at the average probability is not the same as summing
heterogeneous Bernoulli outcomes.

A Poisson-binomial conditional would instead model:

    K | N=n = sum_{j=1..n} Y_j,   Y_j ~ Bernoulli(p_j)

under conditional independence.

Both have the same conditional mean, but generally different variance and
shape. The repository has ordered-opportunity machinery for that alternative;
it is not interchangeable with the currently registered baseline.

> Status note added 2026-10-29: the exact Poisson-binomial aggregator was
> subsequently evaluated once as Question A (count-RPS delta -0.0003333461,
> challenger better; dev-only diagnostic, baseline NOT replaced) — see
> `results_count_agg_eval_v1/RESULT_RECORD.md` and the backlog Session
> Snapshot. It remains a development diagnostic, not the registered
> aggregation.

We should test such an aggregation change separately — not silently substitute
it while evaluating the PA model.

## A6. Lineup position and times through the order

These are related but distinct.

### Lineup position

The order affects which hitters appear in the first n opportunities. For
example, a workload ending early in the third trip through the lineup gives
the top slots more opportunities.

The existing cycled-prefix construction represents that ordering
approximately.

### Times through the order

The current eight-feature model does not explicitly change a hitter's
probability on the second or third encounter. The same projected matchup
probability is reused.

A future model could generate:

    p_{j,r} = P(K on PA | pitcher, batter, trip r, pregame features)

But later trips are observed only for pitchers who remain in the game. A naive
"third-trip rate" mixes familiarity, pitcher quality, workload selection, and
game conditions.

Likewise, actual pitches thrown or actual velocity during the target game are
unavailable to a pregame model. They require either a separate live model or a
declared simulation of future states.

## A7. How to expand feature families

The following is a proposed experiment structure — not a claim that these
features are already in this baseline.

| Family | Candidate inputs | Support and timing requirements |
|---|---|---|
| Handedness | Pitcher hand, batter side, platoon-specific K tendencies | Shrunk split rates and PA counts |
| Pitcher arsenal | Pitch mix, velocity, movement, whiff rates | Pitch-type denominators; prior-game data only |
| Batter contact | Chase, zone contact, swing-and-miss, pitch-type vulnerability | Correct denominators and sparse-sample handling |
| Recency/season | Prior-season, season-to-date, recent decay | No full-season averages attached to earlier games |
| Workload | Prior BF, pitches per start, rest, restrictions, bullpen state | Genuine pregame availability |
| Environment | Park, weather, umpire if known | Information timestamped by decision time |
| Opportunity | Lineup position, projected lineup uncertainty, TTO | Declared future-opportunity assumptions |

For rates, retain the numerator, denominator, window, and source cutoff. Do
not average game-level percentages indiscriminately.

For example:

    pooled whiff rate = sum(whiffs) / sum(swings)

not necessarily the unweighted mean of each game's whiff percentage.

Season-to-date averages must be recomputed as of the prediction date. A final
season average is future information for an earlier game.

## A8. How to isolate improvements

Use two distinct comparisons.

### Feature experiment

Keep the estimator and all other components fixed:

    Existing features
    versus
    Existing features + handedness family

Then repeat for another justified family. Report both PA-level scores and
downstream count-RPS.

### Model experiment

Keep the feature set and data fixed:

    Fixed multinomial logistic
    versus
    Fixed-configuration LightGBM

This tells us whether nonlinear modeling helps, rather than confusing model
capacity with newly added information.

After identifying a useful candidate, tune it using earlier chronological
validation periods. Compare it against its untuned version on a later
development period. Do not tune on the assessment results and then call the
same period independent validation.

"Out of the box" should mean a documented, fixed configuration — not
unrecorded library defaults that change across environments.

> Status note added 2026-10-29: the LightGBM-vs-logistic model experiment was
> already run under the equal-information contract (lgbm-equal-info v2
> closeout, 2026-10-16): NO DETECTABLE DEVELOPMENT ADVANTAGE at the registered
> contract; equal-information nonlinear PA challengers RETIRED pending a new
> registered reason. See the backlog Session Snapshot and
> `experiments/lgbm-equal-info-v2-closeout-2026-10-16/card.md`.

## A9. Leakage and shuffling: the actual rules

We need safeguards at several boundaries:

1. Feature history: only observations available before the forecast cutoff.
2. Training: historical rows get features constructed at their own cutoffs.
3. Preprocessing: scalers, imputers, feature selection, and encoders fit on
   training data only.
4. Validation: forward chronological splits — not randomly mixed PAs from the
   same future period.
5. Forecast identity: predictions remain attached to their generating keys.
6. Assessment: outcomes determine scores, not forecast eligibility or
   features.
7. Tuning: model selection cannot consume protected evaluation outcomes.
8. Lineup/workload provenance: neither may use the target game's realized
   opportunities.

Sorting or shuffling rows for a test is not inherently leakage. The danger is
moving future observations into training, losing feature/outcome alignment, or
changing historical aggregates because row order changed.

The current corrected state code excludes same-date and future observations
before aggregation. That is a conservative date-level boundary, not proof of
timestamp-perfect news reconstruction. [Cutoff
implementation](https://github.com/Cbkaplinger/MLB-Props/blob/0cd8175c591dcae6af162ee360d5d76c3ff14e9f/research/offseason_2026/pregame_pa_ext/forecast_states_v2.py)

## A10. The scorecard should keep three targets separate

| Target | What feeds it now | Evaluation |
|---|---|---|
| PA K probability | Eight historical rate/support features | Binary log loss, Brier, reliability |
| BF distribution | Prior-start empirical workload history | Distribution score, bias, coverage |
| Total starter K | PA probabilities + lineup ordering + workload mixture | Count-RPS, mean error, threshold reliability |

The current experiment measures the first and third while holding the second
fixed.

That is the right starting point. Finish this measurement, then isolate
workload quality, aggregation assumptions, and feature-family improvements in
separate comparisons. The many possible ideas belong in a small ordered
experiment queue — not in the current baseline PR.

---

# Part B — Architecture direction: stay PA-level, defer pitch simulation

**Stay at the plate-appearance level for the current model; do not replace it
with a pitch-by-pitch simulator now.** You can use pitch-level data to improve
PA probabilities without having to simulate every pitch. A PA-level simulator
is also a sensible intermediate option if we later need coherent joint
predictions for strikeouts, hits, walks, outs, and workload.

The important distinction is between the granularity of the data, the
prediction target, and the aggregation method. Those do not have to be the
same.

## B1. Pitch-level features do not require pitch-level simulation

We can build a pregame PA prediction from:

- Prior pitch velocity and movement.
- Pitch-type usage.
- Whiff and chase rates.
- Batter contact rates against pitch types.
- Handedness splits.
- Recent changes in arsenal or effectiveness.

The target remains:

> What is the probability of each outcome in this pitcher-batter plate
> appearance?

For example, a PA model could output:

| Outcome | Illustrative probability — not a project result |
|---|---:|
| Strikeout | 28% |
| Walk | 8% |
| Hit by pitch | 1% |
| Hit | 23% |
| Other outcome | 40% |

Historical pitch data help estimate those probabilities. We do not need to
generate a hypothetical first-pitch fastball, second-pitch slider, and so on
to obtain them.

The current model is much simpler: its eight features summarize historical K
rates, support, and recency. Pitch-level feature families would be later
additions, tested against that baseline — not a prerequisite for completing
it.

## B2. Three architectures, not two

| Architecture | What it does | Recommended role |
|---|---|---|
| PA probabilities + workload distribution | Combines matchup probabilities with possible BF totals | Current baseline |
| PA-level state simulation | Samples PA outcomes, advances lineup/game state, and models removal | Possible later joint-props challenger |
| Pitch-by-pitch simulation | Models pitch selection/outcomes, count changes, PA endings, and game state | Defer until a demonstrated need |

Baseball can be represented with event-based state-transition models; pitch
simulation is not required to model batting order and inning progression.
Georgia Tech's baseball Markov-chain teaching implementation is an example of
that event-level approach.
[isye.gatech](https://www.isye.gatech.edu/~jsokol/markovball)

### Why not pitch-by-pitch now?

It introduces additional things we would have to estimate and validate:

- Pitch choice and location.
- Swing/take decisions.
- Contact and foul probabilities.
- Count-dependent behavior.
- Ball-in-play outcomes.
- Pitch-count accumulation.
- Pitcher removal and substitutions.

A detailed simulator can still be systematically wrong at each of those
layers. More simulations reduce sampling noise around its assumptions; they do
not correct those assumptions.

The recommendation is to add that complexity only if the PA-level model
leaves a specific, measurable problem that simpler changes cannot address.

## B3. How PA probabilities price different props

For a statistic T, the end product must be a count distribution:

    P(T=0), P(T=1), P(T=2), ...

A half-line price follows directly:

    P(T > 4.5) = sum_{t=5..inf} P(T=t)

At an integer line, preserve three probabilities:

    P(win), P(push), P(loss)

The exact statistic and settlement rules determine the event.

### Strikeouts, hits, and walks

For a fixed sequence of PAs, each outcome can be counted using PA
probabilities. Under a declared conditional-independence assumption, count
distributions can be computed analytically rather than simulated.

A joint outcome generator can be written conceptually as:

    G_j(z_K, z_H, z_W)
      = p_{K,j} z_K + p_{H,j} z_H + p_{W,j} z_W + p_other,j

Multiplying these across PAs represents the joint count distribution under
those assumptions. Monte Carlo is one way to approximate the same
distribution; it is not the only way.

However, the current taxonomy is not yet suitable for pricing all these
contracts:

- Its walk class also includes HBP and interference.
- Its "in-play-out" class includes events such as errors and fielder's
  choices.
- Those categories cannot simply be relabeled "walks" and "outs."

The [actual taxonomy
mapping](https://github.com/Cbkaplinger/MLB-Props/blob/0cd8175c591dcae6af162ee360d5d76c3ff14e9f/research/offseason_2026/pregame_pa_ext/m0_multiclass.py)
is appropriate to inspect before extending targets.

### Outs recorded

Outs need more than a binary "this PA was an out" label:

- Some events produce multiple outs.
- Some outs occur on the bases.
- Some strikeouts do not result in the batter being retired.
- Pitcher removal determines where the pitcher's recorded-out count stops.

A coherent outs simulator therefore needs event/state transitions and a
removal model. It still does not necessarily need individual pitches.

Also distinguish pitcher props from batter props: a batter's full-game hits
depend on that team's offensive opportunities and opposing relievers — not
only the starting pitcher's BF distribution.

## B4. A PA-level simulator could eventually couple workload and performance

The current baseline supplies workload externally. A later state model could
instead follow:

    Pregame lineup and pitcher state
            |
            v
    Predict PA outcome probabilities
            |
            v
    Sample outcome and update counts/base-out state
            |
            v
    Estimate whether the pitcher remains
            |
            v
    Advance to next hitter or stop the starter's outing

That could couple walks, hits, strikeouts, and removal.

But replacing the external workload PMF with a removal process is a
substantive new model. We should compare it against the existing empirical
workload baseline, not assume greater realism means greater accuracy.

For now: finish the PA baseline result, then test workload and aggregation
improvements separately.

## B5. RotoGrinders integration already has a foundation

Two repository files were inspected through GitHub:

- [`src/Python/daily_lineups.py`](https://github.com/Cbkaplinger/MLB-Props/blob/main/src/Python/daily_lineups.py)
  contains RotoGrinders fetching/parsing and MLB identity-resolution
  machinery. It preserves projected/confirmed status, batting order, and
  ingestion time.
- [`pregame_lineup_capture.py`](https://github.com/Cbkaplinger/MLB-Props/blob/main/research/offseason_2026/pregame_lineup_capture.py)
  selects captured snapshots available before a timezone-aware forecast cutoff
  and returns explicit fallback reasons.

The research adapter currently defaults to `confirmed_only`. It also
implements `projected_allowed`, explicitly identified as a separate research
mode.

So yes: using RotoGrinders during the season is architecturally feasible
without a rewrite. But source code existing is not proof of a working
scheduled service. Before the season, we must test current-page parsing,
identity resolution, snapshot persistence, scheduling, and prediction wiring.

The parser depends on page structure, so it needs a preseason smoke test and
ongoing failure monitoring — not an assumption that today's code will work
indefinitely.

## B6. How to compare our lineup with theirs

Use the same games and the same decision times:

| Arm | Lineup source |
|---|---|
| A | Our prior-game reconstruction |
| B | RotoGrinders projection captured before cutoff |
| C | Confirmed lineup, only if available before cutoff |
| Diagnostic only | Eventual actual starting lineup |

Hold PA model, workload, aggregation, and eligibility constant.

Historical comparison is valid only where genuine timestamped snapshots exist.
A lineup fetched today or reconstructed afterward cannot prove what
RotoGrinders displayed before an old game. Missing historical snapshots should
remain missing.

The eventual actual lineup is useful as diagnostic truth, not as an actionable
historical input.

## B7. How to measure lineup accuracy

Do not evaluate only "did we get nine names?"

Track:

- Player-set accuracy: which starters were correctly included.
- Exact-slot accuracy: whether each hitter was placed correctly.
- Entire-lineup accuracy: all nine hitters and slots correct.
- Availability: percentage of scheduled starts with a usable forecast.
- Freshness: age of the selected snapshot.
- Late changes: revisions after the prediction cutoff.
- Identity failures: unresolved players, opposing-team errors, and
  doubleheader collisions.
- Downstream impact: change in K probabilities and count-RPS.

A lineup can have imperfect exact-slot accuracy but little effect on K pricing
— or one missing high-contact hitter can materially change it. Measure both
lineup correctness and forecast consequences.

The operational policy should preserve immutable snapshots, distinguish
projected from confirmed, reforecast when permitted lineup changes arrive, and
abstain or use a declared fallback on unresolved identities. Do not silently
substitute a later confirmed lineup into an earlier prediction.

## B8. Direction for the project

No architecture pivot is warranted now:

1. Complete the current Ref0-versus-Ref1 PA baseline.
2. Measure the workload baseline separately.
3. Add justified pitch-derived feature families.
4. Validate the existing RotoGrinders capture path before the season.
5. Consider a PA-level joint simulator when expanding to multiple props or
   demonstrating a workload-dependence limitation.
6. Revisit pitch-by-pitch simulation only if it addresses a measured
   deficiency.

The instinct is right: game-level averages are too coarse for the intended
matchup model, but simulating every pitch is not the necessary next step.
PA-level targets with well-supported pitch-derived features are the practical
middle ground.

---

# Part C — Chat 2 async protocol + modeling-change discipline

*(Third coworker briefing, captured 2026-10-29.)*

Keep Chat 2, but use it **asynchronously**: parked while Chat 1 builds, active
at a published checkpoint, then parked again. Independent review has caught
real scoring and identity defects; the problem has been repeated stale
handoffs and reviewing work before it was published — not the existence of a
reviewer.

For the modeling questions: keep `StandardScaler` and the current logistic
recipe unchanged until the baseline is measured. Transformations, smoothing,
monotonic constraints, and alternative models are useful experiments, but none
is automatically an improvement.

GitHub status at capture time: PR #52 is still open at `0cd8175c`. The active
scope remains assessment preparation followed by the population-versus-
multinomial comparison — not a model tournament.
[PR #52](https://github.com/Cbkaplinger/MLB-Props/pull/52)

## C1. How Chat 2 should operate

Use this division:

| Chat 1 | Chat 2 |
|---|---|
| Implements one agreed task | Does not edit builder files |
| Publishes a complete SHA and evidence | Fetches and reviews that exact SHA |
| Responds to consolidated findings | Distinguishes blockers from follow-ups |
| Executes only authorized procedures | Verifies resulting evidence independently |

For the present task, Chat 2 should review the corrected preparation script
once it is published. It should not poll, review mid-edit working trees, or
reopen unchanged findings.

Afterward, park it until the assessment artifact or real baseline result
exists. That preserves independence without making every development step a
two-agent meeting.

## C2. Is `StandardScaler` best?

No universal best scaler exists. `StandardScaler` is a reasonable baseline: it
subtracts the training mean and divides by the training standard deviation. It
is sensitive to outliers.
[scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html)

Scaling matters here because regularization penalizes coefficients; feature
units influence how those penalties operate. It does not make a variable more
informative, and logistic regression does not require normally distributed
inputs.

Possible later comparisons:

| Choice | Why test it? | Caution |
|---|---|---|
| Standard scaling | Simple reference | Large outliers affect scale |
| Robust scaling | Reduce sensitivity to extreme feature values | Does not remove the outliers |
| Log transform, then scaling | Compress highly skewed support counts | Must handle zero and preserve meaning |
| Power transform | Learn a skew-reducing transformation | Additional fitted preprocessing |
| Quantile transform | Flexible distribution reshaping | Can saturate extreme values and distort distances |

Scikit-learn documents these trade-offs directly.
[scikit-learn](https://scikit-learn.org/dev/auto_examples/preprocessing/plot_all_scaling.html)

The first transformation candidate would be `log1p(n_prior_pitcher)` and
`log1p(n_prior_batter)`, not replacing every feature's scale. "Ten more
observations" plausibly matters differently at support 10 versus 10,000. That
is a hypothesis to test, not a current implementation order.

All fitted transformations must learn their parameters from training data
only.

## C3. How to shape features sensibly

Choose transformations because they express a relationship — not because a
long list is available.

| Transformation | Potential baseball use | What it can lose or distort |
|---|---|---|
| `log1p(x)` | PA counts, pitch counts, support | Changes interpretation of increments |
| Logit of a smoothed rate | Probability effects expressed in log-odds | Requires protection near 0 and 1 |
| Recent minus long-run value | Velocity or K-rate change | Noisy when recent support is small |
| Change per elapsed time | Trend in velocity or usage | Requires strictly backward-looking estimates |
| Absolute deviation | Magnitude of a change | Removes direction |
| Splines | Smooth nonlinear effects without a tree model | Adds flexibility that needs validation |
| Interaction terms | Handedness x arsenal; batter weakness x pitch mix | Sparse combinations can overfit |

For example, a 2 mph increase and a 2 mph decrease should not automatically
become the same `abs(change)` feature. Retain the signed change unless a
mechanism specifically concerns magnitude.

Do not use centered rolling windows, future observations, or a trend
calculated across the eventual full season.

## C4. Should gradient boosting be monotonic?

Separate two concepts.

### Distribution coherence: required

Regardless of estimator:

- Probabilities must be valid.
- A PMF must sum to one.
- CDFs must be nondecreasing.
- Higher K thresholds cannot have higher exceedance probabilities.

These are mathematical requirements.

### Feature-response monotonicity: optional

A constraint such as "higher pitcher K tendency cannot lower predicted K
probability, holding other inputs fixed" is a modeling assumption.

LightGBM supports increasing, decreasing, or unconstrained feature
relationships. Its documentation also warns that simpler constraint methods
can overconstrain predictions.
[lightgbm.readthedocs](https://lightgbm.readthedocs.io/en/latest/Parameters.html)

Do not impose blanket constraints:

- Historical support is not monotonically related to skill.
- Rest can have nonlinear effects.
- Velocity does not universally imply the same K effect across arsenals.
- Handedness categories do not have a natural numeric order.

For a binary K model, selected rate-feature constraints could be a reasonable
challenger. For multinomial probabilities, constraining individual class
scores does not automatically establish monotonicity of the final strikeout
probability after normalization. Verify the installed library's support and
test the actual output behavior.

Compare constrained versus unconstrained models on the same data. Do not
declare constraints correct merely because their narrative sounds intuitive.

## C5. Other smoothing methods

Several different kinds of "smoothing" already exist. Keep their purposes
distinct:

| Method | Purpose | Candidate improvement |
|---|---|---|
| League-prior shrinkage | Stabilize sparse player rates | Estimate shrinkage strength on earlier development data |
| Exponential decay | Emphasize recent history | Compare a small, predeclared set of half-lives |
| Hierarchical pooling | Share information across related players/splits | Separate pitcher, batter, handedness and league effects |
| Smoothed workload histogram | Stabilize BF-category probabilities | Blend player and league distributions gradually |
| State-space model | Track changing latent skill | More complex; justify after simpler references |
| Output calibration | Correct residual forecast probabilities | Separate from smoothing historical inputs |

For workload, a useful future hypothesis is continuous pooling:

    P(N=n) = w * P_pitcher(N=n) + (1-w) * P_league(N=n)

where w increases with reliable historical support. That avoids an abrupt
transition from league to pitcher history at a fixed count threshold.

It must be compared against the existing empirical forecast — not assumed
better.

## C6. Will logistic regression be adjusted?

Yes, after obtaining the fixed recipe's real score.

Use this progression:

1. Current fixed logistic reference.
2. One justified representation change, such as log support.
3. A bounded regularization search.
4. A nonlinear challenger on the same feature set.
5. Selected new feature families.

For tuning, use earlier chronological validation periods; assess the chosen
configuration on a later period. The same data cannot serve both
hyperparameter selection and an unbiased assessment of that selection. Nested
evaluation separates those functions.
[scikit-learn](https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html)

Do not change scaler, features, regularization, training history, and
workload simultaneously.

## C7. Training-loss charts

Yes — but the chart must come from real recorded evaluations.

### LightGBM

Record training and chronological-validation metrics at every boosting
iteration with `record_evaluation`. LightGBM explicitly supports that history
collection. Early stopping uses validation improvement and therefore belongs
inside model selection, not on the final assessment period.
[lightgbm.readthedocs](https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.record_evaluation.html)

### Current logistic regression

The present fitting interface does not provide an equivalent ready-made
per-iteration validation curve. For a future instrumented run, genuine
optimization history can be recorded using an appropriate supported fitting
route.

Do not:

- Fabricate a historical curve for an existing fit.
- Treat separate fits with increasing `max_iter` as one uninterrupted
  training trajectory.
- Change the solver solely to make an attractive chart without labeling the
  change.

For the first baseline, more useful figures are:

- Reliability plots.
- Out-of-time loss by month.
- Loss versus historical support.
- Workload predicted versus observed distributions.
- Count-CDF/threshold calibration.
- Paired per-start score differences.

A training curve diagnoses fitting behavior; it does not establish
forecasting value.

## C8. A small comparison plan — not "every model"

After the current result, use a limited ladder:

| Candidate | Purpose |
|---|---|
| Population rate | Minimum control |
| Binary logistic | Direct K-versus-non-K learned reference |
| Existing multinomial logistic | Test broader PA-outcome modeling |
| Logistic with one justified nonlinear representation | Test feature shape |
| Fixed-configuration LightGBM | Test nonlinear interactions |
| Bounded tuned winner | Test whether tuning adds reliable value |

Use the same eligible observations and forecast-time information. Keep KNN
and neural networks deferred unless simpler results suggest a specific reason.

Model comparisons should include performance, calibration, coverage, runtime,
and implementation complexity — not just the best headline score.

> Status note added 2026-10-29: the fixed-configuration LightGBM rung of this
> ladder was already run under the equal-information contract (lgbm-equal-info
> v2 closeout, 2026-10-16: NO DETECTABLE DEVELOPMENT ADVANTAGE; challengers
> RETIRED pending a new registered reason). Re-entering that rung requires a
> new registered reason and a new pre-registered challenger.

## C9. How to improve each lane

| Lane | First useful improvements | Keep fixed during its experiment |
|---|---|---|
| PA K probability | Valid longer history; rate/support representation; handedness; pitch-derived contact/arsenal features | Workload and aggregation |
| BF distribution | Pooled control; continuous shrinkage; recency; pregame workload restrictions and role | PA model and aggregation |
| Total K distribution | Registered binomial approximation versus heterogeneous PA aggregation; opportunity/TTO modeling; later removal coupling | PA/workload inputs wherever possible |

For total K, preserve an important question: did a component improve its own
metric but worsen count-RPS? That is why every component experiment also needs
downstream evaluation.

## C9a. Immediate direction

Do not implement the ideas above yet.

- Chat 1: finish the corrected preparation script and its synthetic checks.
- Chat 2: review that published script once, then park pending authorized
  preparation evidence.
- Both: keep the current model recipe frozen.
- Next empirical milestone: real Ref0-versus-Ref1 scores.
- After that: choose one next experiment from the observed weakness.

Chat 2 is needed as an independent checkpoint, not as a second builder. And a
measured baseline is needed before turning a reasonable list of modeling ideas
into a large, expensive search.
