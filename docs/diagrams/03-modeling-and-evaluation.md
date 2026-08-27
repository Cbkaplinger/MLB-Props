# 03 — Modeling and evaluation status

Chronological evaluation of the strikeout-rate model, frozen feature gates,
and the shipped model-quality + calibration governance loop.

```mermaid
flowchart TB
  classDef built fill:#1b5e20,stroke:#a5d6a7,color:#fff
  classDef partial fill:#e65100,stroke:#ffcc80,color:#fff
  classDef missing fill:#b71c1c,stroke:#ef9a9a,color:#fff
  classDef risk fill:#4a148c,stroke:#ce93d8,color:#fff
  classDef next fill:#01579b,stroke:#81d4fa,color:#fff

  SEAS["TRAIN_SEASONS = (2023, 2024)<br/>filtered before any split / fit"]:::built
  SPLIT["Chrono date-disjoint ≈ 70/15/15<br/>train ≤ 2024-06-08<br/>val → 2024-08-05<br/>test ≥ 2024-08-06"]:::built
  NEST["Nested research folds<br/>outer 2024 h1/h2 · inner ⊂ train"]:::built

  LGBM["Single-model lane<br/>sparse72 / sparse72_monotone / final58"]:::built
  TBF["TBF Ridge thin bullpen<br/>test MAE≈2.49"]:::built
  CNT["Count layer lanes<br/>historical≈1.79 · single-model winner≈1.762"]:::built
  HOLD["2025 = historical only<br/>already consulted · not pristine"]:::risk

  S1["Steps 1–5: dict · LFO · windows · likelihoods"]:::built
  S7["Step 7: freeze 185"]:::built
  S89["Steps 8–9c: keep/drop · windows · P1"]:::built
  S10["Legacy freeze lineage lock<br/>superseded by sparse-set governance"]:::built
  S12["Step 12: feature-set + family ablation<br/>MAE/skill/risk gates complete"]:::built
  ENS["Deduped ensemble governance<br/>one-opportunity-one-bet fairness"]:::built
  TOP["Current production winner<br/>0.00 sparse72 / 0.60 mono / 0.40 final58<br/>isotonic · conservative floor 0.12"]:::built

  TUNE["11.A Tune LGBM + Ridge α<br/>done (flat/no lift)"]:::built
  WF["11.B Walk-forward stack backtest<br/>done"]:::built
  CAL["11.C Calibration / ECE<br/>done + monitored"]:::built
  ANOM["Exit-anomaly policy eval<br/>A/B + sensitivity wired"]:::built
  ANOMRES["Current result:<br/>neutral under low historical coverage"]:::risk
  PMON["Focused monitors + KPI policy<br/>execution lane + research lane"]:::built
  NEXT["Pristine test growth =<br/>future post-freeze games"]:::partial

  SEAS --> SPLIT
  SPLIT --> LGBM
  SPLIT --> TBF
  SPLIT --> HOLD
  NEST --> S1
  S1 --> S7 --> S89 --> S10 --> S12
  S12 --> LGBM
  LGBM --> ENS --> TOP
  LGBM --> TBF --> CNT
  S10 --> TUNE --> WF --> CAL
  CNT --> WF
  CAL --> PMON --> NEXT
  WF --> ANOM --> ANOMRES
```

## Notes

- Nested folds: `models/Strikeout-Model/research/nested_cv.py`.
- Production chrono split: `Python.training.chronological_split`.
- Keep **unweighted** LightGBM (`--sample-weight none`); PA-weight is diagnostic.
- Count metrics: prefer **Brier / log loss** over accuracy
  (`Python.count_layer.line_market_metrics`).
- Phase 11 plan: `docs/research/phase11_model_quality_gates.md`.
- Anomaly model-quality runners:
  `scripts/run_walkforward_anomaly_ab.py`,
  `scripts/run_walkforward_anomaly_sensitivity.py`.
- Focused ops loop: `production/notebooks/results_kpi_monitor.ipynb`,
  `results_calibration_lab.ipynb`, `results_gate_policy.ipynb`,
  `results_pnl_clv.ipynb`, plus `production/ops/policy_simulator.py`.
- Open polling is parity-locked to board artifacts by default:
  `production/odds/poll_odds.py --snapshot open --from-recommendations`.
- Deduped transfer artifacts:
  `artifacts/odds_log/open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.csv`,
  `open_top3_transfer_bestfloor_overlap_aug21_deduped_top3_from_dedupedsweep.csv`.
- Current freeze record: `docs/research/snapshots/2026-08-20/final58_consensus_freeze.md`.
- Prior freeze record: `docs/research/step10_p1_registry_freeze.md`.
- Archived leaky baselines: `docs/archive/leaky-baseline-2026-07-23/`.
