# Index — MLB Props research map

Four phase diagrams. Open each file for detail; this index only shows how they
relate.

```mermaid
flowchart TB
  classDef built fill:#1b5e20,stroke:#a5d6a7,color:#fff
  classDef partial fill:#e65100,stroke:#ffcc80,color:#fff
  classDef missing fill:#b71c1c,stroke:#ef9a9a,color:#fff
  classDef risk fill:#4a148c,stroke:#ce93d8,color:#fff
  classDef next fill:#01579b,stroke:#81d4fa,color:#fff
  classDef index fill:#263238,stroke:#90a4ae,color:#fff

  IDX["MLB Props research map"]:::index

  A["01 Architecture<br/>L1→L3→k-rate × TBF→counts"]:::built
  B["02 Leakage & risks<br/>priors · parks · PA≥9 filter"]:::risk
  C["03 Modeling & evaluation<br/>chrono · Steps 1–10 · Phase 11 done"]:::built
  D["04 Roadmap<br/>paper CLV live · pristine needs roles"]:::next

  IDX --> A
  IDX --> B
  IDX --> C
  IDX --> D

  A -.->|"feeds"| C
  B -.->|"constraints"| A
  B -.->|"constraints"| D
  C -.->|"gates"| D
```

**Status snapshot (2026-07-31):**

- **Feature spine locked:** LightGBM `production` **184** (Step 11 discipline
  lift on Step 10 P1) ×
  Ridge thin-bullpen TBF × count layer v1 (`p_over` lines **2.5…9.5**).
- **Phase 11.A–C done** (verification: HPO flat, WF expected_K ≈ 1.78, ECE ≈
  0.024) — `docs/research/phase11_model_quality_gates.md`.
- **Post-hoc Platt `p_over_*` calibration** — production pointer
  (`docs/research/prob_calibration_findings.md`); raw probs retained.
- **Phase D interim policy frozen** (~3.5% excluded by `PA≥9`) —
  `docs/research/phase_d_population_findings.md`. Pregame role labels still open for
  pristine v1.
- **Live + paper trading shipped:** morning log/grade → SharpAPI `odds_board` →
  `poll_odds open` → tip-window `close_watcher` → settle/CLV skill tracker —
  `production/README.md`, `docs/reference/market_clv_gates.md`.
- **CLV skill suite shipped (2026-08-06):** `production/results_dashboard.ipynb`
  §11-18: reliability+z-test / band-discrete / rolling 30-bet /
  stake-weighted / per-band histograms / pseudo-ROC / outcome-pairing /
  BCa-CLV sweep / pre-registered next-50-bet checkpoint — see
  `docs/research/notebook_change_log.md`. Floor + Kelly frozen at
  **12% / ⅛ Kelly** (`docs/research/floor_freeze_log.md`).
- **Next:** grow post-freeze holdout; ops discipline (`--append` catch-ups,
  settle after finals); grow CLV sample to **n_clv ≥ 150 at floor ≥ 12%**
  (currently ~72 / BCa CI `[-0.30, +1.78]` still includes zero) for the
  pre-registered next-50-bet gate; optional always-on host.
- **Deferred (not critical path):** Marcel age curve, Steamer/ZiPS/PECOTA floors,
  NB/mixture count challengers — see `docs/diagrams/04-roadmap.md` § Later.
- **Lineup:** training uses first-9-by-PA proxy; live uses announced RG order;
  ID resolve `active → 40Man → fullSeason` — `docs/reference/lineup_train_serve.md`.
- Do not reuse scored 2025 for selection or “final” metrics.
