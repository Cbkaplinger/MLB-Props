# Results Dashboard Diagnostics (Sections 11c-11f)

This guide documents the residual-diagnostics workflow added to
`production/notebooks/results_dashboard.ipynb` for separating strikeout-rate error from
workload (TBF/PA) error and monitoring daily model health.

## Why this exists

The prop mean is:

- `expected_K = k_rate_pred * projected_tbf`

When live results drift, this decomposition identifies whether error is mostly:

- strikeout-rate modeling (`k_rate_pred`),
- workload modeling (`projected_tbf`), or
- interaction between both.

## Section map

- **17 (Appendix A)**: decomposition baseline
  - Compares full error vs oracle-PA and oracle-rate counterfactuals.
  - Writes row-level artifact:
    - `artifacts/odds_log/k_error_decomposition.parquet`
- **18 (Appendix B)**: stratified residual diagnostics
  - Buckets by matchup tier, lineup source, rest bucket, and side.
  - Surfaces where `err_k_rate` and `bias_tbf` concentrate.
- **19 (Appendix C)**: chronological recalibration experiment
  - Compares raw vs Platt-style vs isotonic mapping on `k_rate_pred`.
  - Uses chronological folds once enough distinct game dates exist.
  - Writes daily trend snapshot:
    - `artifacts/odds_log/k_error_decomposition_daily.parquet`
- **20 (Appendix D)**: model health scorecard
  - Fast PASS/WARN checks for daily monitoring.
  - Writes daily scorecard snapshot:
    - `artifacts/odds_log/model_health_scorecard_daily.parquet`

## Key columns and definitions

From section 11c artifacts:

- `err_full = (k_rate_pred * projected_tbf) - actual_K`
- `err_rate_oracle_pa = (k_rate_pred * actual_PA) - actual_K`
- `err_pa_oracle_rate = (actual_k_rate * projected_tbf) - actual_K`
- `err_tbf = projected_tbf - actual_PA`
- `err_k_rate = k_rate_pred - actual_k_rate`

Interpretation:

- If `MAE(err_rate_oracle_pa)` is much lower than `MAE(err_full)`, TBF/PA is
  the bigger issue.
- If `MAE(err_pa_oracle_rate)` is much lower than `MAE(err_full)`, k-rate is
  the bigger issue.

## Daily operating loop

1. Run focused monitors first:
   - `production/notebooks/results_kpi_monitor.ipynb`
   - `production/notebooks/results_calibration_lab.ipynb`
   - `production/notebooks/results_gate_policy.ipynb`
2. Run `production/notebooks/results_dashboard.ipynb` through section 20 only when
   deep-dive verification is needed.
2. Confirm artifacts updated:
   - `k_error_decomposition.parquet`
   - `k_error_decomposition_daily.parquet`
   - `model_health_scorecard_daily.parquet`
3. Read scorecard WARN checks first.
4. If warnings persist 3+ snapshots, open a targeted modeling task:
   - matchup-tier k-rate errors (`avg_matchup` / `favorable_matchup`),
   - under-side `bias_tbf`,
   - long-rest (`10+`) workload bias.
5. Run scenario policy sweep and compare side-specific behavior:
   - `production/ops/policy_simulator.py --thresholds "0.08,0.10,0.12,0.14,0.16,0.18"`
6. Follow the formal daily action policy:
   - `docs/reference/daily_kpi_protocol.md`

## Notes

- The dashboard input is deduped to one prop per `(game_date, pitcher, line)`
  via `dedupe_ledger_props`, so DK/FD duplicate tickets are not double-counted
  in these diagnostics.
- Recalibration in section 19 is a diagnostic gate. Do not deploy any mapping
  to production until chronological fold results remain stable over enough dates.

For a concise narrative-first daily read, use
`analysis/model_results/model_results_story.ipynb`.
