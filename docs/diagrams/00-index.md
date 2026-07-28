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
  D["04 Roadmap<br/>live next · pristine needs roles"]:::next

  IDX --> A
  IDX --> B
  IDX --> C
  IDX --> D

  A -.->|"feeds"| C
  B -.->|"constraints"| A
  B -.->|"constraints"| D
  C -.->|"gates"| D
```

**Status snapshot (2026-07-28):**

- **Feature spine locked:** LightGBM `production` **180** (Step 10 P1 swap) ×
  Ridge thin-bullpen TBF × count layer v1.
- **Phase 11.A–C done** (verification: HPO flat, WF expected_K ≈ 1.78, ECE ≈
  0.024) — `docs/research/phase11_model_quality_gates.md`.
- **Phase D interim policy frozen** (~3.5% excluded by `PA≥9`) —
  `docs/research/phase_d_population_findings.md`. Pregame role labels still open for
  pristine v1.
- **Next:** daily `log_projections` → next-day `grade_projections --all-logged`;
  grow `post_freeze` holdout (`docs/reference/post_freeze_holdout.md`); optional pregame
  role labels for broader population claims.
- **Deferred (not critical path):** Marcel age curve, Steamer/ZiPS/PECOTA floors,
  closing-line / Kelly — see `docs/diagrams/04-roadmap.md` § Later.
- **Lineup:** training uses first-9-by-PA proxy; live uses announced RG order —
  `docs/reference/lineup_train_serve.md`.
- Do not reuse scored 2025 for selection or “final” metrics.
