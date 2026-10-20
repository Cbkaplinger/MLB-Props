# Batter-history current-state documentation + bounded challenger proposal (2026-10-20)

Research-only proposal document. NO fitting, NO new predictions, NO external
data, NO modification of the preserved run or any frozen artifact. Existing
code and artifacts only. Preserved output remains UNACCEPTED and untouched.

## Part 1 - current history behavior (existing code, adapter.py)

| Item | Documented behavior (code-verified) |
| --- | --- |
| Earliest source date | PA table 2022-04-07 (731,347 rows, 2022-2025); ALL cumulative and EW states accumulate from that date; league state too. Training ROWS start 2023-01-01 (2022 rows feed priors only, never train rows). Scoring window 2024-07-01..2025-09-28. |
| Season-reset behavior | NONE. entity_daily_state cum_sum over(entity) across all seasons; no year partition anywhere. Blocks (add_block) only partition SCORING, never the state. |
| Feature windows | Cumulative prior: all prior rows, no window. EW: cumulative with weights 2^(dnum/90) = HALF-LIFE 90 days (not a 90-day window): effective weight of a row halves every ~90 days of age relative to newer rows; 2022 rows are present but negligible by 2024-2025 (~2^-7 weight). League: cumulative, no window. |
| w150 shrinkage | p_prior_w150 = (prior_k + 150 * lg_rate) / (prior_n + 150): raw cumulative K/PA shrunk toward the AS-OF LEAGUE K RATE (strictly-prior lg_rate) with 150 pseudo-PA (W_PRIOR = 150). Applied identically to pitcher and batter. |
| Recency weighting | EW component: ew = ew_k / ew_den where ew_k/ew_den are 2^(dnum/90)-weighted cumulative K and PA sums, strictly prior (shift(1) per entity). NO shrinkage on the EW feature itself: any ew_den > 0 yields the raw weighted ratio; only prior_n == 0 falls back to lg_rate. NOTE (staleness gap): because numerator and denominator share the same date weights, the EW ratio does NOT decay toward league with absolute staleness - a batter whose entire history is 2022 (none since) still presents his 2022 form as his EW at a 2025 start. |
| RAW / L5 definitions | p_h3_raw = frozen per-block logistic (StandardScaler + LogisticRegression(C=1.0, max_iter=1000)) on the 8 FEAT_H3 features (p_pitcher_prior_w150, p_batter_prior_w150, lg_rate, n_prior_pitcher, n_prior_batter, cold_start, ew_pitcher, ew_batter) from the verified checkpoint; feature-based, IDs never enter. p_l5_raw = LOG5 correction from the two w150 priors and lg_rate (no model). Count PMFs: p9 sorted by slot -> cycled prefix-mean pbar_n -> mixture over the BF 37->cap-60 extension -> 24 buckets. |
| Training dates | Per block: train = feature rows 2023-01-01..(block_train_end minus the 60-day cal window); cal = last 60 days before train_end (2024-06-30 / 2024-12-31 / 2025-06-30). fit_models_from_frames fits scaler+LR on TRAIN only (the cal frame is accepted but unused for the logistic - no early stopping exists in this family). |
| Older seasons entering features | YES for cumulative priors, n_prior counts, and lg_rate (2022 rows enter all cumsums). YES-but-negligible for EW (2^(-age/90) weights). The 2022 season exists ONLY as prior source for 2023+ training rows. |
| Existing rolling modules | entity_daily_state (cum + EW, parameterized by entity) is THE rolling module - reused for pitcher and batter; league_daily_state; asof joins. No other rolling machinery exists in this lane (kcount_combiner / bf_distribution are distribution transforms). A challenger REUSES entity_daily_state; no new rolling framework needed. |

## Part 2 - classification status of the 59 cases

Established from existing artifacts (report_debut_pitcher_reconciliation_2026-10-20.md):
all 59 are ACTUAL in-window MLB career debuts as pitchers (first pitcher-row inside
2024-07-03..2025-09-15; zero earlier pitcher rows across the four-season table; zero
earlier batter rows). Boundary: 'actual debut' is established within the frozen
2022-2025 Savant lineage; external register confirmation would be external data
acquisition and is out of scope. The model GENUINELY faces new players - this is
not an artificial gap recoverable by better historical construction from existing
sources.

## Part 3 - bounded batter-history challenger proposal (pre-registration draft)

### Hypothesis

The frozen batter features (career-cumulative w150 + self-relative EW with no
absolute-staleness decay and no shrinkage) leave information unused for batters
whose recent form diverges from their career cumulative rate. ONE batter-only
challenger: anchor recent K/PA to a recency-weighted player-history estimate.
Pitcher features, lg_rate, lineup construction, BF inputs, model family, and
the evaluation population are FIXED.

### Design

- Prior (anchor): recency-weighted batter estimate over rows OLDER than the
  recent window, shrunk to the as-of league rate: p_anchor = (ew_k_old + 150*lg)
  / (ew_den_old + 150) - same w150 weight and target as the frozen recipe; the
  anchor's EW uses the SAME frozen half-life (HALF_LIFE_DAYS = 90; no new decay
  constant). For a batter with no pre-window rows: p_anchor = lg_rate (explicit
  newcomer fallback, flagged source_type unchanged).
- Recent component: raw K/PA over rows INSIDE the recent window R (days,
  strictly prior), no shrinkage: p_recent = k_win / n_win; n_recent = n_win.
- Update rule (sample-size accounting): p_batt_new = (k_win + m * p_anchor)
  / (n_win + m), m = pseudo-PA budget. Disjointness: window rows feed ONLY the
  recent component; pre-window rows feed ONLY the anchor - the same appearance
  never enters both, so no double counting. n_recent and the anchor's effective
  size are both recorded per row.
- Newcomer behavior: zero-history entities keep the REGISTERED exclusion
  (cold_start_no_prior) - the challenger changes NOTHING about the 59
  debut-pitcher starts or any cold-start policy. A short-history batter
  (small n_win) is anchored, not excluded - that is the exact gap the
  hypothesis targets, and it is batter-side only.
- Strictly-prior cutoff: identical asof machinery; two new source-date columns
  (src_date_batt_recent, src_date_batt_anchor) join the existing hard cutoff
  gate (assert_cutoff extended in the diagnostic only).
- Feature set: replace p_batter_prior_w150 + ew_batter with p_batt_recent +
  p_batt_anchor (8 features total; pitcher side, lg_rate, counts, cold_start,
  ew_pitcher unchanged). Same model family: StandardScaler + LogisticRegression
  (C=1.0, max_iter=1000), fit per block on the SAME training rows as the frozen
  block models.
- Candidate budget (ENTIRE budget, pre-declared, no search beyond it): 3 configs
  - R=60d with m=30 (PRIMARY), R=60d with m=15, R=120d with m=30. Half-life
  fixed at the frozen 90 days in all configs. One config selected by the
  pre-declared primary metric on dev rows only; confirm period never consulted.

### Validation

- Eligible population: the 7,135 fully-scored starts (64,215 scored PA rows) from
  the preserved run - IDENTICAL eligible keys for baseline and challenger; the
  59 debut-start abstentions (59/7,194 = 0.82%; coverage 99.18%) are PROMINENTLY
  reported in every output of the diagnostic, never silently dropped.
- Chronological development folds: block_2024H2 (2024-07-01..2024-12-31) and
  block_2025H1 (2025-01-01..2025-06-30) - the registered dev blocks. Challenger
  fit per block on the frozen recipe's train rows (2023-01-01.. block cal_first),
  scaler on train only; NO early stopping, no calibration stage.
- Protected: confirm_2025H2 (2025-07-01..2025-09-28) stays EXCLUDED - not fit,
  not scored, not tuned, not reported as evidence.
- Primary metric: pooled RAW Brier delta (challenger - baseline p_h3_raw) on
  eligible dev rows, paired slate-date bootstrap n=2000 seed 20261001
  block-stratified, null-centered + Holm (m=1 family) - the registered
  convention. Per-fold deltas descriptive only.
- Baseline: the unchanged frozen checkpoint predictions on the same rows
  (reusing the preserved run's valid predictions; the original run STAYS failed
  against its zero-exclusion acceptance - the diagnostic never relabels it).

### Changed-path estimate

- NEW: one research-only diagnostic script (feature builder reusing
  entity_daily_state + challenger fits + evaluation) under
  research/offseason_2026/pregame_pa_ext/; a pre-registered card before fitting.
- UNCHANGED: adapter.py, build_checkpoint.py, freeze_pregame_pa_ext_v2.json, the
  checkpoint artifact, BF/lineup artifacts, the preserved output parquet, all
  production paths. The diagnostic reads existing artifacts only.
- Compute: 3 configs x 2 dev-block logistic fits (seconds each) + one feature
  pass over 7,135 starts - minutes, single process, no MLflow requirement
  (optional tracking through the shared wrapper if the owner wants the receipt).

## Sequencing (owner decisions)

1. This proposal requires separate approval BEFORE any fitting (new challenger
   = new registered candidate; no fitting has occurred).
2. The restricted 7,135-start diagnostic on the EXISTING baseline predictions is
   a separate, smaller approval (no fitting; report baseline diagnostics with
   prominent 59-start abstention reporting).
3. Full-coverage forecasting remains a separate registered improvement; the
   genuine-debut finding indicates the appropriate improvement class is a
   NEWCOMER PRIOR or an EXPLICIT ABSTENTION POLICY - not better historical
   construction (no earlier MLB data exists for these pitchers within any
   available source).
