# Market Research Ops

This module builds open-market calibration/research artifacts without requiring close lines.

## Run All

```powershell
.\.venv\Scripts\python.exe production/ops/market_research/run_market_research.py
```

## Key Outputs

- `artifacts/odds_log/open_projection_quotes_raw.parquet`
- `artifacts/odds_log/open_proj_calibration_rows.parquet`
- `artifacts/odds_log/book_quality_scorecard.parquet`
- `artifacts/odds_log/line_price_calibration_grid.parquet`
- `artifacts/odds_log/line_price_correction_table.parquet`
- `artifacts/odds_log/open_model_edge_bin_monotonicity.parquet`
- `artifacts/odds_log/open_model_regime_drift_flips.parquet`
- `artifacts/odds_log/open_model_dk_fd_correction_deltas.parquet`
- `artifacts/odds_log/open_model_execution_sensitivity.parquet`
- `artifacts/odds_log/calibration_deploy_matrix.parquet`

## Live Testing Hook

`production/odds/odds_board.py` now supports:

```powershell
.\.venv\Scripts\python.exe production/odds/odds_board.py --unit 50 --roi-mode balanced
```

`--roi-mode balanced` enables all current open-era controls:

- line-price correction offsets
- line-aware edge floors
- deploy-matrix OFF segment blocking

Manual controls are still available:

```powershell
.\.venv\Scripts\python.exe production/odds/odds_board.py --unit 50 --apply-line-price-correction --apply-line-floors --apply-deploy-matrix-filter --edge-floor 0.16
```

## Deploy Matrix Auto-Disable

`build_calibration_deploy_matrix.py` now auto-assigns `reason_code=recent_drift_flip_spike`
when a segment has enough recent observations and its 14-day correction-sign flip rate
spikes above policy threshold. This is intended to avoid forcing stale correction
segments during unstable regimes before close-line CLV governance is available.
