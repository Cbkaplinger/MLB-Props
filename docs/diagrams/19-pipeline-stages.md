# 19 - Pipeline stages (PROPOSED, 2026-10-23)

> Six distinct stages with explicit boundaries. The market identity bridge
> (stage 5) is independently verified at the reviewed research SHA.

```mermaid
flowchart LR
    subgraph S1["1. DATA INGESTION"]
        direction LR
        SC["Statcast parquet<br/>(per-pitch, per-game)"]
        RG["RotoGrinders<br/>(lineups)"]
        ODDS["SharpAPI / Odds-API<br/>(quotes, lines)"]
    end

    subgraph S2["2. FEATURE / PA MODEL"]
        direction LR
        L123["L1-L3 pipeline<br/>games, rolling, training"]
        FEAT["features.py<br/>184-feature vector"]
        PA["per-PA probabilities<br/>(4-class M0 v2)"]
    end

    subgraph S3["3. WORKLOAD"]
        direction LR
        TBF["TBF ridge<br/>projected batters faced"]
        WC["workload context<br/>(bullpen, rolling)"]
    end

    subgraph S4["4. COUNT AGGREGATION"]
        direction LR
        CL["count_layer.py<br/>Poisson + WS1c Platt<br/>P(K >= line)"]
        PMF["count PMF<br/>(24-bucket distribution)"]
    end

    subgraph S5["5. MARKET EVALUATION<br/>(HISTORICAL — identity repaired, independently verified)"]
        direction LR
        MATCH["event mapping<br/>(game_pk + starter_pitcher_id)<br/>HISTORICAL — identity repaired, independently verified"]
        SNAP["early snapshot<br/>vs actual opening quote"]
        CLOSE["prior-evening<br/>vs near-close"]
        CONSENSUS["per-start consensus<br/>(NOT game-level)"]
    end

    subgraph S6["6. BETTING EXECUTION<br/>(future)"]
        direction LR
        FLIP["decision-flip analysis<br/>(parked, rerun 2026-11-07)"]
        POLICY["policy filter + sizing<br/>(frozen, production)"]
    end

    S1 --> S2
    S2 --> S3
    S3 --> S4
    S4 --> S5
    S5 --> S6
```

## Market timing documentation

| Timing concept | Definition | Current implementation |
|---|---|---|
| **Early snapshot** | Quote captured before the market settles (typically pre-dawn) | Logged at poll time; no separate snapshot label |
| **Actual opening quote** | The first quote the book posts for a market | Not currently distinguished from later quotes |
| **Prior-evening** | Quote from the evening before the game (typically 20:00+ ET the prior day) | Captured by overnight polling |
| **Near-close** | Quote close to first pitch (within the T-45 urgency gate) | Captured by urgency-gated sweeps |

The distinction between early snapshot and actual opening quote is not
currently implemented. The poll captures whatever the book shows at each
timestamp; there is no separate "opening" label.
