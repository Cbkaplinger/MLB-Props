# PA Count-Distribution Program -- D0-D5 Specification (preregistered, no execution)

Status: **SPECIFICATION ONLY**. No dataset built, no model fitted, no evaluation run.
Phases D0-D5 are separately gated below; each gate after D-spec approval requires its
own owner authorization. This file defines WHAT will be built and judged, never results.

Controlling facts (non-negotiable; see cited records):
- L3 ridge logistic = PA DEVELOPMENT_BASELINE, NOT APPROVED for production
  (`logistic_pa/bundle/`, sidecar `provenance_sidecar.md`).
- P3-log5 = rollback/reference baseline (`pitcher_prior/`).
- `log_pa_prior` = INACTIVE_HISTORICAL_FEATURE (constant zero; excluded henceforth).
- Tree search closed; F6 rest excluded from PA-K manifests.
- Registered 2024 evaluation discipline was once-only; the same discipline governs here.
- Historical TBF and realized batting order are oracle-only diagnostics, never pregame claims.
- Grandfathered Parquets authorize no new binary artifacts in ordinary Git: this program
  commits cards/manifests/reports (JSON/md) only. Predictions live in ignored scratch,
  referenced by path + sha256, never committed.

## 0. Stage map

| Stage | Purpose | Inputs | Outputs | Gate to next |
|---|---|---|---|---|
| D0 | Dispersion + exposure audit | frozen L3, frozen Ridge xTBF, PA table, split manifest | variance decomposition, boundary sets, stop/go | audit shows estimable quantities; else STOP |
| D1 | Transparent count baselines (fixed ladder) | D0 populations + cutoff | 7 pre-registered baseline distributions | ladder frozen before any challenger |
| D2 | Exposure (BF survival) model | cutoff-safe covariates, censoring policy | BF pmf per start + calibration | hazards calibrated; mass sums to 1 |
| D3 | Joint aggregation (PB + mixtures) | L3 p_t, D2 BF law, lineup mode | P(K=k) per start per arm (D0-D5 table) | exact-vs-approximate fixed; seeds frozen |
| D4 | Evaluation + promotion | once-only 2024-style eval design | proper-score verdicts, tie/fail/stop | thresholds frozen (owner fields) |
| D5 | Market layer (separate) | board-time quotes at/before cutoff | benchmark vs market, blend baseline | no betting conclusion; CLV/ROI later |

## D0 -- Data and dispersion audit

- Target: full pitcher strikeout-count distribution P(K=k) for a qualifying start.
- Unit of prediction: one official start (exact-reconciled; PA-1B-O purity rule:
  terminal-row attribution, split-PA flagged; 4,711-start reconciliation procedure).
- Forecast cutoff: scheduled first pitch (frozen default; board-time variants belong
  to lane-D work, not this spec).
- Eligible starts: Q-D4 cohort (PA>=9 first-pitcher games); opener/bulk/scratch/
  suspended excluded per `pa_dataset_contract.md` funnel rules 1-15.
- Dataset: PA table + L3 bundle predictions + frozen Ridge xTBF, all input-hashed per
  card convention; split manifest with MECHANICAL inclusive timestamp bounds (C1/C7
  lesson: every eligible row belongs to exactly one block or a named boundary set;
  the 2024-06-30 boundary rows form a named set counted in reconciliation, never
  silently dropped).
- Development/evaluation boundaries: method development on 2023 folds (F1/F2 as in
  the tree card); once-only evaluation on 2024 E1/E2.
- Prohibition: no 2025/2026 outcomes touched during specification or development.
- BF audit: empirical distribution of actual BF per start; mean/variance by workload
  band, month, role-purity slice.
- Count audit: observed K mean/variance overall and by band.
- Variance decomposition: fixed-exposure variance (heterogeneous Bernoulli at
  observed N) vs random-exposure variance (BF law) vs residual. Do NOT claim
  heterogeneous Bernoulli probabilities alone necessarily create overdispersion;
  the decomposition decides.
- Heterogeneity-vs-overdispersion test: Poisson-binomial variance at observed N vs
  observed K variance within narrow exposure strata. Extra-binomial variation opens
  the D1 arm-7 / D5 gates only; otherwise they stay shut.
- Lineup-availability categories per start: announced-confirmed / announced-unconfirmed /
  proxy-only (`is_initial_lineup`) / unknown; counts reported, never imputed silently.
- Missingness: postponed/scratched-starter policy = exclude + count (never impute a
  start); truncated/split PAs follow the dataset contract quarantine rules.
- Reproducible artifact plan: audit JSON + manifest (no predictions committed).
- Stop conditions: STOP if exposure data cannot support a BF law (coverage floors per
  G4 minima), if cutoff-safe features are unavailable for a lane, or if eligible
  starts fall below the pre-registered floor (owner field).

## D1 -- Transparent count baselines (fixed ladder, all on identical starts/cutoff)

| # | Arm | Inputs | Parameters | Fitting period | Support | Method / fallback |
|---|---|---|---|---|---|---|
| 1 | Shrunk empirical count distribution | realized K, development only | shrinkage strength (frozen) | development | 0..K_max | fallback: league pooled if slice thin |
| 2 | Poisson, matched xK | frozen xK | none | n/a | 0..K_max | exact Poisson pmf |
| 3 | Negative binomial | frozen xK + development K | dispersion (development only) | development | 0..K_max | fallback to Poisson if dispersion unidentified |
| 4 | Fixed-exposure binomial | L3 mean p at actual N | none | n/a | 0..N | exact binomial |
| 5 | Fixed-exposure Poisson-binomial | L3 p_t at actual ordered PAs | none | n/a | 0..N | DP exact (FFT optional); fallback: binomial if sequence unavailable |
| 6 | Random-exposure mixture (PB + BF law) | L3 p_t + D2 BF pmf | mixture weights (development) | development | 0..K_max | fallback to D2-mean plug-in with disclosure |
| 7 | Beta-binomial / latent start-rate mixture | L3 p_t + development K | latent variance (development) | development | 0..K_max | **ONLY if D0 supports extra-binomial variation** |

Expected strengths/failure modes recorded per arm in the experiment card. Arms 1-3 are
baselines; 4-5 are mechanistic challengers; 6 is the integration challenger; 7 is
conditional. L3/P3 roles preserved; PA feature selection stays closed.

## D2 -- Exposure (BF survival) model

- Target: P(N=n) per start over prospective BF index n = 1..N_max (N_max = frozen
  owner field; recommended default 36 with overflow bucket, owner confirms).
- Risk set at index j: starts with N >= j-1 still active (pitcher not yet removed).
- Event: starter removal (hook, complete game, rain-shortened ending).
- Right censoring: none in completed/rain-shortened games (terminal observed);
  suspended/postponed/scratched excluded (missingness policy, counted).
- Completed-game treatment: terminal at observed N (fully observed, not censored).
- Doubleheaders: each game a separate start; same-day fatigue as optional lagged
  covariate with availability proof.
- Openers/bulk relievers: excluded (out-of-scope family; cohort rule).
- Rain/injury/ejection: terminal observed if removal occurred; excluded if no
  removal observed (counted in missingness).
- Terminal event and maximum support: removal; support 1..N_max + overflow bucket;
  tail mass reported, never silently truncated (truncation rule frozen).
- Covariates (cutoff-safe only): lagged rest, lagged pitch-count/workload bands,
  handedness, opponent aggregates, park, season effects, team bullpen state (L1-L3d
  where pre-cutoff). In-game state variables FORBIDDEN for pregame prediction.
- Manager/team/pitcher workload effects: allowed as pre-cutoff covariates with
  availability proof; manager identity optional with same proof.
- Baseline: logistic-hazard per BF index with shrinkage/regularization (strength
  frozen on development); calibration checked (reliability by index band).
- Hazards to pmf: P(N=n) = h_n * prod_{j<n}(1-h_j); assert mass sums to 1 per start.
- Tail handling + probability-sum checks on every output (fail-loud).
- Sparse-history fallback: shrink to workload-band prior; report fallback rate.
- GBNet/boosted survival: listed challenger only, not required first implementation.

## D3 -- Joint aggregation

P(K=k) = sum_n P(N=n) P(K=k | N=n), operationalized:

- N = exposure/BF from D2 (pregame) or actual N (oracle diagnostic lane only).
- Fixed-N Poisson-binomial via dynamic programming O(N*K), exact; FFT optional with
  error bound recorded.
- Batter sequence: mode-specific order (Section: Lineup policies); TTO handling =
  frozen option (none | trip-index covariates in exposure | order-decay sensitivity;
  default none, sensitivity listed not required).
- Confirmed/projected/unknown policies per lineup section; bench/substitution
  uncertainty via replacement-level rates with disclosure, never silent averaging.
- Correlation/shared start-level uncertainty: conditional independence of PA outcomes
  given (p_t, N) is the WORKING ASSUMPTION, tested by the variance diagnostic (D0)
  and the beta-binomial arm (D1.7). Dependence structures beyond that are out of scope.
- Monte Carlo: permitted for mixture layers only; fixed seeds from split manifest;
  convergence via batch-SE thresholds (frozen fields); exact computation preferred.
- Exact vs approximate: declared per arm in the card; approximations carry error bounds.
- Normalization: pmf sums to 1 per start (asserted); max count support K_max (frozen
  owner field; recommended 20 + overflow bucket, owner confirms); tail truncation rule
  frozen with mass accounting.
- Fallback when exposure/lineup missing: lane-appropriate default (UNKNOWN mode) with
  missingness flag; never silent substitution of oracle inputs.
- P3-log5 rollback: the aggregation path must reproduce under P3-log5 inputs as a
  smoke check (same code path, transparent prior) before any L3 claim is trusted.

Owner arm table (frozen):

| Arm | PA probabilities | Opportunity | Distribution |
|---|---|---|---|
| D0 | L3 | Actual TBF | Current Poisson (baseline) |
| D1 | L3 | Actual ordered PAs | Poisson-binomial |
| D2 | L3 | Frozen xTBF | Current Poisson |
| D3 | L3 | Frozen point xTBF | Fractional/sequence approximation (candidates frozen pre-eval) |
| D4 | L3 | Frozen TBF distribution | Mixture of Poisson-binomial (needs versioned OOF residual store; store build is a prerequisite card) |
| D5 | L3 | Frozen TBF distribution | Negative-binomial challenger ONLY if residual overdispersion remains after D4 |

## D4 -- Evaluation and promotion (proper scores primary)

- Log score (count NLL, clip 1e-12 with counter per `count_metrics.md`).
- Ranked probability score / discrete CRPS.
- Randomized PIT (pinned seed; uniformity test; never raw PIT).
- Exact-count calibration; prediction-interval coverage (P50/P80 + tails <2.5 />9.5).
- Mean and variance calibration (observed vs predicted, by band).
- Threshold Brier/logloss + ECE at every supported line (2.5-9.5; canonical scoring,
  never forked; WS1c-vs-raw pair shown where a calibrator is involved).
- Tail calibration for ladder levels; whole-number rungs push-not-loss IF in scope
  (half-lines have no pushes).
- Reliability by exposure band, line level, season, lineup status.
- Point MAE secondary ONLY (never decides when means tie).
- Uncertainty: date-cluster bootstrap B=2000 seed=0 + game_pk sensitivity (Phase 7/8
  convention); multiple-comparison control via bounded challenger count (ladder fixed;
  additions need a new card).
- Tie: CIs straddle zero in both blocks (precedent). Promotion threshold: FROZEN
  NUMERIC OWNER FIELD (precedent: <0.0005 kills; symmetric promotion bar).
- Fail rule / stop rule: mirror the tree stop discipline (ties/loses to incumbent =
  retain incumbent, escalation stops). Rollback rule: P3-log5 reproduction required.
- Missing-result treatment: counted, never imputed; denominators exclude missing.
- Once-only evaluation; no post-evaluation retuning (registered analysis plan frozen
  before unblinding).

## D5 -- Market layer (separate from baseball truth)

1. Pure baseball distribution (D0-D4 output, no market inputs).
2. Market-implied distribution / available line+price at decision clock.
3. Development-fitted model/market blend (global blend FIRST baseline, nfelo-style).
4. Decision/pricing layer (out of scope for this program; no betting recommendation).

- Market timestamp/cutoff: board-time quotes at or before the forecast cutoff only.
- De-vigging: multiplicative two-way (existing `market.py` convention); record American
  + decimal, decimal canonical for math.
- Benchmarking without leakage: morning-or-earlier consensus; closes NEVER at decision
  time (close = later CLV-style diagnostic only, separate evaluation).
- Granular blend only after adequate sample evidence; no pitcher-specific adaptive
  blend by default.
- Calibration + predictive-score comparison of blend vs arms (same-subset rule).
- CLV/ROI/profitability: separate later evaluations, never conclusions of this program.
- No betting recommendation or market conclusion from PA evidence.

## Lineup policies (three forecast modes)

| Mode | Allowed information | Order construction | Replacement uncertainty | Comparability | Label | Fallback |
|---|---|---|---|---|---|---|
| CONFIRMED | timestamped announced lineup with fetched_at <= cutoff | announced slots 1-9 | late-scratch -> replacement-level + flag | comparable across modes with label | `lineup=confirmed` | downgrade to PROJECTED with reason |
| PROJECTED | announced without timestamp proof, or realized initial-9 proxy | announced or proxy order | proxy carries availability-unverified tag | comparable with label; never pooled with CONFIRMED silently | `lineup=projected-unverified` | downgrade to UNKNOWN |
| UNKNOWN | none | overall opponent means, no order | n/a | reported separately, never pooled | `lineup=unknown` | n/a (is the fallback) |

Realized batting order is NEVER pregame-available unless confirmed before the
registered forecast timestamp. Lane mapping: oracle lanes use actual sequence;
pregame-style lanes use CONFIRMED/PROJECTED/UNKNOWN with labels (validation_lanes.md
lanes A-D preserved).

## Gates (all frozen before execution; owner fields marked *)

- Data contract approved (dataset contract + funnel rules + cohort).
- Split manifest approved (mechanical bounds; boundary sets named; seeds pinned).
- Exposure target approved (N_max*, support, censoring policy).
- Lineup policy approved (mode assignment rule per start).
- Baseline ladder frozen (D1 arms + fallbacks).
- Metrics frozen (NLL/RPS/PIT/coverage/line-level; MAE secondary).
- Promotion/tie/stop rules frozen (delta threshold*, K_max*, seed policy).
- Artifact policy approved (JSON/md committed; predictions referenced, never committed).
- No future-outcome access (2025/2026 results untouched through unblinding).
- Implementation card approved (separate authorization AFTER this spec).

Approvals separate: specification != implementation != execution != unblinding != market use.

## Explicit exclusions

PA feature search; PA retraining; tree-search reopening; MLflow implementation;
production integration; policy-2025 work; future-season outcome access; new Parquets
in ordinary Git without owner approval; Git LFS; betting deployment; automated
schedules; model registry/serving; profitability claims.

## Required tables (in this spec)

Stages (Section 0) | baseline ladder (D1) | exposure definitions (D2) |
lineup modes (above) | evaluation metrics (D4) | external methods (below) |
artifact plan (D0 + Gates) | open owner decisions (below).

## External methods disposition

| Idea | Disposition | Note |
|---|---|---|
| Poisson-binomial modeling | ACCEPTED FOR BASELINE | D1.5 + D3 core |
| Discrete-time survival | ACCEPTED FOR BASELINE | D2 design |
| Proper scores, RPS, randomized PIT | ACCEPTED FOR BASELINE | D4 metrics per count_metrics.md |
| Hierarchical/generalized log5 | ACCEPTED FOR BASELINE | P3 prior + rollback (already in use) |
| nfelo market regression | ACCEPTED FOR BASELINE | D5 global blend |
| KSplit methodology | ACCEPTED AS CHALLENGER | order-weighted sequence variant, gated card |
| GBNet / boosted survival | DEFERRED | later D2 challenger only |
| NGBoost / distributional forests | DEFERRED | later challengers, not first implementation |
| Sloan DRL / full RL agent | REJECTED | wrong tool for distributional estimation |
| Beta-binomial / latent mixtures | CONDITIONAL | only if D0 supports extra-binomial variation |

## Open owner decisions (frozen fields; implementation blocked until filled)

| # | Field | Recommended default | Blocks |
|---|---|---|---|
| 1 | K_max count support + tail rule | 20 + overflow bucket, mass accounted | D3/D4 |
| 2 | N_max BF support + overflow rule | 36 + overflow bucket | D2/D3 |
| 3 | Promotion delta threshold (count NLL + line-level) | symmetric to kill precedent | D4 verdict |
| 4 | D3 fractional-method default | floor/ceiling linear-fraction mixture; nearest-integer as sensitivity | D3 |
| 5 | D4 store prerequisite | versioned OOF residual store built first (separate card) | D4 execution |
| 6 | Forecast cutoff edge cases (dawn/day-game variants) | scheduled first pitch; variants deferred to lane-D work | D0 populations |
| 7 | MC batch-SE convergence thresholds | set at implementation-card review | D3 mixtures |
| 8 | Eligible-start floor (n) | G4 minima apply | D0 stop rule |
