# 04 — Roadmap (remaining work)

Future layers after the frozen k-rate artifact. Dashed edges = not implemented.

```mermaid
flowchart TB
  classDef built fill:#1b5e20,stroke:#a5d6a7,color:#fff
  classDef partial fill:#e65100,stroke:#ffcc80,color:#fff
  classDef missing fill:#b71c1c,stroke:#ef9a9a,color:#fff
  classDef risk fill:#4a148c,stroke:#ce93d8,color:#fff
  classDef research fill:#0d47a1,stroke:#90caf9,color:#fff

  ART["Frozen k-rate artifact<br/>lightgbm_krate_*.{txt,json}"]:::built

  OPEN["Resolve opener / piggyback<br/>selection bias via pregame role info"]:::risk
  S5["Step 5: compare likelihoods<br/>unweighted / PA-weighted / binomial / beta-binomial"]:::missing

  DL["Harden live lineup path<br/>announced lineup via MLB numeric IDs"]:::partial
  LIVE["Build live prediction assembly<br/>+ monitoring · NOT IMPLEMENTED"]:::missing

  TBF["Leakage-safe projected TBF model<br/>lag PA / Outs / Pitches from Level 1<br/>NOT YET BUILT"]:::missing
  BB["Count layer: beta-binomial<br/>K successes / PA trials · recommended"]:::missing
  NB["NB with log-TBF offset<br/>challenger"]:::missing
  POIS["Poisson GLM floor<br/>transparent baseline"]:::missing
  EXP["expected_K = k_rate × projected_TBF<br/>then P(K ≥ n) from count layer"]:::missing

  PARK["Remove neutral / international<br/>park contamination"]:::risk

  S7["Step 7: registry freeze<br/>after Steps 1 / 3 / 4 / 5"]:::missing
  SNAP["Reproducible baseline snapshot<br/>only after stability"]:::missing

  ART --> OPEN --> S5
  ART --> DL --> LIVE
  ART --> TBF
  TBF --> EXP
  BB --> EXP
  NB --> EXP
  POIS --> EXP
  ART --> PARK

  S5 --> S7
  LIVE --> S7
  EXP --> S7
  PARK --> S7
  OPEN --> S7
  S7 --> SNAP
```

## TBF spine (minimal, no Level 1 rebuild)

1. Read `pitcher_games.parquet` (already has `Pitches`, `PA`, `Outs`).
2. Add lagged workload features (`PA_P*`, `Outs_P*`, `Pitches_P*`) via rolling
   means — Level 2 does **not** emit these today.
3. Join onto existing `pitcher_training.parquet` on `(game_pk, pitcher)`.
4. Target = same-game `PA`; never use same-game `PA`/`Outs`/`Pitches` as features.
5. End-to-end props must score with **projected** TBF only.

## Live assembly (minimal)

1. Load frozen LightGBM `.txt` + feature list from `.json`.
2. Pull today's slate via `daily_lineups.build_daily_slate`.
3. As-of join pitcher form + announced opponent lineup + park factor.
4. Predict `k_rate`; write dated prediction parquet.
5. Block `expected_K` until the TBF model exists.
