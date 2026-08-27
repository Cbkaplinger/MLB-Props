# TBF spine — Phase A rest + Phase B lagged workload

**Status:** implemented (research/TBF track; not in frozen k-rate registry)  
**Date:** 2026-07-27  
**Code:** `src/Python/pitcher_rolling.py`, `src/Python/pipeline/rolling.py`,
`src/Python/features.py`  
**Artifacts:** rebuilt `pitcher_rolling.parquet` / `pitcher_training.parquet`

## What landed

### Phase A — starter rest

| Column | Meaning |
|---|---|
| `days_rest` | In-season calendar days since previous starter appearance; null on season debut |
| `days_rest_capped` | `min(days_rest, 15)`; null on debut |
| `is_season_debut` | 1 if no prior in-season appearance |
| `rest_is_long_gap` | 1 if `days_rest > 15` (IL / rehab / phantom rest flag) |

Rules: season-scoped (no offseason carry); same-date starts share first-row rest
so doubleheaders do not invent zero-day rest from each other.

### Phase B — lagged volume (TBF covariates)

Leakage-safe means of prior starts (current start excluded):

- `PA_P5` / `PA_P10` / `PA_P20`
- `Outs_P5` / `Outs_P10` / `Outs_P20`
- `Pitches_P5` / `Pitches_P10` / `Pitches_P20`

Same-game `PA` / `Outs` / `Pitches` remain labels/oracle only (or dropped raw).

## Safety vs frozen k-rate

All of the above are **`is_experimental_feature`** for the k-rate allow-list.
Legacy single-model freeze lineage did not consume these TBF covariates as
k-rate inputs (they remained experimental on the rate path). Current deployment
still keeps these covariates on the TBF lane, not the k-rate sparse-set lane.

`model_feature_names(..., include_experimental=True)` exposes them for TBF
research fits.

## Coverage snapshot (full 2023–2025 training frame after rebuild)

- Season debut rate ≈ 7.0%
- Long-gap rate ≈ 4.0%
- `PA_P5` null ≈ 3.8% (early history)
- Typical `days_rest` median 6 (starters)

## Status updates

- Live slate assembly (k-rate + TBF + count layer): **shipped**.
- Phase D opener/piggyback pregame role labeling: **still open**.

## Phase A.1 + C (landed)

- `rest_gap_severity`, `is_career_mlb_debut` on rest block
- `bullpen_team_games.parquet` + `bullpen_*_L{1,2,3}d` lookbacks
- TBF set `workload_context_bullpen` **frozen**
  (`docs/research/tbf_first_model_findings.md`)
- Count layer v1 chrono-scored (`docs/research/count_layer_findings.md`)
- See `docs/research/phase_d_population_findings.md` for the population-policy addendum

## First model

Fitted: `docs/research/tbf_first_model_findings.md` (`models/TBF-Model/train.py`).

## Pickup

```powershell
python -m Python.pipeline.games
python -m Python.pipeline.rolling
python -m Python.pipeline.training
python -m pytest tests/test_pitcher_rolling.py tests/test_bullpen.py tests/test_pipeline.py tests/test_feature_safety.py tests/test_tbf.py -q
```
