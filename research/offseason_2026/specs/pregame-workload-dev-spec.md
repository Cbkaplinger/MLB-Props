# Pregame Workload Development Specification -- coverage, leakage tests, workload distribution (DRAFT v2.2)

Status: **DRAFT -- planning only. NO execution authorized.** v2.2
(correctness-and-attribution revision) fixes the debut rule, separates
identity/history from capacity reset from debut status, rewords EWMA,
requires distinct starts/relief summaries, adds BulkBot claim-level
attribution, makes L6 a property of the NEW fitting pipeline, and
defines the staged coverage experiment. The spine/workload_spine.py
implementation and its synthetic tests are submitted for CODE REVIEW
only; no real-data fitting or scoring.

## 0. Investigation inputs (read-only, owner-approved lookback)

Saved in `%TEMP%\nonoracle_evidence\` (hashes verified; no fitting):

- `leakage_investigation.json`: (1) outcome-dependent feature-row
  existence CONFIRMED (pitcher_rolling row existence == current-game
  PA>=9 outcome, bidirectional); (2) career-debut labels contaminated
  (248 of 328 have 2022 appearances); (3) park factors prior-season
  only by construction (history-truncation test still mandatory).
- `older_history_investigation.json` (local Statcast 2015-2021, read
  only): of the 80 pitchers "not observed in 2022", **17 have earlier
  local pitching appearances** (last prior season: 2015 x1, 2018 x3,
  2019 x2, 2020 x2, 2021 x9 -- including one 6-year-gap case), and
  **63 remain history left-censored** (no pitching appearance in local
  2015-2022 coverage). In total, at least 265 of the 328
  "career debut" rows had prior MLB pitching appearances.

**Retraction (owner-directed):** the earlier claim "80 true MLB
debuts" is withdrawn. The 80 are relabeled "not observed in 2022"; 17
are "history backfilled from local coverage"; 63 remain "history left
censored" (earlier appearances may exist outside local coverage, e.g.
pre-2015). **No row may be labeled MLB career debut unless coverage or
an independent historical source (e.g. Retrosheet event files)
supports it.** Labels refer to first MLB PITCHING appearance; a prior
position-player career is a different fact and was not checked.

## 1. Objective and estimand distinctions

Three preregistered questions (unchanged from v1): **coverage**
(outcome-independent history builder), **uncertainty** (workload
distribution vs strikeout tails), **transfer** (Opening Day and
next-season). Distinctions locked now:

- The modeling assumption is **"normal intended workload, subject to
  performance and managerial removal"** -- not "full workload".
- **Conditional projection** (expected strikeouts assuming no
  unexpected injury interruption) is a legitimate research target but
  must be LABELED as conditional; it is not automatically the
  unconditional actual-game strikeout probability.
- **Actual-game distribution** (probabilities for the strikeouts
  ultimately recorded) is the pricing-relevant target; **settlement**
  (what a given book pays/voids, e.g. starting-pitcher protection
  rules) is a third, separately versioned layer. Book settlement
  rules change over time and are versioned independently of the
  probability model.
- Calibration means consistency between forecast distributions and
  the observations they are intended to predict (proper scores).
- The next scientific objective is **better out-of-fold count
  probabilities** -- not PnL maximization on repeatedly inspected
  data. PnL evaluation comes later as five separate reports
  (workload accuracy/uncertainty; strikeout probability quality;
  selection and executable price; same-book CLV; settlement-adjusted
  PnL).

## 2. Part A -- outcome-independent forecast spine and history builder

### 2.1 Spine (unchanged from v1; identity definition frozen v2.2-review)

Forecast rows = all first pitchers of a game; current-game outcomes
never gate row existence or feature availability. Join failures are
their own label, never silently coerced.

**First-pitcher identity (frozen):** the ONLY permitted definition is
the canonical `Python.pitcher_features._starter_keys`: (game_pk,
pitcher) pairs for the pitcher who opened EACH half of inning 1,
ordered by (inning_topbot, at_bat_number, pitch_number). Grouping by
game alone returns only the away-side starter and is FORBIDDEN. The
spine's `first_pitcher_keys` is a thin wrapper that adds game_date
(single-valued per game, fail loud), side (Top/Bot of the opened
half), and `is_home` (home team pitches the Top), and reconciles
against the canonical keys (fail loud on divergence). A mid-PA
substitution in the first PA selects the pitcher who BEGAN the half,
never the completer. A game missing either inning-1 half fails loud
(explicit quarantine by the caller, never a silent drop). No
competing starter definition may be introduced.

**`is_start` derivation (frozen):** `is_start` is determined
solely by membership in the canonical first-pitcher key set.
Position-player status is a separate attribute and does not
override that classification. No position-player appearances are
excluded without separately authorized, reconciled exclusions.

### 2.2 History representation: dual track

| Concept | A 35-pitch injury exit |
|---|---|
| Actual recent workload | Count the pitches actually thrown (retained separately, always) |
| Typical workload capacity | Robust summaries so one outing does not dominate |
| Documented historical injury exit | Separate evidence-backed label only |
| Current workload restriction | Only pregame-documented information |
| Unknown reason for short outing | Stays unknown; never inferred from pitch count |

- Robust summaries (preregistered, not a search): recent median +
  longer-history shrinkage; exponentially weighted history (frozen
  half-lives). Neither diagnoses injuries; a poor-performance hook is
  equally capable of being the outlier.
- **No BF-threshold injury inference**, anywhere. Injury-return
  labels require independent injury/transaction evidence (forward
  collection or an external verified source).
- Surprise exits are NOT removed from evaluation -- that would change
  the estimand rather than improve actual-game probabilities.

### 2.3 Label taxonomy (v2.2: debut status is never inferred from absence)

Three dimensions stay SEPARATE, never collapsed:

- **Known identity/history:** prior MLB appearance established (id-
  matched counts preserved across everything).
- **Capacity reset:** older history no longer contributes to the
  specified capacity estimate (a modeling convention; identity is
  untouched).
- **Debut status:** independently established or unknown -- an
  absence of observed history never proves a debut.

| Label | Definition (v2.2) |
|---|---|
| no_prior_appearance_observed | No prior appearance in available coverage; reported WITH coverage bounds; NOT a proven debut |
| first_mlb_pitching_appearance | ONLY via independent debut evidence or sufficiently complete career coverage |
| season_debut | First appearance in the current season (takes precedence over gap-return labeling; gap days still recorded) |
| no_prior_start_observed | No prior START in limited history; NOT a proven first MLB start; starter capacity falls back to the population mean, flagged |
| returning_after_gap | Days since last observed appearance, with coverage recorded |
| injury_return | Requires independent injury/transaction evidence |
| capacity_reset | Frozen convention (below); identity metadata preserved |
| join_failed | Expected source record could not be attached |
| ordinary | None of the above |

Per-investigation status (unchanged): 265 of 328 artifact-flagged
"career debuts" have prior MLB pitching appearances found; the
remainder are no_prior_appearance_observed / left-censored.

### 2.4 Feature groups and the narrow reopening

The broad strikeout-feature search is NOT reopened. Only the
workload-history representation affected by the confirmed
construction problem is reopened, in this order:

1. Repair the forecast spine (outcome-independent availability).
2. Rebuild complete prior histories (starts and relief,
   distinguished; short outings preserved).
3. Freeze a few workload summaries (Section 3 candidates).
4. Test one robust-history alternative.
5. Only then test ONE interaction group or the one nonlinear
   challenger.

Interaction shortlist (pick exactly ONE after steps 1-4, with
novelty first demonstrated against the frozen feature inventory):
recent workload x days since last appearance (default proposal);
typical pitch budget x prior pitches per PA; historical
starter/relief usage x recent workload. All components strictly
prior or independently pregame-known. No announced pitch limits
invented from realized pitches.

`pitch_number` is per-PA; outing pitch counts are summed per
(game_pk, pitcher).

### 2.5 Identity matching and capacity-reset rules (owner decisions, frozen)

- **Matching is by MLBAM pitcher id, never by name.**
- **History uses ALL prior appearances -- starts AND relief**,
  distinguished; forecasts target first pitchers (retrospective
  identity in development, labeled; never pregame-announced).
  Historical start/relief classifications describe realized history,
  not verified pregame intent.
- **Capacity reset (frozen modeling convention, NOT an established
  scientific boundary):** threshold 365*3 = 1095 days; boundary
  operator strictly greater-than. A gap > 1095 days between
  consecutive appearances truncates CAPACITY summaries to the
  post-gap suffix; a gap > 1095 days between the last appearance and
  the forecast empties capacity history. Reset removes old
  observations from CAPACITY SUMMARIES ONLY; identity/history
  metadata (all-season counts, days since last appearance) is always
  preserved. Fallback when no post-reset capacity exists: population
  mean, flagged (`no_prior_start_fallback` / shrinkage term). A later
  long gap triggers a second reset correctly (tested). No sensitivity
  search over the threshold during evaluation.
- **EWMA is recency-sensitive, NOT outlier protection:** a recent
  35-pitch outing pulls the EWMA down substantially. Wording frozen:
  median = robust typical-capacity summary; shrinkage limits
  instability (K = 20 prior APPEARANCES toward the population mean
  BF, source period declared by the caller, cutoff strictly prior);
  EWMA = recency-sensitive summary. A robust EWMA would require an
  explicit, separately frozen transformation -- none is added, and no
  clipping exists anywhere in the builder.
- **Starts and relief are separated in capacity estimates:** distinct
  summaries for (a) actual total workload across all appearances,
  (b) historical-start capacity, (c) historical-relief summaries and
  role counts; explicit no-prior-starts fallback. Relief outings
  never dilute starter capacity (the same concern as injury exits,
  in reverse).
- Builder implementation: `research/offseason_2026/workload_spine.py`
  (RULE_VERSION `workload_spine_v2.2`); synthetic tests
  `tests/test_workload_spine.py` (18) cover L1-L5, L7 builder-level
  plus the reset truncation/metadata/second-reset, short-outing
  preservation, debut-coverage bounds, role separation, shrinkage
  definition, gap, and injury-evidence rules. L6 is NOT asserted
  here; it gates the new fitting pipeline (Section 6).

## 3. Part B -- candidate budget (frozen before evaluation)

| Candidate | Purpose |
|---|---|
| Corrected expanding/trailing baseline | Preserve the strongest simple comparator |
| Recent median + longer-history shrinkage | Limit one outing's influence on capacity |
| Exponentially weighted history | Adapt to genuine workload changes |
| Robust regression challenger (Huber-type) | Test whether extreme residuals distort fitted models |

- Windows {5, 10, 20}, EWMA half-lives {3, 5, 10}, shrinkage weights
  frozen a priori; actual recent pitches retained separately even
  when capacity summaries are robust.
- Window/parameter selection happens ONLY inside chronological inner
  folds (nested selection); selection and assessment are separated.
  No simultaneous search across windows, features, interactions,
  model family, and calibration.
- The trailing comparator is compared on MAE/RMSE as-is, but needs a
  DECLARED probability model before NLL/RPS comparisons. Declared
  here: the trailing candidate's probability form is the empirical
  per-pitcher distribution of prior BF (history permitting), with the
  history-band pooled empirical distribution as its fallback --
  frozen before scoring.

## 4. Part C -- workload-distribution candidates (at most three)

Support: appeared-first-pitcher distribution on BF in {1, ..., 40}
with frozen explicit overflow (mass at 40+ or an explicit tail
parameter; never silent truncation). **Zero exposure (BF=0) belongs
to scratch/non-appearance accounting, not to the appeared-first-
pitcher distribution** -- it is tracked separately and never silently
merged. No zero-inflation of the appeared distribution.

1. **D-BASE** -- empirical/shrunk workload-distribution baseline.
2. **D-REG** -- regularized discrete workload model (frozen
   dispersion; training-only fitting).
3. **D-NL** -- one nonlinear distributional challenger (XGBoostLSS-
   style reference), admitted only if D-BASE and D-REG complete.

Scores: count NLL, RPS, line Brier/log loss (lines 4-7),
count-aware randomized PIT, coverage 50/80/95%; stratified by
early-season / missing-history / short-outing / PA>=9. Paired
comparison mandatory vs the strongest simple baseline on identical
keyed rows.

## 5. Part D -- evaluation design and early-season fit rule

- **Early-season origins** (Opening-Day week, April 15): fitting
  before sufficient 2023 history uses the **approved prior-season
  lookback** (2022-and-earlier, read-only) plus 2023-to-date. If a
  lane's prior-season training is not approved for a given origin,
  that origin is **baseline-only** (Part B candidates with >=K prior
  appearances; insufficient-history rows fall back to the population
  mean with labels) and inner-split models are **BLOCKED** there
  unless formable. Lanes never fall back to full-sample tuning.
- **Midseason origins** 2023-07-01 / 08-01 / 09-01 retained for
  comparability with Run 1.
- **Season transfer: APPROVED by owner (2026-10-01)** -- train 2023,
  evaluate 2024, with explicit non-pristine disclosure (2024 was
  previously inspected and is never a pristine holdout). 2025 is NOT
  a substitute development playground; 2025/2026 remain closed.
- Rolling-origin, chronological, no random CV; training-only fitting
  (L6).

## 6. Part E -- retention, report acceptance, and L6 gate

Keyed out-of-fold predictions with observations, comparator IDs,
slice flags; probability vectors; per-row feature availability,
fallback source, history denominators; exact hashes and ACTUAL
source-access inventory; per-origin + pooled metrics for all
mandatory comparisons; machine-readable completion checks -- a
missing mandatory slice FAILS report acceptance.

**L6 (inner-fit isolation) is a property of the NEW fitting
pipeline and must be tested THERE** (imputation, scaling, tuning,
clipping, calibration confined to the permitted partition). It is
NOT inherited by assertion from the Run 1 harness.

## 6a. Coverage experiment -- staged definition (v2.2)

Run 1's leaked feature construction is retained as a **historical
diagnostic reference**, not a valid benchmark that a repaired model
must outperform. Removing leakage may worsen apparent accuracy; that
does not make the repair a failure. The comparison sequence:

1. **Read-only reconstruction audit:** rebuild outcome-independent
   features, reconcile coverage, quantify feature differences vs the
   old table -- no fitting.
2. **Corrected baseline:** retain comparable feature formulas and the
   frozen fitting recipe wherever possible.
3. **Robust-history challenger:** change ONLY the preregistered
   capacity representation.
4. **Distribution work:** proceed after steps 2-3 are interpretable.

A fully redesigned robust-history model compared against Run 1 must
never be reported as "coverage lift."

## 7. Part F -- source-access rules

- **Period-pure research artifacts preferred**; no silent loader
  changes during execution (Run 1's filtered-scan change is the
  recorded counterexample).
- Approved read-only lookback inventory (explicit, per lane): 2022
  artifact (Run 1 pattern); 2015-2021 artifacts (older-history
  investigation pattern) for debut/gap verification and prior-season
  training where approved.
- Retrosheet event files may be used later for independent
  appearance reconciliation beyond the local Statcast horizon;
  separate approval before first use.
- pitcher_rolling / batter_* / park_factors are NOT used for the new
  spine (superseded by the history builder); any continued use
  requires explicit multi-period-open approval.

## 8. Forbidden (until separately authorized)

Fitting/scoring real data; 2025/2026 access; production or policy
changes; modifying Run 1 artifacts or the deviations record;
promoting any comparator; BF-threshold injury inference.

## 9. Appendix -- BulkBot as a candidate news-evidence source (2027 ledger; not a feature)

BulkBot's accessible public posts may provide **evidence about planned
openers, bulk followers, pitch limits, and later revisions** -- i.e.,
intended-workload information that is substantially better than
manufacturing role labels from short realized outings. Status wording
(locked): a comprehensive, validated historical pregame role dataset is
not established; public timestamped news may support a limited,
evidence-backed subset. Absence of a post is NEVER proof of a normal
role, and an account focused on unusual roles is not an exhaustive
census.

### 9.1 Role-and-workload evidence ledger schema (vendor-neutral, claim-level attribution v2.2)

```text
game_pk
pitcher_id
claim_type: opener designation / bulk assignment / pitch restriction
claim_origin: directly reported / aggregator inference / unclear
supporting_source: evidence supporting THAT specific claim
reported_role: starter / opener / bulk / uncertain
reported_pitch_limit: nullable
claim_status: reported / tentative / revised / withdrawn
valid_from
superseded_at
source_account
post_id
source_url
underlying_source_url
published_at
first_observed_at
forecast_cutoff
raw_capture_hash
supersedes_claim_id
review_status
```

A team announcement can establish a roster move without establishing
the workload plan; those claims stay separate. "No report found"
stays separate from "confirmed normal workload."
Three dimensions stay separate (never collapsed into a confidence
score yet): **authority** (team statement / reporter / aggregator /
unsupported inference), **certainty** (confirmed / expected / possible
/ unknown), **timeliness** (available before the forecast cutoff or
only afterward).

### 9.2 Leakage safeguards and evidence timing

- Prospective (2027): model use requires `first_observed_at` at or
  before the forecast cutoff. **`valid_from` states when the
  expectation applied; it does NOT imply historical availability.**
  Any forward evidence needs an observation/collection timestamp
  before future model use.
- Historical reconstruction: verify exact post timestamps (not the
  displayed calendar date); preserve uncertainty qualifiers and
  revisions (original + revision separately); exclude later replies
  or corrections from earlier forecasts; never use realized BF to
  judge whether an original role claim was credible; label
  historical public-news reconstruction separately from
  contemporaneously captured evidence. A correct opener announcement
  posted after the morning decision is unavailable to that morning
  forecast.

- Prospective (2027): accept evidence only if actually captured by
  the forecast cutoff.
- Historical reconstruction: verify exact post timestamps (not the
  displayed calendar date); preserve uncertainty qualifiers and
  revisions (original + revision separately); exclude later replies
  or corrections from earlier forecasts; never use realized BF to
  judge whether an original role claim was credible; label
  historical public-news reconstruction separately from
  contemporaneously captured evidence. A correct opener announcement
  posted after the morning decision is unavailable to that morning
  forecast.

### 9.3 Bounded feasibility review (before any use)

1. Review a fixed, consecutive period (no cherry-picked examples).
2. Trace claims to original team/reporter sources.
3. Measure timestamp availability, revisions, game/player mapping
   quality, and ambiguous claims.
4. Separate evaluable claims from unverified ones.
5. Decide whether public, permitted access is reliable enough for
   manual capture or future automation. No paid access, no aggressive
   scraping, no fragile production dependency.

First prospective application: a human-reviewed role/restriction flag
or out-of-support warning -- not an automatically learned BF
adjustment. A calibrated role-conditioned model comes later, only if
label volume and reliability justify it.

## 10. Review gate

This draft returns for owner review. The spine/history-builder
implementation and its synthetic leakage tests are complete and may be
reviewed as code; NO real-data execution is authorized. Execution (if
approved) is a separate, single-run authorization per lane with the
frozen spec hash.
