# 16 - Data lineage (PROPOSED, 2026-10-23)

> Tracks raw sources through the lake to production tables. The Odds-API
> historical archive lives outside git in `data/Odds-Historical/` (34,307
> files, 3.3 GB; sha256 manifest at `data/Odds-Historical.sha256`).

```mermaid
flowchart LR
    subgraph RAW["Raw sources"]
        SC["Statcast CSV<br/>(per-pitch, 2015-2026)"]
        RG["RotoGrinders<br/>(lineups, confirmed)"]
        SA["SharpAPI<br/>(DK/FD odds)"]
        OA["Odds-API<br/>(theoddsapi archive)"]
    end

    subgraph LAKE["Data lake (gitignored)"]
        RAWP["data/Odds-Historical/<br/>34,307 files, 3.3 GB<br/>sha256 manifest"]
        SAVANT["research/datasets/<br/>pa_table, eval_panel"]
    end

    subgraph TABLES["Pipeline tables (src/Python/pipeline/)"]
        L1["L1: games.py<br/>pitcher_games, batter_games"]
        L2["L2: rolling.py<br/>pitcher_rolling, batter_rolling"]
        L3["L3: training.py<br/>pitcher_training, batter_training"]
    end

    SC --> L1
    L1 --> L2 --> L3
    RG --> I2["daily_lineups.py"]
    I2 --> L3
    SA --> I3["sharp_odds.py"] --> LEDGER["odds_ledger"]
    OA --> RAWP
    L3 --> FEATURES["features.py -> registries.py<br/>184-feature vector"]
    FEATURES --> MODEL["k-rate ensemble + TBF ridge<br/>-> count_layer Poisson/WS1c"]
    MODEL --> BOARD["odds_board.py -> recommendations"]
```

## Key tables

| Table | Grain | Source | Consumed by |
|---|---|---|---|
| `pitcher_games` | (pitcher, game) | Statcast | `rolling.py` |
| `pitcher_rolling` | (pitcher, game) rolling window | `games.py` | `training.py`, `features.py` |
| `pitcher_training` | (pitcher, game) + labels | `rolling.py` | `train.py` |
| `batter_training` | (batter, game) + PA features | `rolling.py` | `train.py` |
| `pa_table` | (PA, slot) | pregame-pa-ext pipeline | PA model, count eval |
| `pa_predictions` | (PA, slot, model) | logistic_pa experiment | count eval |
| odds ledger | (ticket, game, book) | `poll_odds.py` | `grade_odds_ledger.py` |
