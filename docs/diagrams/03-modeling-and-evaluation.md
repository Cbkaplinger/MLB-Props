# 03 — Modeling and evaluation (View B: built research and evaluation chain)

> Verified base: committed `31e9891`. Later bridge/WF work is reported-only
> (see `00-index.md`) and is not drawn here.

Chronological evaluation of the strikeout-rate model, frozen feature gates,
and the shipped model-quality + calibration governance loop.

> View B status: green below is EXISTING (frozen production lineage) or
> RESEARCH-BUILT (built + evaluated in `research/offseason_2026/`, never
> promoted). Dashed edges are proposals. REJECTED challengers are listed,
> never drawn as live. Research never feeds production automatically.

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
  TOP["Current production winner<br/>0.00 sparse72 / 0.60 mono / 0.40 final58<br/>Poisson + WS1c · champion policy live"]:::built

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

- View B research chain (RESEARCH-BUILT unless marked; all docs-only here).
  - PA dataset: `research/offseason_2026/specs/pa_dataset_contract.md` +
    manifest (PA grain, binary K target conditional on PA occurring; input
    pitch rows -> output PA rows with attribution; K to completing pitcher,
    split-PA flagged).
  - PA-1A batter tendency: `experiments/pa1a_raw_pa/run_pa1a.py` (RESEARCH-BUILT;
    shrunk batter rates; survives both 2024 blocks).
  - P3-log5 pitcher prior: `experiments/pitcher_prior/` (RESEARCH-BUILT,
    promoted reference/rollback; m=100 selected on 2023 folds; log5 with PA-1A).
  - L3 ridge logistic: `experiments/logistic_pa/` + `bundle/` manifest +
    sidecar (RESEARCH-BUILT, DEVELOPMENT baseline, NOT production; trip
    dummies + starter_pa_index/9; F6 rest excluded; reproducible to 2.2e-16).
  - Tree challenger: `experiments/tree_pa/run_tree.py` (REJECTED: TIE, blend
    gate failed corr 0.9965, lane CLOSED; L3 retained).
  - Oracle aggregation: `experiments/pa1b_oracle_xk/run_pa1b_o.py`
    (RESEARCH-BUILT diagnostic; oracle lineup lane only).
  - Workload spine: `research/offseason_2026/workload_spine.py`
    (RESEARCH-BUILT point-BF reference).
  - BF PMF: `research/offseason_2026/bf_distribution.py` +
    `run_bf_distribution_2023.py` (RESEARCH-BUILT; point xTBF insufficient).
  - Log5 rate + K combiner: `research/offseason_2026/kcount_combiner.py` +
    `run_kcount_integration_2023.py` (RESEARCH-BUILT; conditional-K to
    marginal-K PMF; binomial mixture retained reference).
  - Evaluation package: `research/offseason_2026/eval_package.py`
    (RESEARCH-BUILT; PA prob, xK, distributions, market-line probs, betting
    slices; date-clustered bootstrap).
  - History/transfer lanes: `run_corrected_history_2023.py`,
    `run_i3_transfer_2024.py`, `run_i3_opportunity_2023.py`,
    `run_i4_card_source_2023.py`, `run_i5_tail_2023.py`,
    `run_sep_challenger.py` + frozen `sep-challenger-contract.md`
    (REJECTED September hazard challenger: BF repair real both seasons, K
    degraded in 2024 confirm; lane CLOSED).
  - Inventory rule: do not assume the proposed PA LightGBM is the first PA
    model. Prototypes above predate it; the L3 bundle is the baseline to beat.
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
  `results_calibration_lab.ipynb`, `results_bettable_cohort.ipynb` (hosts retired gate-policy audit),
  `results_pnl_clv.ipynb`, plus `production/ops/policy_simulator.py`.
- Open polling is parity-locked to board artifacts by default:
  `production/odds/poll_odds.py --snapshot open --from-recommendations`.
- Deduped transfer artifacts:
  `artifacts/odds_log/open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.csv`,
  `open_top3_transfer_bestfloor_overlap_aug21_deduped_top3_from_dedupedsweep.csv`.
- Current freeze record: `docs/research/snapshots/2026-08-20/final58_consensus_freeze.md`.
- Prior freeze record: `docs/research/step10_p1_registry_freeze.md`.
- Archived leaky baselines: `docs/archive/leaky-baseline-2026-07-23/`.
