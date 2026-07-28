# Production ops (daily scoring)

Cron-friendly CLIs for the live strikeout stack. **Not a web backend.**

## What lives where

| Layer | Path | Responsibility |
|---|---|---|
| Library | `src/Python/` | Statcast I/O, pipeline L1–L3, slate scrape, feature assembly, scoring |
| Research / train | `Models/` | Nested CV, HPO, freeze training, ablations |
| Ops | `production/` | Daily refresh + score orchestration (this folder) |
| Future API | *(not yet)* | Thin HTTP/job layer that imports `Python.*` or shells these scripts |

ML logic, feature engineering, and model I/O stay in `src/Python/`. Production scripts only parse args, call library functions, and print/exit for schedulers. When you add a backend, put request routing there — do not duplicate feature or model code.

## Daily flow

```text
1. refresh_statcast   → incremental Savant YTD (cache + only new days)
2. refresh_features   → pipeline games → rolling → training (incl. projection year)
3. score_slate        → RotoGrinders + as-of features → expected_K / line probs
```

Or one shot: `python production/run_daily.py`

## Commands

```powershell
# Statcast: reuse parquet; fetch only days after cached max through yesterday ET
python production/refresh_statcast.py
python production/refresh_statcast.py --year 2026 --refresh-trailing-days 1

# Rebuild Level 1–3 including the projection season
python production/refresh_features.py
python production/refresh_features.py --skip-training   # L1–L2 only (faster live)

# Score today's slate (needs fresh rolling; --allow-stale for degraded)
python production/score_slate.py --live
python production/score_slate.py --dry-run

# Interactive board (expected_K + fair American 3.5–8.5, dual RG/MLB stacked)
# Open: production/daily_projections.ipynb
# (scores via a fresh subprocess — same path as the terminal; avoids Jupyter LightGBM AVs)

# Full chain
python production/run_daily.py
python production/run_daily.py --skip-features --allow-stale
```

Outputs:

- Savant: `Data/Savant-Data/regular/<year>/statcast_<year>_regular.parquet`
- Features: `Data/processed/*.parquet`
- Scores: `artifacts/live_scores/`

## Dual RG / MLB starters

Live scoring dual-emits rows when RotoGrinders and MLB probable IDs disagree
(`starter_source`, `starter_disagreement`, `is_preferred`). Prefer the MLB
row near lock; compare both early. **Batting orders always come from
RotoGrinders** — dual scoring only swaps the SP.

```powershell
python production/score_slate.py --live --allow-stale
# RG-only: add --no-dual-starters
```

## Projection log + grading

```powershell
python production/log_projections.py --allow-stale
# After Level 1 includes that slate date:
python production/grade_projections.py --preferred-only
python production/grade_projections.py --date 2026-07-27 --preferred-only
```

Writes `artifacts/projection_log/projections.parquet` and `graded.parquet`.
Dashboard later; hold off for now.

## Playground demos

Counterfactuals and toys live under `playground/` (e.g. pitcher vs every
team). See `playground/README.md`.

## Incremental Statcast

`Python.statcast.update_statcast_season` is the production path:

- Missing file → full YTD download through yesterday (ET).
- Existing file → fetch `cached_max + 1` … `yesterday` only.
- Optional `--refresh-trailing-days 1` re-pulls the last cached day for late Savant fixes.
- Already current → no network fetch (`skipped_fetch: true`).

Full re-download remains available via `download_statcast_season` for repairs.
