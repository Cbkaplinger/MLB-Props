# 04 — Roadmap (View C: proposed offseason architecture + decision log)

Research spine is feature-frozen with current sparse-set governance lanes.
Phase 11.A–C remains historical verification context. Live assembly + paper
trading / CLV are shipped; dashed edges = still open.

> **Live prioritization:** [`docs/EXECUTION_BACKLOG.md`](../EXECUTION_BACKLOG.md)
> (FORWARD / DEFERRED). This roadmap diagram is research status, not the ops queue.
>
> Metric lane note: deployment champions are selected on decision metrics, while
> single-model MAE winners are tracked separately in
> `docs/reference/governance_metric_stack.md`.

```mermaid
flowchart TB
  classDef built fill:#1b5e20,stroke:#a5d6a7,color:#fff
  classDef partial fill:#e65100,stroke:#ffcc80,color:#fff
  classDef missing fill:#b71c1c,stroke:#ef9a9a,color:#fff
  classDef risk fill:#4a148c,stroke:#ce93d8,color:#fff
  classDef next fill:#01579b,stroke:#81d4fa,color:#fff

  FEAT["Feature research lineage<br/>current sparse-set governance active"]:::built
  TBF["TBF Ridge thin bullpen<br/>FROZEN + joblib"]:::built
  CNT["Count layer v1<br/>chrono scored · lines 2.5…9.5"]:::built

  TUNE["11.A Estimator tuning<br/>HPO flat vs defaults"]:::built
  WF["Historical baseline lane<br/>legacy expected_K benchmarks"]:::built
  CAL["Calibration lane<br/>WS1c live (isotonic lineage)"]:::built
  PCAL["Post-hoc Platt p_over<br/>WS1c live 2026-09-10"]:::built
  PHD["11.D Phase D interim policy<br/>~3.5% excluded; role labels open"]:::partial
  ANOM["Exit-anomaly governance<br/>shipped in ops + reports"]:::built
  ANOMEFF["WF impact under current tags<br/>neutral (low historical density)"]:::risk

  LIVE["Live inference assembly<br/>production daily ops"]:::built
  MKT["Paper trading / CLV<br/>SharpAPI DK+FD · ledger"]:::partial
  SKILL["CLV skill suite<br/>§11-20 incl. scorecard"]:::built
  KPI["Daily KPI protocol + policy JSON<br/>dynamic gate states"]:::built
  SPLIT["Focused monitor split<br/>KPI · calibration · gate · PnL"]:::built
  PSIM["Policy simulator<br/>edge-floor sweeps by side"]:::built
  GATE["Quality gate (BET->HOLD)<br/>matchup/rest/dynamic edge"]:::built
  HOLD["Pristine post-freeze holdout<br/>needs pregame role labels"]:::missing
  PARK["Park contamination cleanup"]:::risk

  FEAT --> TUNE
  TBF --> TUNE
  CNT --> WF
  TUNE --> WF --> CAL
  CAL --> PCAL
  PHD --> HOLD
  CAL --> LIVE
  PCAL --> LIVE
  CAL --> ANOM --> ANOMEFF
  LIVE --> MKT
  LIVE --> GATE
  SKILL --> KPI
  SKILL --> SPLIT
  KPI --> GATE
  PSIM --> GATE
  SPLIT --> PSIM
  LIVE --> HOLD
  MKT --> SKILL
  SKILL -.->|"n_clv ≥ 150 + BCa CI"| HOLD
  FEAT --> PARK
```

## Status (2026-09-11, replay era — August rows below retained for lineage)

| Track | State |
|---|---|
| Frozen stack | **Poisson + WS1c live** (shipped 2026-09-10; ship-lift +0.0016) |
| Live policy | **Champion** (cap 0.24 / lean +0.04 / DK+FD-only / clip ±0.02; rebuilt-panel truth 2025 n=505 +11.0% → 2026 n=460 +8.8% disclosed peek, White p=0.0075; 9/11 pre-WS1c +15.5%→+15.6% superseded; pin green) |
| Sizing | **1/16-Kelly live**, flat 1u research benchmark (flat wins paper ROI everywhere; "⅛ Kelly" in August rows below is stale) |
| Replay lake | **On disk** (vendor envelopes, juiced ledger, slate totals joined) |
| Retrain | **Closed** (walk-forward dead #66) |

| Track | State |
|---|---|
| Feature research (Steps 1–11) | **Done** — legacy freeze lineage retained; sparse-set governance active |
| TBF + count layer v1 | **Done** — `p_over` lines **2.5…9.5** |
| Phase 11.A–C model quality | **Done** — confirmatory |
| Post-hoc `p_over_*` calibration | **Done** — Platt production pointer; raw retained (`docs/research/prob_calibration_findings.md`) |
| Phase D opener/piggyback | **Interim policy** — role labels still open |
| Live assembly | **Shipped** — `production/` refresh → log → grade (`docs/reference/live_assembly_plan.md`) |
| Paper trading / CLV | **Shipped ops; sample building** — edge floor **12%** + 1/16-Kelly live, flat $50u realized (`docs/reference/market_clv_gates.md`) |
| CLV skill suite (dashboard) | **Shipped 2026-08-06** — `production/notebooks/results_dashboard.ipynb` §11-20: reliability, residual decomposition, chrono recalibration test, and daily scorecard (`docs/research/notebook_change_log.md`) |
| Focused monitor split | **Shipped 2026-08-11** — `results_kpi_monitor`, `results_calibration_lab`, `results_pnl_clv`; `results_gate_policy` **retired 2026-09-17** into `results_bettable_cohort` |
| Policy simulator CLI | **Shipped 2026-08-11** — `production/ops/policy_simulator.py` writing scenario artifacts |
| Daily KPI + dynamic gate policy | **Shipped** — `production/ops/kpi_policy.json`, `production/ops/kpi_daily_action.py`, `docs/reference/daily_kpi_protocol.md` |
| Quality gate in live odds flow | **Shipped** — `production/odds/odds_board.py` and `production/odds/poll_odds.py` (`--quality-gate`) |
| Floor + Kelly freeze | **Logged** — `docs/research/floor_freeze_log.md`; skill remains under ongoing governance monitoring |
| Pristine future holdout | **Protocol live** — `production/projections/post_freeze_holdout.py` (`docs/reference/post_freeze_holdout.md`); grows with `game_date >= 2026-07-28` |
| Lineup train/serve | **Documented** — first-9-by-PA vs announced; roster cascade `active → 40Man → fullSeason` |
| Chrono recalibration promotion gate | **In progress** — compare raw vs isotonic vs Platt after `>=15` distinct dates |
| Exit-anomaly governance | **Shipped** — override/mask/report loop + rolling-policy PASS/WARN + WF A/B/sensitivity runners |
| Historical anomaly effect size | **Neutral so far** — low tagged density in 2023-2024 backfill |

## Why Phase 11 felt quiet

Gates exist to catch failure modes. Here the frozen defaults already sat near a
local optimum: nested HPO did not beat them; the stack held under walk-forward;
calibration did not need a patch. That is the intended outcome of a healthy
freeze — boring confirmation, not a new research story.

Canonical: `docs/research/phase11_model_quality_gates.md`,
`docs/research/phase_d_population_findings.md`, `docs/reference/live_assembly_plan.md`,
`docs/reference/market_clv_gates.md`,
`docs/research/floor_freeze_log.md` (floor + Kelly freeze),
`docs/research/notebook_change_log.md` (dashboard additions).

## Workload companions

| Phase | Status |
|---|---|
| A–C rest / volume / thin bullpen | **Done** (in TBF) |
| D opener/piggyback | **Interim policy** — `docs/research/phase_d_population_findings.md` |

## Later (not critical path)

### Ops / live

1. Grow post-freeze holdout; settle discipline after finals; optional always-on host for `close_watcher`.
2. Continue CLV sample growth and confidence tightening at floor ≥ 12%. The
   pre-registered next-50-bet decision rule is frozen at
   `artifacts/odds_log/next_50_checkpoint.json`
   (`production/notebooks/results_dashboard.ipynb` §18b); on hit, escalate KB stake
   size; on miss, revert to ¼ Kelly at the 12% floor; on hold, re-evaluate at
   `n_clv = 200`. Floor/Kelly changes are recorded in
   `docs/research/floor_freeze_log.md`.
3. Pregame role ingestion (opener / piggyback) for pristine v1.
4. Doubleheader-safe schedule join hardening in `daily_lineups`.
5. Park-factor hygiene (neutral-site / international venue keys).

### Model / count-layer challengers

6. Negative-binomial / mixture-over-TBF challengers (count layer, not rate features)
   — still open if live ECE regresses after Platt.
7. Longer outer folds / stronger external floors if the goal shifts beyond leakage-safe stack.

Post-hoc **Platt** on `p_over_*` is shipped (not a count-family change):
`docs/research/prob_calibration_findings.md`.

### Deferred external baselines & enrichment (post–Marcel-lite)

Landed already: Marcel-lite k<sub>rate</sub> floor
(`models/Strikeout-Model/research/marcel_baseline.py`, manuscript Table 3b);
paper-trading product layer (SharpAPI opens/closes — not a historical closing-line archive).

These are **optional** follow-ons if the goal shifts from “leakage-safe stack”
to “best available predictor / richer market check”:

| Idea | Why later | Notes / blockers |
|---|---|---|
| **Age curve on Marcel** | Small expected lift; cleans the talent baseline | Needs birthdates (not in `player_id_map`); pybaseball / Chadwick register |
| **Steamer / ZiPS / PECOTA as game k_rate floors** | Richer season systems than Marcel | Licensing / scrape ethics; usually season rates → map to game rows; still not matchup models |
| **Multi-year closing-line archive** | Stronger backtests than forward paper sample | Needs historical K-prop closes + de-vig; separate from modeling paper |
| **Weather / travel / catcher / umpire** | Possible rate or TBF signal | New leakage-safe joins; promote only via nested chrono screens |

Do **not** reopen frozen production feature sets for these without a new
nested outer protocol and a pristine post-freeze holdout.

> Verified 2026-09-30: calibration lane now reads WS1c-live (was isotonic-era text); Kelly rows aligned to 1/16-Kelly live. Deployed settings not inferred from source.

## View C — Proposed offseason architecture (PROPOSED; dashed = not built)

> Verified base: committed `31e9891`. No PROPOSED box below was verified as
> implemented at this base. Newer bridge/WF reports are described in
> `00-index.md` only, not drawn here.

Do not implement a box to make the picture true. No box below feeds
production without a gated promotion + revert path. Research never edits live
scorers, policy JSONs, schedules, or ledgers. Calibration and policy reuse
are separately fitted/evaluated candidates — neither is automatic.

```mermaid
flowchart TB
  classDef proposed fill:#e8eaf6,stroke:#5c6bc0,color:#000,stroke-dasharray:5 5
  classDef built fill:#1b5e20,stroke:#a5d6a7,color:#fff
  classDef rejected fill:#fce4ec,stroke:#c62828,color:#000

  HIST["Historical feature snapshots<br/>PROPOSED · rolling-window clocks<br/>input: prior games · output: pregame feature row"]:::proposed
  PACLASS["PA classifier (binary LightGBM)<br/>PROPOSED · after L3<br/>input: PA matchup row · output: per-PA K prob"]:::proposed
  BFPMF["BF PMF (workload uncertainty)<br/>PROPOSED for live use · RESEARCH-BUILT offline<br/>input: workload features · output: P(BF=N)"]:::proposed
  AGG["Poisson-binomial aggregation<br/>PROPOSED · per-PA probs over BF PMF<br/>input: per-PA probs + BF PMF · output: marginal K PMF"]:::proposed
  RECAL["Recalibration candidate<br/>PROPOSED · separately fitted/evaluated<br/>input: raw K PMF · output: calibrated P(K>=line)"]:::proposed
  POLMKT["Policy reuse candidate<br/>PROPOSED · not decided<br/>input: candidate probs · output: BET/HOLD + ledger"]:::proposed
  REJ1["Tail redistribution<br/>REJECTED · degraded upper-K reliability"]:::rejected
  REJ2["September hazard fix<br/>REJECTED · BF repair real, K degraded"]:::rejected
  REJ3["Tree blend over L3<br/>REJECTED · corr 0.9965 gate fail"]:::rejected

  HIST -.-> PACLASS
  HIST -.-> BFPMF
  PACLASS -.-> AGG
  BFPMF -.-> AGG
  AGG -.-> RECAL
  RECAL -.-> POLMKT
```

Notes:

- Status 2026-10-29: the Poisson-binomial AGG node below was evaluated once
  as Question A (dev-only diagnostic, count-RPS delta -0.0003333, baseline
  retained; receipt `research/offseason_2026/pregame_pa_ext/results_count_agg_eval_v1/RESULT_RECORD.md`).
  The registered baseline aggregation is binomial conditionals at averaged
  cycled-slot probabilities, NOT a heterogeneous Poisson-binomial -- see
  `research/offseason_2026/pregame_pa_ext/briefing_pa_model_and_architecture_2026-10-29.md`.
- Training vs pregame inference stay separate; every PROPOSED node needs an
  explicit training contract (target, population, cutoff) before comparison.
- PA classifier + Poisson-binomial limits: assumes PA flips independent given
  features; breaks under fatigue/game-state coupling and workload dependence.
  The authorized chronological WF comparison in the research window holds the
  comparison design; this diagram prescribes no first-comparison setup.
- Recalibration is a candidate fitted and evaluated separately after
  aggregation — not a required stage. Policy reuse is a proposal, not an
  established architecture decision.
- Math definitions live once in `00-index.md` (plain-language section);
  boxes carry no headline numbers.
- Rejected boxes above are closed branches. Reopen only on new evidence +
  owner order.
