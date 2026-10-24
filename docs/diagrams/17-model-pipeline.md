# 17 - Model pipeline (PROPOSED, 2026-10-23)

> Shows the frozen model pipeline from point-in-time features through count
> PMF and market comparison. Each node cites the implementing module.

```mermaid
flowchart TB
    subgraph FEATURES["Point-in-time features (frozen)"]
        F1["features.py<br/>production 184-feature vector<br/>+ registries.py (Step 11 freeze)"]
        F2["pregame_pa_ext/<br/>PA features (per-slot)"]
    end

    subgraph KRATE["K-rate ensemble (frozen)"]
        K1["Mean baseline"]
        K2["Ridge (production 184)"]
        K3["LightGBM (sparse 72)"]
    end

    subgraph TBF["TBF ridge"]
        T1["workload_context_bullpen<br/>+ rolling workload"]
    end

    subgraph COUNT["Count layer (live)"]
        C1["count_layer.py<br/>Poisson expected_K<br/>+ P(K >= line)"]
        C2["WS1c Platt calibration<br/>(per-line sigmoid/Platt,<br/>not isotonic regression)"]
    end

    subgraph POLICY["Policy filter (live)"]
        P1["kpi_policy.json<br/>edge_floor 0.12<br/>edge_cap 0.24<br/>under_lean premium<br/>DK+FD only<br/>game_cap (supported up to 3;<br/>configured value: check kpi_policy.json)"]
        P2["market.py<br/>1/16-Kelly sizing<br/-> flat $50"]
    end

    subgraph OUTPUT["Outputs"]
        O1["odds_board.py<br/>recommendation board<br/>+ slate exposure"]
        O2["odds_ledger<br/>open + graded tickets"]
    end

    F1 --> K1
    F1 --> K2
    F1 --> K3
    F2 --> PA["per-PA probabilities<br/>(4-class or binary)"]
    T1 --> C1
    K2 --> C1
    K3 --> C1
    C1 --> P1 --> P2 --> O1
    O1 --> O2
```

## Feature pipeline detail

| Stage | Module | Input | Output |
|---|---|---|---|
| L1 | `pipeline/games.py` | Statcast parquet | `pitcher_games`, `batter_games` |
| L2 | `pipeline/rolling.py` | L1 tables | `pitcher_rolling`, `batter_rolling` (rolling windows, rest, bullpen) |
| L3 | `pipeline/training.py` | L2 tables | `pitcher_training`, `batter_training` (lineup + park factors) |
| Feature | `features.py` | L3 + registries | 184-feature production vector |
| Registry | `registries.py` | feature definitions | Step-11 frozen set |

## Model components (frozen)

| Component | Implementation | Trained on | Status |
|---|---|---|---|
| K-rate ensemble | `train.py` (Mean, Ridge, LightGBM) | 2023-2024 chronological split | FROZEN |
| TBF ridge | `models/TBF-Model/` | workload context + bullpen | FROZEN |
| Count layer | `count_layer.py` (Poisson) | per-game K distribution | LIVE |
| WS1c calibrator | Platt scaling per line | historical calibration set | LIVE |
| Policy filter | `kpi_policy.json` | 2025-lock champion selection | LIVE |
