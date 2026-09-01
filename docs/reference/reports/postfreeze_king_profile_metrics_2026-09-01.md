# Post-freeze KING-profile metrics (2026-09-01)

**Companion to:** `ssac27_policy_freeze_audit_2026-09-01.md`  
**Ensemble:** `0.60 production_sparse72_monotone + 0.40 production_final58_consensus` (`production/ops/live_krate_ensemble.json`)  
**Freeze:** `KING_PROFILE_AUG2026` @ `2026-08-21T16:10:00Z`  
**Lane definition:** deduped settled ledger rows with `game_date > 2026-08-21` **and** `passes_floor == True` (operational tickets with stake &gt; 0 under the live floor gate).

## Headline (honest)

| Lane | n | ROI | Win rate | CLV mean (pp) | CLV &gt;0 share | Date span |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| **Post-freeze KING floor** | **74** | **−1.55%** | 48.6% | +1.59 | 58.6% (n_clv=29) | 2026-08-22 → 2026-08-31 |
| Post-freeze KING · over | 45 | −24.6% | 37.8% | +0.58 | 63.2% (n=19) | same |
| Post-freeze KING · under | 29 | +29.3% | 65.5% | +3.51 | 50.0% (n=10) | same |
| Pre-freeze policy-search window · floor (context) | 172 | +2.56% | 50.0% | +0.75 | 58.5% (n=123) | 2026-07-30 → 2026-08-17 |

Source machine JSON (local/gitignored artifacts): `artifacts/odds_log/postfreeze_king_profile_metrics_20260901.json`.

## What this means

1. There **is** a real post-freeze sample now (n=74 KING-floor tickets over ~10 days) — larger than the demoted n=26 search lane, still short of DSR power targets (~98 / ~147).
2. Aggregate post-freeze ROI is **slightly negative**. Do **not** replace the demoted 26-bet ROI story with a claim of validated edge.
3. Side asymmetry dominates: **unders carry, overs bleed**. Any portfolio claim that ignores side is misleading.
4. CLV on the thin post-freeze CLV-available subset is mildly positive (~59% beat-close) — interesting, not conclusive (`building_sample`).
5. Broader floor-calibration tables that start at `2026-07-31` **mix pre- and post-freeze days** and must not be labeled “post-freeze OOS.”

## Watch-outs

- `passes_floor==False` rows often have `stake==0` (logged candidates, not bet). Always filter stake&gt;0 / passes_floor for money metrics.
- Deduped vs raw still matters for PnL.
- Freeze-day `2026-08-21` itself is excluded from the strict post lane (policy locked mid-day).
- Re-run this extract after each settle week; do not freeze these point estimates into the abstract as “edge.”
