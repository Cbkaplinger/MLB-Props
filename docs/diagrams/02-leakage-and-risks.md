# 02 — Leakage and population risks

Horizontal constraints that apply to every pipeline level and future model.

```mermaid
flowchart TB
  classDef built fill:#1b5e20,stroke:#a5d6a7,color:#fff
  classDef partial fill:#e65100,stroke:#ffcc80,color:#fff
  classDef missing fill:#b71c1c,stroke:#ef9a9a,color:#fff
  classDef risk fill:#4a148c,stroke:#ce93d8,color:#fff
  classDef research fill:#0d47a1,stroke:#90caf9,color:#fff

  SC["statcast.py<br/>shared event / wOBA / discipline primitives"]:::built
  L1F["pitcher_features.py / batter_features.py<br/>Level 1: one row per start / game"]:::built

  FILT["MIN_STARTER_BATTERS_FACED = 9<br/>postgame filter → selection-bias risk"]:::risk
  TBF_RULE["Same-game PA / TBF<br/>never a prediction feature<br/>oracle diagnostic only"]:::built

  ROLL["pitcher_rolling.py / batter_rolling.py<br/>prior-game only · season-to-date resets yearly"]:::built
  PRIORS["Priors<br/>xFIP: 1,000 FB · batter K-shrink: 200 PA<br/>park regress: 500 PA"]:::built
  PARK_RISK["Neutral / international parks<br/>NOT filtered → contamination risk"]:::risk

  BP["ballpark.py<br/>season Y uses only seasons before Y<br/>unseen venue = 1.0"]:::built
  LINEUP["Historical lineup proxy<br/>first 9 distinct batters by first PA<br/>is_initial_lineup"]:::built
  GATE["features.py allowlist<br/>reject unexpected numeric columns<br/>184 production freeze · expanded research families"]:::built
  DET["Deterministic redundancy removed<br/>Contact≈1−Whiff · CSW≈SwStr+CS"]:::built
  VIF["Multicollinearity · VIF clusters<br/>165-feat & 74-feat Ridge proposals<br/>do NOT replace 248-feature gate"]:::research

  SC --> L1F
  L1F --> FILT
  L1F --> ROLL
  FILT --> TBF_RULE
  ROLL --> PRIORS
  ROLL --> BP
  PRIORS --> PARK_RISK
  BP --> LINEUP --> GATE --> DET --> VIF
```

## Hard rules

- Every feature must be known before first pitch.
- Forbidden as features: same-game `K`, `PA`, `Outs`, `k_rate`, actual TBF;
  future dates/seasons/lineups/park outcomes; IDs / names / team strings /
  raw dates / join keys.
- No SHAP on the current path (archived pre-pipeline SHAP used forbidden
  same-game fields). Prefer grouped permutation / drop-column importance.
- Live announced lineups (`daily_lineups.py`) replace the historical proxy at
  inference time only — never during Level 3 training construction.
- Gate changes are policy-controlled (`production/ops/kpi_policy.json`) and
  validated through scenario sweeps (`production/ops/policy_simulator.py`) plus
  focused monitor notebooks under `production/notebooks/`.
