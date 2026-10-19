# METRIC_SCHEMA — market-eval-v1 registered + proposed metrics

**Date:** 2026-10-14 (correction C2). Layer-specific metric schema for the
scoring run. Reuses persisted errors where they exist; anything beyond the
registered set is listed as PROPOSED and requires explicit approval BEFORE
execution.

## Layer 1 — PA / projected-state (payload PMFs vs realized K)

Persisted errors exist in `bf-workload-v1\data\start_metrics_v2.parquet`
(`base_h3_*`, `base_l5_*`) and are REUSED verbatim (never recomputed):

| Metric | Column(s) | Definition (as persisted upstream) |
| --- | --- | --- |
| Count RPS | `base_{h3,l5}_rps` | summed ranked probability score over the PMF |
| Count log score | `base_{h3,l5}_logscore` | log score with 1e-12 floor |
| Mean-K error | `base_{h3,l5}_rmse_mean_k` | RMSE of E[K] |
| Milestone (PMF-tail exceedance) Brier | `base_{h3,l5}_brier_ge6/8/10/12` | Brier of P(K >= m) at minimum_k m in {6,8,10,12} |

## Layer 2 — count layer (per-start, at matched starts)

Same persisted columns restricted to the matched-contract starts; reported
alongside the full-cohort values. No recompute.

## Layer 3 — market layer (registered scoring outputs)

### Primary probability-skill metric (the PIN)

- **Multi-class Brier at matched contracts**: ONE observation per
  (start, line, side) row of `matched_contracts.parquet`; classes
  {win, push, lose}; `Brier = mean over rows of sum_c (p_c - y_c)^2`.
- Competitors on IDENTICAL matched contracts: H3-raw (`p_h3_*` mapped by
  side), LOG5-raw (`p_l5_*`), de-vig market (`p_market`; push mass 0 —
  disclosed limitation on integer lines; this cohort has zero integer-line
  contracts).
- Outcome: realized K from `start_metrics_v2` via (game_pk, pitcher,
  pitch_half); half lines never push; integer-line push = explicit refund
  class (registered + tested; unexercised by real data).
- **Anti-double-counting (PIN)**: complementary over/under sides share one
  realization and are NOT independent. Bootstrap at the slate-date level is
  the declared correlation handling; effective counts (distinct
  (start, line) pairs, distinct starts, distinct slate dates) are reported
  ALONGSIDE contract-side counts in `skill_metrics.json`.
- **Uncertainty**: paired slate-date bootstrap, 2000 resamples, seed
  20261001, resampling unit = game_date, identical resample indices across
  all competitors; 95% percentile intervals for each competitor's Brier and
  for the paired skill diffs (h3 - market, l5 - market, h3 - l5).
- Breakdowns: per tier (Tier A primary / Tier B separately labeled
  sensitivity), per book, per side.
- Secondary: binary log loss on non-push rows (1e-12 floor), same
  competitors and breakdowns.

### Paper-betting metrics (reported separately from probability skill)

| Metric | Definition |
| --- | --- |
| Paper ROI | sum(pnl_units) / n_bets; flat 1-unit stakes |
| Paper PnL | sum(pnl_units); win +stake*(d-1), lose -stake, push 0 |
| Win rate | wins / (wins + losses) (pushes excluded) |
| CLV | `clv_pct = (d_bet - d_close)/d_close` vs the bet book's OWN closing side price; bets without a closing ref keep their ledger row but are excluded from CLV stats with the count disclosed |
| ROI uncertainty | slate-date bootstrap (ratio estimator; separate draw stream from the skill bootstrap, same seed family, documented) |

Settlement semantics: half line L -> over wins at K >= ceil(L); integer L ->
push at K = L (stake refunded, PnL 0), over at K >= L+1, under at K <= L-1.

## PROPOSED additional outcome analyses (NOT registered; require explicit
owner approval BEFORE execution — listed here to make them explicit)

1. **Median-K error and interval coverage** at the count layer (central
   50%/90% PMF intervals): not persisted in start_metrics_v2; would need a
   small addition to the persisted-error builder or a recompute pass.
2. **Calibration curves / reliability tables** for the contract-level win
   probabilities (H3 vs market), by tier and line bucket.
3. **Per-line-bucket skill decomposition** (e.g., 4.5-5.5 vs 6.5+) with the
   same slate bootstrap.
4. **CLV-conditional ROI** (paper ROI split by positive/negative realized
   CLV) as a market-efficiency diagnostic.
5. **Ladder-correlation-aware portfolio metrics**: per-start aggregated
   exposure (max simultaneous stake, per-start PnL) instead of per-bet
   independence; the scoring run reports the multiple-bets-per-start counts
   (3,731 starts; max 5 bets/start) but does NOT build a portfolio P&L.
6. **Tier B (2024, clock proxy) as sensitivity-only replication** of every
   primary metric — implemented as separate fields, never pooled with
   Tier A.

None of these touches a live production path; any adoption would be a
versioned card correction executed under a new authorized run.
