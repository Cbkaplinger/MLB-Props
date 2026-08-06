# Playground — fun demos on the frozen strikeout stack

Not for cron. Daily scoring stays in `production/`. These scripts show off
counterfactuals and dual-starter views using the **already-trained** artifacts
in `artifacts/models/` (no retrain needed).

## Model weights (frozen)

| Artifact | Path |
|---|---|
| K-rate LightGBM | `artifacts/models/lightgbm_krate_20260803_155401.{txt,json}` |
| TBF Ridge | `artifacts/models/tbf_pa_ridge_workload_context_bullpen_20260728_035607.joblib` |

Daily / playground scoring **loads** those files. Retrain only when you
intentionally change the freeze (`Models/Strikeout-Model/train.py`,
`Models/TBF-Model/train.py`).

## Demos

### Pitcher vs every team (what-if)

```powershell
# Chris Sale (519242) vs all other clubs — prints only (no parquet)
python playground/whatif_pitcher.py --pitcher-id 519242
python playground/whatif_pitcher.py --name "Chris Sale" --away
# Optional persist: add --write
```

Uses today's RG lineup when that club is on the slate; otherwise each team's
most recent batting order 1–9 from `batter_rolling`.

### Dual RG vs MLB starters (production live)

```powershell
python production/score_slate.py --live --allow-stale
```

On disagreement you get two rows per team (`starter_source` =
`rotogrinders` / `mlb_probable`), with `is_preferred=True` on the MLB
probable. Filter:

```powershell
python -c "import polars as pl; df=pl.read_parquet('artifacts/live_scores/live_scores_2026-07-28.parquet'); print(df.filter(pl.col('starter_disagreement')).select('team','player_name','starter_source','expected_K','is_preferred').sort('team','starter_source'))"
```

### Line shopper (manual odds dry-run)

Paste book K lines against the projection log — **no API**. Useful for a quick
what-if. Locked gates: `docs/reference/market_clv_gates.md` (8% edge floor,
¼ Kelly).

**Canonical paper-trading path** (SharpAPI + durable ledger + tip closes) is
`production/` — `odds_board` → `poll_odds` → `close_watcher` →
`grade_odds_ledger`. See `production/README.md`. This playground script does
not replace that stack.

```powershell
python playground/line_shopper.py
python playground/line_shopper.py --list
python playground/line_shopper.py --quote "Shane Bieber,4.5,+115,-145"
python playground/line_shopper.py --quote "Bieber,4.5,115,-145" --write
```

Optional write → `artifacts/odds_log/paper_dry_run.parquet`.

## Other cool ideas (not built yet)

| Demo | Why it’s fun |
|---|---|
| **Rest sensitivity** | Same pitcher, sweep `days_rest` 3→8 and watch expected_K / TBF move |
| **Opener detector** | Flag announced starters whose form / TBF looks like a bulk-guy profile |
| **Park tour** | One pitcher, hold lineup fixed, swap `park_k_factor` across stadiums |
| **Handedness stack** | Rank today’s LHB-heavy vs RHB-heavy lineups for a given arm |
| **Season heat map** | Walk-forward expected_K error by month / team (calibration vibe check) |
| **Name resolver lab** | Paste ugly DFS names → see roster variant / fuzzy match path |

PRs welcome as more scripts under this folder.
