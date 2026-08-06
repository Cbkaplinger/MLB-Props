# Production ops (daily scoring + paper trading)

Cron-friendly CLIs for the live strikeout stack and the **odds / CLV product
layer**. **Not a web backend.** Odds never train LightGBM — see
`docs/reference/market_clv_gates.md`.

## What lives where

| Layer | Path | Responsibility |
|---|---|---|
| Library | `src/Python/` | Statcast I/O, pipeline L1–L3, slate scrape, feature assembly, scoring, market math, odds ledger, **CLV skill checks** (`skill_stats.py`) |
| Research / train | `Models/` | Nested CV, HPO, freeze training, ablations |
| Ops | `production/` | Daily refresh, projection log, SharpAPI board/ledger, close watcher, **CLV skill dashboard** (`results_dashboard.ipynb`, Sections 11-18) (this folder) |
| Artifacts | `artifacts/` (gitignored) | `projection_log/`, `odds_log/` (incl. CLV reliability + BCa sweep + next-50 checkpoint), models, research dumps |
| Future API | *(not yet)* | Thin HTTP/job layer that imports `Python.*` or shells these scripts |

ML logic and model I/O stay in `src/Python/`. Production scripts parse args,
call library functions, and print/exit for schedulers.

## Canonical morning loop

```text
1. refresh_statcast          → incremental Savant through yesterday ET
2. refresh_features --skip-training  → Level 1–2 (add full refresh when needed)
3. log_projections           → preferred board → artifacts/projection_log/
4. grade_projections         → attach actuals when Level 1 has finals
5. odds_board --unit 50      → model × DK/FD; BET-only terminal; full slate parquet/HTML
6. poll_odds --snapshot open --unit 50
                             → lock bet-time tickets (replaces unclosed same-day)
7. grade_odds_ledger --status
```

Interactive morning board: `production/daily_projections.ipynb`
(yesterday grades → today xK → edges → CLV table → CLV skill tracker).

```powershell
cd C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props

.\.venv\Scripts\python.exe production/refresh_statcast.py
.\.venv\Scripts\python.exe production/refresh_features.py --skip-training
.\.venv\Scripts\python.exe production/log_projections.py --allow-stale
# log_projections → score_frame applies production Platt calibrator when
# artifacts/models/prob_calibration_production.json exists (raw p_over_* kept;
# p_over_*_cal + calibration_version logged; fair_amer / odds prefer cal).
```

Probability calibration (research / promote):

```powershell
.\.venv\Scripts\python.exe Models/Strikeout-Model/research/fit_prob_calibration.py --method both
.\.venv\Scripts\python.exe Models/Strikeout-Model/research/fit_prob_calibration.py --method both --set-production
```

See `docs/research/prob_calibration_findings.md`. Edge floor is frozen at
**12%** as of the 2026-08-06 freeze + same-day reaffirmation; do not retune
from calibrator-induced edge shrinkage in either direction. See
`docs/research/floor_freeze_log.md` for the canonical record.
.\.venv\Scripts\python.exe production/log_projections.py
# if rolling is a day behind: add --allow-stale

.\.venv\Scripts\python.exe production/grade_projections.py --all-logged --preferred-only `
  --exclude-abbreviated --exclude-out-of-support

.\.venv\Scripts\python.exe production/odds_board.py --unit 50
# optional: --open-html | --show-all
# watch for: preferred with no scored quote (...)

.\.venv\Scripts\python.exe production/poll_odds.py --snapshot open --unit 50
.\.venv\Scripts\python.exe production/grade_odds_ledger.py --status
```

Requires `SHARPAPI_KEY` in repo-root `.env` (see `.env.example`). Free tier =
DraftKings + FanDuel (60s delay). **Model edge math stays local** — do not use
SharpAPI +EV as the decision signal.

## Catch-up opens (late markets)

First open of the day **locks** prices. If preferred starters later get K lines
(Pallante-style miss), **append only**:

```powershell
.\.venv\Scripts\python.exe production/poll_odds.py --snapshot open --append --unit 50
```

Do **not** re-run bare `--snapshot open` after the morning lock — default
**replace** wipes unclosed same-day tickets and rewrites bet-time prices.
`--append` only adds keys that are not already in the ledger.

## CLV close watcher

```powershell
# Leave running after morning open (PC awake). Ctrl+C to stop.
.\.venv\Scripts\python.exe production/close_watcher.py
# or: .\production\run_close_watcher.ps1

# One-shot fallback:
.\.venv\Scripts\python.exe production/poll_odds.py --snapshot close
```

Watcher fills closes when tip is in **T−15m … T+5m**. Idle sleeps until the next
window (no SharpAPI). Cross-book close is on by default (`ok_cross_book`); past
window / missing market → `close_status=unavailable`.

This is **not** the same as `--snapshot open --append` (that only creates new
tickets).

## Settle + skill curve

```powershell
.\.venv\Scripts\python.exe production/grade_odds_ledger.py --auto-settle-api --status --curve

# Manual overrides when needed:
.\.venv\Scripts\python.exe production/grade_odds_ledger.py --settle "Logan Webb,2026-07-29,4"
.\.venv\Scripts\python.exe production/grade_odds_ledger.py --close "Logan Webb,2026-07-29,+115,-120"
```

Writes / updates `artifacts/odds_log/ledger.parquet` and
`threshold_curve.parquet`. Skill bar / n_clv ≥ 150 at floor ≥ 12% rules:
`docs/reference/market_clv_gates.md` and
`docs/research/floor_freeze_log.md`. The dashboard Sections 11-18 also write
`clv_reliability.parquet`, `edge_band_discrete.parquet`,
`clv_floor_bca.parquet`, and `next_50_checkpoint.json` (see
`production/results_dashboard.ipynb`).

## Commands (reference)

```powershell
# Statcast
python production/refresh_statcast.py
python production/refresh_statcast.py --year 2026 --refresh-trailing-days 1

# Features
python production/refresh_features.py
python production/refresh_features.py --skip-training

# Score only (also used by the notebook worker)
python production/score_slate.py --live
python production/score_slate.py --dry-run
python production/run_daily.py
python production/run_daily.py --skip-features --allow-stale

# Manual quotes (no API) — optional fallback
python production/log_odds_quotes.py --book novig --unit 50 --list-board
```

Outputs:

| Path | Role |
|---|---|
| `Data/Savant-Data/regular/<year>/…` | Savant cache |
| `Data/processed/*.parquet` | L1–L3 features |
| `artifacts/live_scores/` | One-off `score_slate` dumps |
| `artifacts/projection_log/projections.parquet` | Logged model boards (replace-by-date) |
| `artifacts/projection_log/graded.parquet` | Graded actuals |
| `artifacts/odds_log/recommendations.parquet` | Full slate edges (overwrite each board run) |
| `artifacts/odds_log/ledger.parquet` | Durable paper tickets |
| `artifacts/odds_log/threshold_curve.parquet` | Exploratory edge sweep |
| `artifacts/odds_log/clv_reliability.parquet` | Dashboard §11 weekly decile calibration |
| `artifacts/odds_log/edge_band_discrete.parquet` | Dashboard §12 per-`[f,f+1)` band table (BCa CIs) |
| `artifacts/odds_log/clv_floor_bca.parquet` | Dashboard §18a authoritative BCa floor sweep |
| `artifacts/odds_log/next_50_checkpoint.json` | Dashboard §18b pre-registered decision rule + ledger SHA-256 |

## CLV skill dashboard (`production/results_dashboard.ipynb`)

Skill tracker that sits on top of `artifacts/odds_log/ledger.parquet`.
Sections 1-10 (cumulative ROI sweep, etc.) pre-date the 2026-08-06 batch.

**Sections 11-18 (added 2026-08-06, see `docs/research/notebook_change_log.md`):**

- §11 — CLV-vs-realized-win-rate reliability + two-proportion z-test (writes `clv_reliability.parquet`; `skill_stats.two_proportion_z_test`)
- §12 — discrete-band `[f, f+1)` flat-1u ROI with **BCa** CIs (writes `edge_band_discrete.parquet`; `skill_stats.bootstrap_bca_ci`)
- §13 — rolling 30-bet CLV with ±2 SE ribbon (`skill_stats.rolling_stat_with_se`)
- §14 — stake-weighted `sum(clv × stake)/sum(stake)` with BCa CI (`skill_stats.stake_weighted_bootstrap_ci`); reveals whether Kelly-sized bets are amplifying less-skillful CLV
- §15 — per-band CLV distribution histograms (stacked win/loss)
- §16 — pseudo-ROC of `clv_pp ≥ t` as a classifier of `result == win` (AUC)
- §17 — CLV outcome-pairing `(p_market, p_close)` scatter by result + 2×2 contingency + risk ratio
- §18a — **BCa** CLV floor sweep (the authoritative one; Section 10's percentile sweep stays for back-compat; writes `clv_floor_bca.parquet`)
- §18b — pre-registered **next-50-bet** checkpoint (writes `next_50_checkpoint.json`: timestamp + ledger SHA-256 + universe-as-of + the decision rule)

Floor + Kelly frozen at **12% / ⅛ Kelly** as of the 2026-08-06 freeze+same-day
reaffirmation; canonical record at `docs/research/floor_freeze_log.md`.
Re-freeze gate = **n_clv ≥ 150 at floor ≥ 12%** AND simultaneous BCa-CLV CI
excluding zero + win-rate > 0.524 break-even. See
`docs/reference/market_clv_gates.md` for the operating protocol.

## Dual RG / MLB starters

Live scoring dual-emits rows when RotoGrinders and MLB probable IDs disagree
(`starter_source`, `starter_disagreement`, `is_preferred`). Prefer the MLB
row near lock; compare both early. **Batting orders always come from
RotoGrinders** — dual scoring only swaps the SP.

Lineup MLB-ID resolve widens `active → 40Man → fullSeason` so IL / non-40
names on RG cards still match (e.g. Chadwick Tromp).

```powershell
python production/score_slate.py --live --allow-stale
# RG-only: add --no-dual-starters
```

## Projection log + grading

Formal expected_K logging begins **2026-07-28**. Count lines include
**2.5 … 9.5** (`PROJECTION_K_LINES`). Odds scoring falls back to binomial
`k_rate × TBF` if a logged board lacks a `p_over_*` column.

```powershell
python production/log_projections.py --allow-stale
python production/grade_projections.py --preferred-only
python production/grade_projections.py --all-logged --preferred-only `
  --exclude-abbreviated --exclude-out-of-support
```

**Pregame OOS** (sized to 0 / flagged OOS): `projected_tbf < 12`,
`expected_K < 1.5`, `days_rest ≥ 120`.  
**Postgame abbreviated:** `actual_PA < 9` (openers / early exits).

## Morning notebook map

`production/daily_projections.ipynb`:

1. Score today's slate  
2. Yesterday — projections vs actuals  
3. Today — preferred projections (`xK`, `p_over_*`)  
4. Today — edges (BET by default)  
5. Model edge vs CLV (**per-book** detail table)  
6. CLV skill tracker (**one prop** = best-edge book; no DK+FD double count)  
7. Season so far (compact)  
8. Optional residual charts  

## Post-freeze holdout (frozen stack, no refit)

```powershell
python production/refresh_features.py
python production/post_freeze_holdout.py
```

See `docs/reference/post_freeze_holdout.md`. Lineup train/serve skew:
`docs/reference/lineup_train_serve.md`.

## Playground demos

Counterfactuals and toys live under `playground/` (e.g. pitcher vs every
team, line shopper). The **production** SharpAPI board + ledger is the paper
stack; playground is not the skill sample. See `playground/README.md`.

## Incremental Statcast

`Python.statcast.update_statcast_season` is the production path:

- Missing file → full YTD download through yesterday (ET).
- Existing file → fetch `cached_max + 1` … `yesterday` only.
- Optional `--refresh-trailing-days 1` re-pulls the last cached day for late Savant fixes.
- Already current → no network fetch (`skipped_fetch: true`).

Full re-download remains available via `download_statcast_season` for repairs.
