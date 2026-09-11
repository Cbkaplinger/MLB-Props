# Freeze playbook — 2026-09-11 (reproducibility contract)

> Owner order: document what is necessary so this process is reproducible.
> An auditor with this repo at this commit, the ignored data lake, and the
> two API keys must be able to reconstruct every ticket and every number.

## 1. Frozen stack (verify before anything)

| Piece | Pinned value | Where |
|---|---|---|
| k-rate ensemble | train 2023–24, sparse72×0.0 / mono×0.6 / final58×0.4 | `production/ops/live_krate_ensemble.json` |
| TBF ridge | 2026-07-28 stem | L3 `pitcher_training.parquet` lineage |
| Count layer | Poisson (`COUNT_LAYER_FAMILY_DEFAULT="poisson"`) | `src/Python/count_layer.py` |
| Calibrator | WS1c per-line Platt pointer | `artifacts/models/prob_calibration_production.json` (joblib has `ws1c`) |
| Sizing | 1/16-Kelly (`DEFAULT_KELLY_FRACTION = 0.0625`), $50 unit | `src/Python/market.py` |
| Odds in trainer | never (`market_clv_gates.md`) | — |

## 2. Live policy version (this freeze)

`line_floor_policy.json` `line_floor_v1` (2.5→0.20, 3.5→0.18, 4.5→0.14,
5.5→0.14, 6.5/7.5→0.12, 8.5→0.14, 9.5→0.16) + `kpi_policy.json`
(`edge_cap` 0.20, `offset_cap` 0.02, 4.5-over veto, 2.5/3.5 probation 0.18,
TBF≥15, postseason HOLD 2026-09-27). `robust_refusal` measured and
REVERTED same day (2025 −0.2% vs base +4.2%; code retained, key absent).
Regression pin: `tests/test_live_stack_pin.py` (fails on any drift).

## 3. Reproduce (commands from repo root, `.venv` python, $0 unless noted)

```powershell
# Guard: frozen stack intact (336 tests incl. pin)
.\.venv\Scripts\python.exe -m pytest tests/ -q --ignore=tests/test_notebooks.py
# Today's board (spends one SharpAPI fetch; backs up recs first)
Copy-Item artifacts/odds_log/recommendations.parquet artifacts/odds_log/recommendations_pre_<date>.parquet
.\.venv\Scripts\python.exe production/odds/odds_board.py --unit 50 --roi-mode conservative --write-quotes artifacts/odds_log/sharp_quotes_latest.parquet --show-all
# Weekly measurement (no live change)
.\.venv\Scripts\python.exe production/ops/run_weekly_policy_settle_pack.py
.\.venv\Scripts\python.exe production/ops/market_research/ledger_gate_stacker.py
# Lake measurements (needs ignored data lake on disk; spends ~0 credits)
.\.venv\Scripts\python.exe production/ops/market_research/slate_shock_join.py
# Closeout (spends ~300 credits/day; refuses today/future and past 2026-09-28)
.\.venv\Scripts\python.exe production/ops/market_research/pull_regular_season_closeout.py
```

## 4. Data lineage (raw JSON is truth, parquet is projection)

- Paid lake: `data/Odds-Historical/theoddsapi/raw/{market}/{snapshot}/{event}.json`
  (9,189 envelopes, vendor `timestamp/previous/next` kept in
  `snapshot_envelope.parquet`; 12 post-commence closes flagged, never graded).
- Friend opens: `data/Odds-Open-Close-2025-2026/` (same vendor `event_id`s).
- Normalizer: `pull_oddsapi_historical.py` (re-run never re-spends).
- Probabilities: `universe_panel_live.parquet` (71,080 line-points, frozen).
- Money: `juiced_replay_candidates.parquet` (19,613 rows, rejects kept) +
  `juiced_replay_report.json`. Close-invalid rows excluded from CLV (2,075/2,077).
- Totals: `featured_totals.parquet` (220,482 rows; calendar clocks, not first-pitch).

## 5. Golden numbers (cite, do not recompute)

`docs/reference/golden_metrics.md`. Canonical: juiced flat all-books +7.3%
(n=2,077) / DK+FD +12.3% (n=982) / 2025 +4.2% / 2026 +12.6% confirmatory;
cap-only 2025 +8.0% (n=912). Live paper: `paper_quant_report.json`
(full +2.7% → veto +6.5%, 36 days). Universe skill −0.0043, opener +0.044.
