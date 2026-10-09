# I3b 2024 transfer-validation freeze (pre-read, 2026-10-08)

> **Status: FROZEN BEFORE ANY 2024 OUTCOME READ** (ownership-ordered:
> "Freeze before reading 2024 outcomes"). This document records the
> exact retained recipe, extracted from code/manifests on 2026-10-08,
> BEFORE the 2024 Savant parquet or Retrosheet archive was opened for
> modeling. 2024 is described as **"outcome-unread by this research
> line before authorization"** - the owner's prior modeling work used
> 2023-2024 development folds, so 2024 is NOT pristine.

## 1. Frozen recipe (the retained I3b chain)

### BF workload component
- **Features (exact active columns, from `run_corrected_history_2023.py:75`,
  `CHALLENGER_FEATURES`):** `start_capacity_shrunk_bf`,
  `start_capacity_median_bf_5`, `start_capacity_mean_bf`,
  `n_capacity_appearances`, `relief_mean_bf`, `actual_bf_mean_last5`,
  `actual_expanding_mean_bf`, `days_since_last_capacity`,
  `opp_team_k_rate_std`, `opp_team_k_rate_vs_hand`. All strictly-prior
  per row (manifest: `corrected-history-feature-manifest.md`).
- **Model:** `bf_distribution.fit_hazard` - L2 logistic stopping
  hazard (C=1.0), risk-set rows 1..36, index one-hots + features,
  median/mean-sd preprocessing; `predict_pmf` -> 37-category BF PMF;
  overflow extension via `kcount_combiner.extend_overflow_with_hazard`
  (hazard tail to cap 60; cap-120 sensitivity arm).
- **Training population:** arm B = expanding, strictly pre-origin.
  2023 lane fit hazards on 2023 rows pre-origin only (2022 entered via
  history features + constant fallback). **Transfer translation
  (pre-registered in transfer-validation-readiness-2026-10-08.md
  section 7 BEFORE any 2024 read): hazard-fit rows = 2022 + 2023 +
  2024-to-origin eligible first-pitcher rows.** This is a pool
  expansion relative to the 2023 lane's literal structure; recorded
  here so the deviation is explicit, not silent.

### PA strikeout-rate component
- **Shrinkage formula (`pa_k_baseline.prior_rates`, line 83):**
  `rate = (k + w * lg) / (n + w)` with **w = 150** (`W_SHRINK`, frozen
  constant). **Provenance of 150: FIXED BY PRE-REGISTRATION**
  (`pa-k-baseline-prereg.md`: "Arms: A = shrunk log5 blend (w=150
  frozen)"); it was neither tuned nor estimated from between-player
  variation. It stays frozen for this validation.
- **log5:** `p = sigmoid(logit(p_pitcher) + logit(p_batter) -
  logit(lg))` (`arm_a_probs`, line 100).
- **Eligible PA population:** terminal PAs (truncated_pa excluded) in
  first-pitcher games where the recorded pitcher == that game's first
  pitcher. **Pitcher relief appearances are EXCLUDED by construction**
  (a relief outing's pitcher != that game's first pitcher). Batter
  rates: rolled up over the same first-pitcher PA rows.
- **History window:** NO rolling window, NO decay - cumulative
  prior-rate aggregates over the whole available pool with strict
  `game_date < as_of` cutoff. Cross-season carryover: YES (2022 rows
  eligible for 2023 origins; 2022+2023 for 2024 origins).
- **League reference:** same prior pool (all entities), recomputed per
  origin at the as_of cutoff; cold start -> (lg, prior_n=0) -> rate
  equals the league rate.
- **Rate pool for the transfer (pre-registered):** 2022 + 2023 +
  2024-to-origin first-pitcher PAs.

### Opponent-card component
- **B1 proxy card:** most recent strictly-prior game's observed
  batting card (>= 9 distinct observed batters; the DH slot; no
  same-day doubleheaders). **B2 fallback:** league-average order when
  no eligible prior game exists.
- **p\* (`lineup_opportunity.p_star`):** `p* = sum_t S(t) p_t /
  sum_t S(t)`, S(t) = P(N >= t) from the BF PMF; p_t = log5 matchup
  probability cycling the card through batting order.

### Count combination
- `K|N=n ~ Binomial(n, p*)`; `kcount_combiner.combine_count(ext60,
  p*)` -> 24-category count PMF (support 0..22 + absorbing >=23;
  latent mean retained for xK). xBF = E[N] from ext60; xK = p* E[N].

## 2. Source/configuration hashes (recorded pre-read)

| Item | SHA256 |
| --- | --- |
| Savant 2023 parquet (approved) | `b9f9db9923badca17e551cf23be8429bfba984361732a8911bf0d68a40d5285f` |
| Savant 2022 parquet (approved) | `63d40a4955da73ab8f9b01d87d90dd676acdf8b7447c574a5edf807897724ce4` |
| Savant 2024 parquet (pre-read hash verify) | `de78a1893aa21e305153f5594987f85b40e4bc0cf572484e995a1416b3c49b33` |
| Checkpoint commit | `d3f8edb` (research(count): 2023 overhaul checkpoint) |
| Frozen contracts | kcount-integration-prereg `796a3606...`; pregame-opportunity-contract `2f3b9f22...`; i4-card-source `5fbedb77...`; i5-tail `2d58a7d2daba90c7cff2a24660076348be3bb967a12909db47561c7cf533b040` |

Retrosheet 2024 events acquired 2026-10-08 (30 .EV* files, 13.2 MB)
into the gitignored raw tree; digest recorded in the run manifest.

## 3. Evaluation contract (unchanged from the readiness doc)

- Origins: 2024-04-15 / 07-01 / 08-01 / 09-01; eval rows = 2024
  first-pitcher rows in each origin's window; FINAL 2024-10-01.
- Gate 0 (pre-model): Retrosheet-vs-Savant BF/PA reconciliation on
  the 2024 eval spine; **>= 99% row agreement required**, else STOP
  before forecasting/scoring and report the blocker. No silent
  definition repairs.
- Metrics via `eval_package.py` UNCHANGED: count-RPS, log score +
  floor accounting, signed mean bias (pred - act) for BF and K, MAE,
  milestone Brier + ge10/ge12 reliability, variance accounting, seeded
  PIT (20261001), per-origin + debut/sparse-history slices with
  sample-size warnings.
- Comparators: the frozen 2023 I3b recipe ONLY (recomputed on 2024
  chronology). No September challenger, no I5 revision, no shrinkage
  or decay tuning, no lineup-policy change, no calibration fitting,
  no mid-season refit of parameters.
- Claim ceiling: validates the RESEARCH CHAIN (proxy cards, realized
  first-pitcher identities) - not a deployable 8am pregame forecast.
  No betting-value claims (no matched 2024 odds in this lane).
- Proxy-card staleness/newer-than-origin flags and short-outing
  categories (debut / season-debut / insufficient-history / failed
  joins) recorded per row.
