# Pitcher Outs Expansion Plan

Purpose: reuse the strikeout production stack to add pitcher-outs rigor without
destabilizing current strikeout operations.

## Scope boundary

- Strikeouts remain the only production claim and promotion lane.
- Outs work runs as shadow research until governance gates are met.

## Reused components

- Watcher + quote capture (`production/odds/close_watcher.py`)
- Ledger settle flow (`production/odds/grade_odds_ledger.py`)
- Runtime monitors (`production/ops/build_runtime_monitoring_snapshot.py`)
- Operator dashboard (`production/app/dashboard_streamlit.py`)
- Daily automation (`production/ops/run_daily_kpi_loop.py`)

## Current shadow artifacts

- `artifacts/odds_log/watcher_aux_quotes.parquet`
- `artifacts/odds_log/aux_market_shadow_prop_level.parquet`
- `artifacts/odds_log/aux_market_shadow_summary.json`

## Promotion checklist for outs

1. **Data coverage**
   - stable open/close coverage by book and line
   - enough settled rows with matched outs outcomes
2. **Shadow quality**
   - positive/neutral CLV behavior by regime
   - no concentrated risk pockets by maturity or odds bucket
3. **Model layer**
   - leakage-safe outs model with chronological validation
   - calibration and reliability diagnostics on walk-forward splits
4. **Governance lane**
   - shadow policy sweep (ROI/risk/market-skill)
   - fail-closed gates in place before any live promotion
5. **Production decision**
   - promote only if outs clears sample-size and risk thresholds without
     degrading strikeout operations

