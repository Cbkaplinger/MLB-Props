# Live assembly plan

**Status:** shipped (2026-07-28+) — historical scoring proven; daily ops under
`production/` (Statcast → features → log → grade → odds board → CLV ledger)  
**See also:** `docs/research/phase11_model_quality_gates.md`,
`docs/research/phase_d_population_findings.md`, `production/README.md`,
`docs/reference/market_clv_gates.md`

> Metric lane note: live deployment champion selection follows decision metrics
> (market-skill/risk/fairness). Single-model MAE values are tracked separately in
> the model-family lane (`docs/reference/governance_metric_stack.md`).

## Goal

```text
k_rate_hat  ← Live k-rate ensemble config (primary) OR legacy single-model artifact (fallback)
tbf_hat     ← Ridge thin-bullpen TBF     [joblib]
expected_K  ← k_rate_hat × tbf_hat
P(K ≥ L)    ← count_layer (binomial lines 2.5…9.5)
```

## Frozen inputs

| Piece | Location |
|---|---|
| k-rate (active) | `production/ops/live_krate_ensemble.json` |
| k-rate (fallback baseline) | `artifacts/models/lightgbm_krate_20260803_155401.*` |
| TBF | `artifacts/models/tbf_pa_ridge_workload_context_bullpen_20260728_035607.joblib` |
| Features | Ensemble member JSON `features` lists (58/72) + TBF 24 |
| Code | `src/Python/live_assembly.py`, `models/Strikeout-Model/predict_slate.py` |
| Daily ops | `production/` (see `production/README.md`) |
| Market / CLV | `src/Python/{market,odds_* ,sharp_odds}.py` + `production/{odds_board,poll_odds,close_watcher,grade_odds_ledger}.py` |

Current live blend configuration:

- `0.00 production_sparse72`
- `0.60 production_sparse72_monotone`
- `0.40 production_final58_consensus`

## Commands

```powershell
# Preferred daily chain (ops) — full morning loop in production/README.md
python production/ops/refresh_statcast.py          # cache + only new days
python production/ops/refresh_features.py --skip-training
python production/projections/log_projections.py
python production/odds/odds_board.py --unit 50 --roi-mode conservative
python production/odds/poll_odds.py --snapshot open --unit 50 --roi-mode conservative --from-recommendations

# Wiring proof on a date already in pitcher_training
python models/Strikeout-Model/predict_slate.py --historical-date 2025-09-20

# Fetch slate only / live score without logging
python production/ops/score_slate.py --dry-run
python production/ops/score_slate.py --live
python production/ops/score_slate.py --live --allow-stale
```

Outputs: `artifacts/live_scores/`, `artifacts/projection_log/`,
`artifacts/odds_log/`.

## Assembly checklist

1. ~~Slate IDs (RotoGrinders + MLB)~~ — `daily_lineups.build_daily_slate`
2. ~~As-of pitcher form from Level 2~~ — `live_assembly.build_live_feature_frame`
3. ~~Pregame rest / bullpen for slate date~~ — recomputed (not copied from last start)
4. ~~Announced opp lineup aggregates~~ — as-of batter rates + production means
5. ~~Score k-rate + TBF + count layer; log model IDs / hashes~~
5b. ~~Post-hoc Platt on `p_over_*` → `p_over_*_cal` (optional production pointer)~~
6. ~~Paper board + open tickets + tip-window closes~~ — `odds_board` / `poll_odds` / `close_watcher`
7. Team-code bridge: **`ARI` → `AZ`** for Statcast joins

Calibration: `src/Python/prob_calibration.py`; fit via
`models/Strikeout-Model/research/fit_prob_calibration.py`. Disable with
`score_frame(..., calibration_path=False)`. Findings:
`docs/research/prob_calibration_findings.md`.

## Known limits

- Level 1–2 include **2026 through the latest refreshed Savant day** (see
  `production/ops/refresh_statcast.py`). Re-run daily; Savant often lags overnight.
- Overnight RG vs MLB probable disagreements **dual-score** both pitchers
  (`starter_source`, `is_preferred` on MLB). Pass `--no-dual-starters` for RG-only.
  Strict fail: `--require-probable-match`.
- `--allow-stale` scores when rolling is >1 day behind the slate and sets
  `stale_days` in metadata — not for betting decisions.
- Playground counterfactuals: `playground/whatif_pitcher.py`. Manual quote paste:
  `playground/line_shopper.py` (canonical paper path is SharpAPI + ledger).
- Roster name resolve widens `active → 40Man → fullSeason` within the team.
- Phase D: announced openers are **out of support**; metrics remain conditional
  on `PA ≥ 9` (cutoff screen 5–10 keeps 9).
- Doubleheaders: schedule attach uses `###2` / `Game 2` markers when present,
  else nearest tip time; unmatched RG cards (stale matchups) are skipped with a
  warning rather than failing the slate.
