# PA Overhaul Phases 4–5 Durable Record (2026-09-29)

Status: PA-1A EXECUTED AND SUPPORTS INCREMENTAL BATTER SIGNAL (narrow claim below).
Author: offseason agent, Phase 5.5 owner authorization (one durable report + bounded
attribution artifact + one audit cross-link). Chat-only findings from Phases 4/4.5 are
consolidated here. Companion artifacts: `research/offseason_2026/experiments/pa1a_raw_pa/`
(cards, preflight.json, deviations.md, per_pa.parquet, reliability.parquet) and
`pa1b_oracle_xk/` (card, completeness.json).

## 1. Supported PA-1A claim (exact)

> "Using the registered 2024 PA population and supplied pregame rate features, M2's
> addition of shrunk batter strikeout tendency improved PA-level log loss and Brier
> score relative to the pitcher-only M1 construction in both registered chronological
> blocks."

- Demonstrated: M2−M1 logloss Δ −0.00436 (E1) / −0.00711 (E2), Brier Δ −0.00147 /
  −0.00233; game-date-clustered 95% CIs exclude zero in both blocks; game_pk-clustered
  sensitivity agrees; 100% of 2,000 replicates favor M2 in both blocks; negative in all
  pre-registered slices (month, hands, history buckets, matchup number, trip proxy).
- Suggested: M2 also beats M0 (league constant) pooled (−0.0037 logloss, CI excludes 0)
  and in E2; not in E1 alone (CI crosses 0).
- Weakened (evidence against M1 as constructed): M1 (unshrunk season-reset pitcher rate,
  league-scalar fallback) is WORSE than the constant in E1 (+0.0045 logloss, CI excludes
  0) — the pitcher cold-start problem.
- Not yet tested: everything downstream — aggregation (PA-1B), pregame xK, count
  distributions, calibrators, frozen-stack comparison, odds/policy/betting.
- Falsified/known-weak: raw unshrunk pitcher rate as M1 prior; log5 calibration (β≈0.65
  pooled, overconfident).

Populations: primary 211,292 (drop 360 truncated_pa unknown-label; keep 1,275
field_error); sensitivity 211,652 (retains 360 under assumed is_k=0; results identical
to 4th–5th decimal). Blocks: E1 2024-03-28..06-30 (n=55,815); E2 07-01..09-30 (n=50,252).
2023 (105,225 primary) = prior history only, never scored.

## 2. Architecture (frozen Phase 4.5/5)

Binary PA K target conditional on PA occurring; no pair memorization; matchup K
probability separated from opportunity/TBF; no TTO input in PA-1; sequence fields
(starter_pa_index, trip_proxy, matchup_number) are diagnostics, never inputs; O0 oracle
/ O1 point-xTBF / O2 survival / O3 TBF-mixture aggregation ladder; five-report
evaluation hierarchy; final feature set NOT frozen.

Arms: M0 = league_k_prior (0.223813, 2022-derived, ratified for PA-1A only).
M1 = coalesce(k_rate_std, league_k_prior) — k_rate_std is UNSHRUNK expanding
season-to-date (pitcher_rolling.py:1040), resets each season, shifted before the game,
constant within game, league-scalar fallback (9.7%/2.5% of E1/E2 rows). M2 = odds-form
log5: p = o(p_p)·o(p_b)/o(l) / (1+·), p_p = M1 value, p_b = b_k_rate_std_shrunk
((ΣK+200·lg)/(ΣPA+200), prior-season league scalar 0.223813, expanding within season,
no season carry-forward, 100% populated), l = league_k_prior. Clip [1e-6, 1−1e-6] on
M2 inputs/outputs and (registered deviation, non-substantive, before scoring) on M1
outputs because raw rates hit exact 0/1.

## 3. Preflight result (machine-readable in preflight.json)

Gates A,B,C,D,E,G PASS; F WARN (122 multi-pitcher PAs 2023–24, 0.058% — resolved, see §4).
One logged non-substantive deviation (M1 clip). Bootstrap: B=2000, seed=0, percentile 95%;
primary cluster game_date; sensitivity cluster game_pk; 7-day moving block DEFERRED.
A first bootstrap implementation normalized by sampled cluster count instead of sampled
PA count and was corrected before results were reported (scale bug caught by raw-vs-CI
sanity check).

## 4. Multi-pitcher attribution (RESOLVED)

Artifact: `research/offseason_2026/experiments/pa1a_raw_pa/attribution_reconciliation.json`
(sha256 4245cf5e0d0e6b7fa74c2868242bf87219d17f56d1f9ba673089cc3e208bcc25).
All 122 = genuine mid-PA pitching changes (first pitch row by a preceding real pitcher;
no automatic/clock events; anomalous pitcher pitched other PAs in the same games).
Official rule (MLB Glossary; OBR Ch.9 scorer convention; cf. OBR 6.09(b)): the K is
credited to the pitcher who delivered the third-strike pitch and the PA is charged to
the completing pitcher — the PA table's terminal-row attribution matches official
bookkeeping on all 122 rows including all 44 K labels. Canonical future rule: keep
terminal-row attribution + split_pa_flag; split PAs excluded from PA-1B primary start
purity and from single-pitcher prior fitting; retained elsewhere with disclosure.
Sensitivity rule: re-run PA-1A primary with the 51 E1/E2 split rows excluded (expected
immaterial; not run).

## 5. Historical feature evidence (compact register; full Phase-4 chat trace consolidated)

- Rolling windows P5/P10/P20 (pitcher=starts, batter=games): convention-first, then
  stabilization-checked (K% r=.50 at 100 PA ≈ 4.3 starts / 75 PA ≈ 18.8 games;
  artifacts/stabilization/expanded/), then nested window ablation kept them.
  DIRECTLY TRANSFERABLE to PA target.
- EB shrinkage 200 PA (batter): convention, never grid-searched; 300-PA Glicko lesson
  directional. MUST RETEST (sweep 100/150/200/300 as separate card).
- Pitcher prior-season carry-forward exists (add_prior_season_shrunk_k), unwired.
- VIF program: 248-set → 74 clusters (median VIF 3.21). Feature-set lineage
  248→185→180→73→72/58 = one family tree; LightGBM 248 test MAE 0.0983 vs mean 0.1070.
- Pitch-type features: only FF/SL/CH stabilize; promotion lift failed (+0.0001 MAE).
  TEST LATER for PA.
- Order-weight 0.1069 vs 0.1053 (n=8,975): pair-level and order-weight promotion
  REJECTED. WS5b slot-blend Poisson-binomial: w=0 optimal, KILLED. v4 sim: Brier 0.1472
  vs Poisson 0.1461 vs ws1c 0.1438 — archived challenger.
- Count family race: Poisson won (Brier 0.13981); CRPS/PIT helpers ABSENT (audit:1007).
- Hook table: 353,824 PAs, pull 0.0999, survivor-biased, uncalibrated; 3 hook fixes
  killed; NB-mixture falsified (no overdispersion).
- TTO: never modeled (owned gap). Park: prior-season EB (500 PA), leakage-safe.
  Umpire ruled out by policy; weather/catcher absent.
- 2025/26-contaminated decisions (prior knowledge only): debut-cohort biases, WS1c,
  ensemble weight selection, KING_AUG2026.

## 6. Open items (owner-gated)

PA-1B-O (specified, 95.82% of 4,711 starts reconcile exactly to canonical PA;
primary = 4,514 exact-reconciled starts); pitcher-prior experiment card (P0–P4,
specified, not run); frozen-comparator replay contract; PA-1B-P (needs 2026-only
projected-lineup lane); trained ladder (M3→M5) only after PA-1B; deep learning not
authorized by row count alone.


## AM.1 Phase 6 append (2026-09-30): pitcher-prior repair + oracle aggregation executed

Gate A resolved the Phase 5.5 terminology conflict: pitcher_games (2023-24) entries are 100% OFFICIAL starters
(0 bulk-9); all 122 multi-pitcher PAs were completed by <9-PA relievers (64 official-starter-began, 58
reliever-to-reliever) and NEVER entered the PA table (Phase 5 Gate F's '51 starter-terminal rows' was an
unsorted-last() artifact; its '197 under-reconciled starts' corrected to 4,711/4,711 exact). Frozen comparator
= DESCRIPTIVE_TRAIN_OVERLAP for 2024 (members <=2024-06-08; weights 2026-08-21; WS1c 2026-09-03; no 2024 OOF):
stopped for primary, clean comparison deferred to 2025. Pitcher-prior: P3 pooled EB (m=100, 2023-fold selected)
PROMOTED FOR DEVELOPMENT (beats original M2 both blocks, 100% fav, calibration beta~0.92). PA-1B-O (4,711 exact
official starts): batter signal SURVIVES aggregation (M2-M1 MAE -0.037/-0.051, 100% fav both blocks) and
cold-start repair SURVIVES (P3-M2 MAE -0.144/-0.042, 100% fav). Artifacts + hashes under experiments/{pitcher_prior,
pa1b_oracle_xk}/ incl. report.md each.


## AM.2 Phase 7.5 append (2026-09-30): guards, contracts, immutable L3 bundle

Eight permanent regression guards (tests/test_pa_research_guards.py, 9 tests green incl. contract
roundtrip): season isolation, key-based join alignment (the guard caught the contract itself - polars
left joins do not preserve order; align_predictions now row-indexes and sorts), independent aggregation
checksum, population reconciliation, P3 reproduction vs canonical counts (1e-9), identical-arm keys,
temporal boundaries, duplicate-key rejection. Research contracts: research/offseason_2026/contracts/
pa_contracts.py (predict_pa_probabilities, aggregate_oracle_xk ACTUAL_TBF_ORACLE only, other modes
NotImplementedError). L3 bundle: logistic_pa/bundle/ (model_card + feature/preprocessing manifests +
model_bundle.json + hashes); intercept NOT serialized at execution time - RECOVERED from stored
predictions + rebuilt features (constancy 1e-15); reproduction vs stored L3 predictions max |dp| 2.2e-16
(machine epsilon) - BUNDLE REPRODUCIBLE. Tree card drafted (next_tree_card_draft.json, T0-T3, tree must
beat L3); validation lanes A-D specified (validation_lanes.md) incl. 2025 no-lineup-snapshot implication
and 2027 lineup-version logging spec. Fixed-offset contextual arm recorded as UNTESTED (no performance
estimate exists; earlier bound conjecture withdrawn).
