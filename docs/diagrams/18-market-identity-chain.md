# 18 - Market identity chain

> **Historical flow** (top diagram): the superseded broken implementation at
> `6bee3f7`. Pitcher identity is filtered early but lost at dedup, consensus,
> and the model join.
>
> **Repaired flow** (bottom diagram): identity carried through every
> transformation as `(game_pk, starter_pitcher_id)`. Independently verified
> at the reviewed research SHA.

## Historical flow (broken at `6bee3f7`)

```mermaid
flowchart TB
    subgraph RAW["Raw quotes (per book, per timestamp)"]
        Q1["Quote for pitcher A"]
        Q2["Quote for pitcher B"]
    end

    subgraph VERIFY["verified_odds_for_start()"]
        V["Filter: pitcher == pitcher_key<br/>(identity PRESERVED here)"]
    end

    subgraph DEDUP["select_near_close()"]
        D["Deduplicate by<br/>game_pk, book, line, side<br/>(pitcher identity LOST here)"]
    end

    subgraph CONSENSUS["consensus_over_probs()"]
        C["Pivot/group by<br/>game_pk, book, line<br/>(both starters collapsed into<br/>one game-level market)"]
    end

    subgraph JOIN["run_market_eval_k()"]
        J["Join consensus to model forecast<br/>ON game_pk alone<br/>(same consensus attached to both starters)"]
    end

    Q1 --> V
    Q2 --> V
    V --> D
    D --> C
    C --> J
```

## Repaired flow (verified at the reviewed research SHA)

```mermaid
flowchart TB
    subgraph RAW2["Raw quotes (per book, per timestamp, per starter)"]
        Q1["Quote for pitcher A<br/>key = (game_pk, pitcher_A_id)"]
        Q2["Quote for pitcher B<br/>key = (game_pk, pitcher_B_id)"]
    end

    subgraph VERIFY2["verified_odds_for_start()"]
        V["Filter: pitcher == pitcher_key<br/>start key = (game_pk, starter_pitcher_id)"]
    end

    subgraph DEDUP2["select_near_close()"]
        D["Deduplicate by<br/>game_pk, starter_pitcher_id, book, line, bet_side<br/>(identity PRESERVED)"]
    end

    subgraph CONSENSUS2["consensus_over_probs()"]
        C["Group by<br/>game_pk, starter_pitcher_id<br/>(per-start consensus, not game-level)"]
    end

    subgraph JOIN2["run_market_eval_k()"]
        J["Join consensus to model forecast<br/>ON (game_pk, starter_pitcher_id)<br/>(full start key)"]
    end

    Q1 --> V
    Q2 --> V
    V --> D
    D --> C
    C --> J
```

## Field definitions

| Field | Source | Meaning | Example |
|---|---|---|---|
| `pitcher_key` | Vendor (RotoGrinders / SharpAPI) | Vendor-specific pitcher identity used for matching quotes to a start | Vendor string or numeric key |
| `pitcher_id` (MLBAM) | Canonical MLBAM | Standardized MLB player identifier used for joins and model features | 605483 |
| `team_side` | Derived from game context | Which team the pitcher plays for in this game | home, away |
| `bet_side` | Derived from the betting market | Over/under direction of the betting market | over, under |

These must not share an ambiguous field name in the scored output. The
vendor `pitcher_key` is resolved to the canonical MLBAM `pitcher_id` by
`daily_lineups.py` and `identity.py` before entering the model pipeline.
