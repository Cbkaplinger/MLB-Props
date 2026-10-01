# Offseason 2026 choice log (immutable append-only)

Rules: append entries with UTC date; never rewrite or delete a prior entry.
A superseded entry stays with its status changed by a NEW entry, never by edit.
Backtest terms: 2023–24 train/dev, 2025 validation+policy, 2026 locked
retrospective (never pristine), 2027 prospective.

## 2026-09-28 — Five owner approvals (from Phase 1 checkpoint)

| # | Decision | Status | Evidence |
|---|---|---|---|
| A1 | Batter-K stays post-processing; lower layers frozen; no pair memorization | APPROVED | Audit §§M, W |
| A2 | Backtest terms locked (23–24 / 25 / 26-retro / 27-prosp) | APPROVED | Audit §§I, X, AD |
| A3 | No new top-level folder; bounded `research/offseason_2026/` with import/write rules | APPROVED | Audit §AF; scaffold Phase 4 |
| A4 | Promotion requires staging + regression guard + registry + human approval + named rollback | APPROVED | Audit §AF Gates 1–6 |
| A5 | Uncertain-lineup doctrine (projected vs replacement prior vs delay) | PENDING (Q-04 → Q-D3 resolved as modes 1–4, §AC; owner confirms mode priority) | Audit §§AC, AG |

## 2026-09-28 — Q-01…Q-08 statuses (audit §S)

Q-01 config-is-truth (confirm + fix README lag): OPEN. Q-02 live-open definition:
OPEN. Q-03 2026-consultation freeze: APPROVED (no new 2026 tuning). Q-04 lineup
doctrine: PENDING (see A5). Q-05 spring re-activation = one deploy: OPEN
(confirm). Q-06 retention set: OPEN. Q-07 Novig key + RG backstop: OPEN.
Q-08 first-3 build lock: OPEN.

## 2026-09-28 — Binding constraint #1 (2025 refit is in-sample)

The final 2025 policy refit touches all 2025 data, so its 2025 backtest is
in-sample and may never be cited as validation. Only the locked 2026 run judges
the refit policy. Applies to floors, caps, vetoes, probation, calibration maps,
book universe, and sizing. (Source: Phase 3 §AD + owner direction.)

## 2026-09-28 — Binding constraint #2 (2025B n-floors)

2025B requires pre-registered n-floors (G4 minima: n≥200 cells, ≥30 per segment,
100+5 BET claims). Below floor, report direction only — never certify. (Source:
Phase 3 §AD + owner direction.)

## 2026-09-28 — Binding constraint #3 (pitch rows ≠ PA n)

Pitch-row counts are never cited as PA sample size. Sample size = terminal,
eligible PAs after the §AA funnel, reported per rule with counts + overlap.
(Source: Phase 3 §AA + owner direction.)

## 2026-09-28 — Friend CSVs deleted on owner order (uncommitted)
Both `data/Odds-Open-Close-2025-2026/*.csv` deleted. 98.8% redundant; the 35
friend-only events (12 real starts) preserved as workspace artifacts
(`friend_only_backup_*.parquet`, 290 + 34 rows). Re-check the 12 events before
the 2026 run. Eval panel verified clean: 5,600 rows, zero dupes at
(game,pitcher,line,book) and (game,pitcher,line), zero nulls in
p_model/p_open/p_close/K.

## 2026-09-28 — Phase 4 entries

- §AH canonical index appended to audit (this log is its decision companion).
- Workspace `research/offseason_2026/` scaffolded per §AF; boundary test result
  recorded in workspace README (or as a new entry here if it fails).
- Dataset specs frozen under `research/offseason_2026/specs/`; funnel manifest
  reconciled to §AA counts or discrepancies logged here as new entries.
## 2026-09-28 — PRE-REGISTRATION: 2025 walk-forward policy selection (NOT YET RUN)

Frozen input: eval_panel.parquet sha256
`7455234734575f318daaefbdefe69a7c53dc07d0eb16fe555e86176d11515585`
(5,600 rows; determinism 0.0; conventions in eval_panel_manifest.json).
Champion baseline: edge >= 0.12, best-price DK/FD at board clock, $50 flat,
no veto/cap/probation. Any run using other inputs is void.

Candidate grid (bounded, 12 configs + champion; nothing outside may win):
floors {0.10, 0.12, 0.14} x caps {0.20, 0.24} x probation {2.5/3.5-bump on/off}.
Veto 4.5-over always-on. Sides: model side only. Books: DK/FD best-price.
Stakes: $50 flat. Lines 2.5-9.5.

Selection criterion per checkpoint: maximize ROI lower confidence bound
(game-day clustered bootstrap, B=1000, seed = checkpoint YYYYMM), subject to:
(a) dual same-book CLV gate — beat-close frequency AND stake-weighted CLV >= 0;
(b) n>=30 per segment AND n>=200 per cell AND 100+5 BET-claim minimum
(binding constraint #2); (c) stability — positive LCB in >=2/3 of completed
forward folds. Failed gates logged with reason; no silent drops.

Block calendar (PRIMARY): warm-up Apr-May 2025 (no selection). End of Jun:
select on Apr-May, evaluate frozen on Jul. End of Jul: select on Apr-Jul,
evaluate Aug. End of Aug: select on Apr-Aug, evaluate Sep. Concatenate
Jul+Aug+Sep forward blocks as verdict. SENSITIVITY (after primary, never
before): 2025A/2025B half-split; bi-monthly blocks.

Multiple testing: the 12-config grid is the universe. Winner judged by White
reality check vs champion (stationary block bootstrap, block = game-day);
report the p-value. Log every configuration tried.

Freeze rule: optional final refit on all 2025 is IN-SAMPLE (binding constraint
1, never validation). Freeze config + hashes + date, then the 2026 locked run.
2027 prospective. No threshold/floor/veto/probation/cap/book/sizing change
after 2026 exposure.

No-2026 guard: selection harness MUST assert max panel game_date < 2026-01-01
and log the assertion firing before any metric is computed. Any 2026 read voids
the run.
## 2026-09-30 — PHASE 7 VERDICT: PROMOTE L3 AS PA DEVELOPMENT BASELINE [C5]

Decision: retain/promote L3 (contextual ridge logistic, beta_logitP3 0.92 +
20 family coefficients + 4 trip/index terms) as the PA development baseline.
Selection basis: registered 2023 fold evidence only (F1/F2 chronological folds;
C grid + family ablations + coefficient stability). Evaluation: 2024 E1/E2 used
once (executed string-date masks; see pa_split_provenance_correction_2026-09-30.md
for the registered-vs-executed count note — symmetric across arms, paired claims
unaffected). Baseline P3-log5 (pitcher prior m=100, 2023-selected; transparent
rollback target). L1 recalibration marginal; L2 smaller contribution; F6 rest
rejected (fold ablation ~zero). Fixed-offset contextual candidate NEVER RUN — no
performance estimate exists; earlier bound conjecture withdrawn. Actual historical
TBF and realized batter order were oracle-only diagnostics. Frozen production
comparator disqualified on 2024 (train overlap). No production, market, ROI, CLV,
or profitability conclusion follows. Card: experiments/logistic_pa/card.json
(sha 489b892b…); bundle reproducible to 2.2e-16 (intercept recovered, see
bundle/provenance_sidecar.md).

## 2026-09-30 — PHASE 8 VERDICT: RETAIN L3, STOP TREE SEARCH [C5]

Decision: retain L3; the registered tree search is CLOSED. T1 (LightGBM leaves 7 /
depth 3 / min_data 500 / ff 0.8 / L2 1.0, selected on 2023 folds) effectively tied
L3 on the once-only 2024 evaluation (E1 +0.000022, E2 -0.000042, both paired CIs
straddle 0) and did not clear the promotion requirement. T2 monotone dropped on
2023 development evidence (0.517279 vs 0.516918). T3 blend gate failed (2023-OOF
residual correlation 0.9965 vs the P3-log5 proxy; fold-fitted L3 not serialized).
Stop rule applied as registered. Same registered periods and baseline discipline;
2024 evaluation once-only; actual TBF and realized sequence remained oracle-only.
No market or profitability conclusion follows. Card:
experiments/tree_pa/card.json (sha 95b9627d…).
