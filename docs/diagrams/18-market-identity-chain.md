# 18 - Market identity chain (UNDER AUDIT, 2026-10-23)

> Shows the identity flow from raw odds quotes through model forecast join.
> The current implementation has a demonstrated player-mixing defect at
> `c07976d`: pitcher identity is filtered early but omitted from dedup keys,
> consensus construction, and the final model join. UNDER AUDIT until the
> full start key `(game_pk, starter_pitcher_id)` is carried through every
> transformation.

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
        D["Deduplicate by<br/>game_pk, book, line, side<br/>(identity LOST here — AUDIT)"]
    end

    subgraph CONSENSUS["consensus_over_probs()"]
        C["Pivot/group by<br/>game_pk, book, line<br/>(both starters collapsed<br/>into one game-level market — AUDIT)"]
    end

    subgraph JOIN["run_market_eval_k()"]
        J["Join consensus to model forecast<br/>ON game_pk alone<br/>(same consensus attached to<br/>both starters — AUDIT)"]
    end

    subgraph TARGET["Required behavior"]
        T1["Per-start consensus<br/>key = (game_pk, starter_pitcher_id)"]
        T2["Per-start forecast join<br/>key = (game_pk, starter_pitcher_id)"]
    end

    Q1 --> V
    Q2 --> V
    V --> D
    D --> C
    C --> J
    J -.-> "IDENTITY BREAK" .-> T1
    T1 --> T2
```

## Distinguishing side fields

| Field | Meaning | Example |
|---|---|---|
| `team_side` | home/away (which team the pitcher plays for) | home, away |
| `bet_side` | over/under (the betting market direction) | over, under |
| `pitcher_key` | canonical pitcher identity (MLBAM ID) | 605483 |

These must not share an ambiguous field name in the scored output.
