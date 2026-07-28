# Live assembly plan

**Status:** v1 wired (2026-07-28) — historical scoring proven; daily ops under
`production/` (incremental Statcast + feature refresh + score)  
**See also:** `docs/phase11_model_quality_gates.md`,
`docs/phase_d_population_findings.md`, `production/README.md`

## Goal

```text
k_rate_hat  ← LightGBM production (180)  [frozen booster]
tbf_hat     ← Ridge thin bullpen         [joblib]
expected_K  ← k_rate_hat × tbf_hat
P(K ≥ L)    ← count_layer (binomial lines)
```

## Frozen inputs

| Piece | Location |
|---|---|
| k-rate | `artifacts/models/lightgbm_krate_20260728_033241.*` |
| TBF | `artifacts/models/tbf_pa_ridge_workload_context_bullpen_20260728_035607.joblib` |
| Features | JSON `features` list (180) + TBF 24 |
| Code | `src/Python/live_assembly.py`, `Models/Strikeout-Model/predict_slate.py` |
| Daily ops | `production/` (see `production/README.md`) |

## Commands

```powershell
# Preferred daily chain (ops)
python production/run_daily.py
python production/refresh_statcast.py          # cache + only new days
python production/refresh_features.py --skip-training
python production/score_slate.py --live

# Wiring proof on a date already in pitcher_training
python Models/Strikeout-Model/predict_slate.py --historical-date 2025-09-20

# Fetch slate only
python production/score_slate.py --dry-run

# Live as-of score (needs rolling through yesterday; --allow-stale for degraded)
python production/score_slate.py --live
python production/score_slate.py --live --allow-stale
```

Outputs land in `artifacts/live_scores/`.

## Assembly checklist

1. ~~Slate IDs (RotoGrinders + MLB)~~ — `daily_lineups.build_daily_slate`
2. ~~As-of pitcher form from Level 2~~ — `live_assembly.build_live_feature_frame`
3. ~~Pregame rest / bullpen for slate date~~ — recomputed (not copied from last start)
4. ~~Announced opp lineup aggregates~~ — as-of batter rates + production means
5. ~~Score k-rate + TBF + count layer; log model IDs / hashes~~
6. Team-code bridge: **`ARI` → `AZ`** for Statcast joins

## Known limits

- Level 1–2 include **2026 through the latest refreshed Savant day** (see
  `production/refresh_statcast.py`). As of 2026-07-28 refresh: through
  **2026-07-27**. Re-run daily; Savant often lags overnight.
- Overnight RG vs MLB probable disagreements **dual-score** both pitchers
  (`starter_source`, `is_preferred` on MLB). Pass `--no-dual-starters` for RG-only.
  Strict fail: `--require-probable-match`.
- `--allow-stale` scores when rolling is >1 day behind the slate and sets
  `stale_days` in metadata — not for betting decisions.
- Playground counterfactuals: `playground/whatif_pitcher.py` (pitcher vs all teams).

- Phase D: announced openers are **out of support**; metrics remain conditional
  on `PA ≥ 9` (cutoff screen 5–10 keeps 9).
- Doubleheaders: schedule attach uses `###2` / `Game 2` markers when present,
  else nearest tip time; unmatched RG cards (stale matchups) are skipped with a
  warning rather than failing the slate.