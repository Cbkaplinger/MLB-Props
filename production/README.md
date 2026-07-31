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

Formal expected_K logging begins **2026-07-28** (first `projections.parquet`
slate). Grade only after Level 1 contains that date’s finals.

```powershell
python production/log_projections.py --allow-stale
# After Level 1 includes that slate date:
python production/grade_projections.py --preferred-only
python production/grade_projections.py --date 2026-07-28 --preferred-only
python production/grade_projections.py --all-logged --preferred-only
# Drop openers / 1st-inning injury exits (actual_PA < 9) + pregame OOS from MAE:
python production/grade_projections.py --all-logged --preferred-only `
  --exclude-abbreviated --exclude-out-of-support
```

Writes `artifacts/projection_log/projections.parquet` and `graded.parquet`.
Notebook §7 (`daily_projections.ipynb`) shows previous-day / all-time tables
and pred-vs-actual charts from the graded file.

## Post-freeze holdout (frozen stack, no refit)

```powershell
python production/refresh_features.py
python production/post_freeze_holdout.py
```

See `docs/reference/post_freeze_holdout.md`. Lineup train/serve skew:
`docs/reference/lineup_train_serve.md`.

## Odds ledger (edge / units / CLV)

Product layer — does **not** feed the strikeout trainer. Protocol:
`docs/reference/market_clv_gates.md`.

```powershell
# After log_projections: ingest full-board quotes (repeat --quote)
python production/log_odds_quotes.py --book novig --unit 50 --list-board
python production/log_odds_quotes.py --book novig --unit 50 `
  --quote "Sean Burke,6.5,-150,+130" --quote "Andre Pallante,4.5,+163,-185"

# SharpAPI live poll (requires SHARPAPI_KEY in repo-root .env)
# open replaces unclosed same-day tickets; stores tip time + minutes_to_tip_at_open
python production/poll_odds.py --snapshot open --unit 50

# Tip-aware CLV watcher (leave running; PC awake). Or one-shot close:
.\production\run_close_watcher.ps1
python production/close_watcher.py --once
python production/poll_odds.py --snapshot close


# Live recommendation board (preferred × odds × edge × units) — open the HTML
python production/odds_board.py --unit 50 --open-html

# Close + settle + exploratory threshold curve
python production/grade_odds_ledger.py --close "Logan Webb,2026-07-29,+115,-120"
python production/grade_odds_ledger.py --settle "Logan Webb,2026-07-29,4"
python production/grade_odds_ledger.py --status --curve
```

Writes `artifacts/odds_log/ledger.parquet` (+ `threshold_curve.parquet`).
SharpAPI free tier returns DraftKings + FanDuel only (60s delay). Model edge
math stays local — do not use SharpAPI +EV as your decision signal.
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
