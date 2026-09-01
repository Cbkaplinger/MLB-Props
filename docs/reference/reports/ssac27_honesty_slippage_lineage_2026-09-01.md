# Artifact lineage — quant_honesty / slippage vs authoritative replay (SSAC27 item 7)

**Date:** 2026-09-01  
**Status:** Documented intentional freeze (no silent rewrite of bootstrap/DSR artifacts)

## Authoritative point estimates (use in manuscript headlines)

Source: `artifacts/odds_log/open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.json`

| Metric | Value |
| --- | ---: |
| ROI | 0.4363 |
| Sharpe | **0.4438** |
| max drawdown | **0.1905** |
| Calmar | **2.2903** |
| PnL (u, 1u=50) | +24.17 |

These are the **policy-search** n=26 lane numbers (pre-freeze; demoted from deployment claims per SSAC #4).

## Frozen diagnostic artifacts (do not treat as conflicting headlines)

| Artifact | Sharpe | maxDD | Calmar | Role |
| --- | ---: | ---: | ---: | --- |
| `quant_honesty_aug21_summary.json` `baseline_metrics` | 0.4352 | 0.3685 | 1.1841 | PSR/DSR/bootstrap CIs / power plan; Sharpe used in DSR pipeline at freeze |
| `slippage_sensitivity_top3_floor12_aug21.csv` | 0.4352 @ 0pp | — | — | Haircut sensitivity on same 26-bet set |

**Why not rewrite:** Re-running Bailey–LdP DSR/bootstrap from a different Sharpe definition would change `dsr`/`psr`/CIs without a pinned regeneration script in-repo. The manuscript already cites **replay** for profile points and **honesty JSON** for DSR/CIs; §8.3 cites the slippage CSV Sharpe column as-is.

**Rule going forward:** Headline ROI/Sharpe/DD/Calmar → replay JSON. Trial-adjusted stats → honesty JSON. Slippage table → slippage CSV. Never mix without a lane tag.

## Equity curve regeneration

Figure 3 is now regenerable via `docs/paper/make_figures.py` → `fig_equity_top3_vs_top1()` from  
`artifacts/odds_log/open_top3_transfer_bestfloor_picks_aug21_deduped_top3_from_dedupedsweep.csv`  
(`config` ∈ {top1,top3}, `best_floor=0.12`; PnL_u = stake × rpd / 50).
